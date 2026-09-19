pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

QtObject {
    id: root

    property bool active: true
    property var items: []
    property var imageDataById: ({})
    property var linkPreviewCache: ({})
    property int revision: 0
    property bool _operationInProgress: false
    
    readonly property string dbPath: Quickshell.dataPath("clipboard.db")
    readonly property string binaryDataDir: Quickshell.dataPath("clipboard-data")
    readonly property string schemaPath: Qt.resolvedUrl("clipboard_init.sql").toString().replace("file://", "")
    readonly property string insertScriptPath: Qt.resolvedUrl("../../scripts/clipboard_insert.sh").toString().replace("file://", "")
    readonly property string checkScriptPath: Qt.resolvedUrl("../../scripts/clipboard_check.sh").toString().replace("file://", "")
    readonly property string watchScriptPath: Qt.resolvedUrl("../../scripts/clipboard_watch.sh").toString().replace("file://", "")
    readonly property string copyScriptPath: Qt.resolvedUrl("../../scripts/clipboard_copy.sh").toString().replace("file://", "")
    readonly property string gcScriptPath: Qt.resolvedUrl("../../scripts/clipboard_gc.sh").toString().replace("file://", "")
    readonly property string linkPreviewScriptPath: Qt.resolvedUrl("../../scripts/link_preview.py").toString().replace("file://", "")

    property bool _initialized: false

    property var suspendConnections: Connections {
        target: SuspendManager
        function onWakingUp() {
            // Small delay to allow wl-paste to work again after wake
            wakeRestartTimer.restart();
        }
    }

    property var wakeRestartTimer: Timer {
        id: wakeRestartTimer
        interval: 2000
        repeat: false
        onTriggered: {
            if (root._initialized) {
                root.list();
                clipboardWatcher.running = true;
            }
        }
    }

    signal listCompleted()

    // Clipboard watcher using custom script that monitors changes
    property Process clipboardWatcher: Process {
        running: root._initialized && !SuspendManager.isSuspending
        command: [watchScriptPath, checkScriptPath, dbPath, insertScriptPath, binaryDataDir]

        onRunningChanged: {
            if (running) {
                // Watcher started — arm the stability reset (fires only if it
                // stays alive long enough to prove it's not crash-looping).
                watcherStabilityTimer.restart();
            }
        }

        stdout: SplitParser {
            onRead: line => {
                if (line === "REFRESH_LIST")
                    Qt.callLater(root.list);
            }
        }
        
        stderr: StdioCollector {
            onStreamFinished: {
                if (text.length > 0 && !text.includes("No selection")) {
                    console.warn("ClipboardService: watcher stderr:", text);
                }
            }
        }
        
        onExited: function(code) {
            // Watcher should keep running, but restart with bounded exponential
            // backoff and a crash-loop cap so a broken watcher can't spawn a
            // process every few seconds forever. The backoff resets after the
            // watcher stays alive for a stable period.
            if (root._initialized && !SuspendManager.isSuspending) {
                console.warn("ClipboardService: watcher exited with code:", code, "- restarting in", root._watcherRestartDelay, "ms");
                root._watcherRestartCount++;
                root._watcherRestartDelay = Math.min(root._watcherRestartDelay * 2, root._maxWatcherRestartDelay);
                if (root._watcherRestartCount >= root._watcherRestartCap) {
                    console.warn("ClipboardService: watcher restart cap reached (" + root._watcherRestartCap + "), giving up until the next init/suspend cycle");
                    return;
                }
                watcherRestartTimer.restart();
            }
        }
    }

    // Bounded backoff restart for the clipboard watcher (see onExited above).
    property Timer watcherRestartTimer: Timer {
        interval: root._watcherRestartDelay
        repeat: false
        onTriggered: {
            if (root._initialized && !SuspendManager.isSuspending && root._watcherRestartCount < root._watcherRestartCap) {
                clipboardWatcher.running = true;
            }
        }
    }

    // Resets the watcher backoff after a stable run, so an occasional hiccup
    // restarts quickly again instead of staying throttled forever.
    property Timer watcherStabilityTimer: Timer {
        interval: 60000
        repeat: false
        onTriggered: {
            root._watcherRestartCount = 0;
            root._watcherRestartDelay = 1000;
        }
    }

    property int _watcherRestartCount: 0
    property int _watcherRestartDelay: 1000
    readonly property int _watcherRestartCap: 10
    readonly property int _maxWatcherRestartDelay: 30000

    // Initialize database
    property Process initDbProcess: Process {
        running: false
        
        stderr: StdioCollector {
            onStreamFinished: {
                if (text.length > 0) console.warn("ClipboardService: DB Init Error: " + text)
            }
        }

        onExited: function(code) {
            if (code === 0) {
                root._initialized = true;
                ensureBinaryDataDir();
                Qt.callLater(root.list);
            } else {
                console.warn("ClipboardService: Failed to initialize database (Exit code: " + code + ")");
            }
        }
    }

    property Process ensureDirProcess: Process {
        running: false
    }

    // Single process to check and insert clipboard content (used for manual checks)
    property Process checkAndInsertProcess: Process {
        running: false
        
        stderr: StdioCollector {
            onStreamFinished: {
                if (text.length > 0 && !text.includes("No selection")) {
                    console.warn("ClipboardService: checkAndInsertProcess stderr:", text);
                }
            }
        }
        
        onExited: function(code) {
            _operationInProgress = false;
            if (code === 0) {
                Qt.callLater(root.list);
            }
        }
    }

    // List all items from database
    property Process listProcess: Process {
        running: false
        
        stdout: StdioCollector {
            waitForEnd: true
            
            onStreamFinished: {
                const raw = text;
                Qt.callLater(() => {
                var clipboardItems = [];
                
                var trimmedText = raw.trim();
                if (trimmedText.length === 0) {
                    root.items = clipboardItems;
                    root.listCompleted();
                    root._operationInProgress = false;
                    return;
                }
                
                try {
                    var jsonArray = JSON.parse(trimmedText);
                    
                    for (var i = 0; i < jsonArray.length; i++) {
                        var item = jsonArray[i];
                        var isFile = item.mime_type === "text/uri-list";
                        
                        // For files, extract the filename from the URI for preview
                        var preview = item.preview;
                        if (isFile && item.full_content) {
                            var uriContent = item.full_content.trim();
                            if (uriContent.startsWith("file://")) {
                                var filePath = uriContent.substring(7); // Remove "file://"
                                var fileName = filePath.split('/').pop();
                                // Decode URL encoding (e.g., %20 -> space)
                                fileName = root.decodeUriString(fileName);
                                preview = "[File] " + fileName;
                            }
                        } else if (item.is_image === 1) {
                            preview = "[Image]";
                        }
                        
                        clipboardItems.push({
                            id: item.id.toString(),
                            preview: preview,
                            fullContent: item.preview,
                            mime: item.mime_type,
                            isImage: item.is_image === 1,
                            isFile: isFile,
                            binaryPath: item.binary_path || "",
                            hash: item.content_hash || "",
                            size: item.size || 0,
                            createdAt: item.created_at || 0,
                            pinned: item.pinned === 1,
                            alias: item.alias || "",
                            displayIndex: item.display_index !== null ? item.display_index : -1
                        });
                    }
                } catch (e) {
                    console.warn("ClipboardService: Failed to parse clipboard items:", e);
                }
                
                root.items = clipboardItems;
                root.listCompleted();
                root._operationInProgress = false;
                });
            }
        }
        
        stderr: StdioCollector {
            onStreamFinished: {
                if (text.length > 0) {
                    console.warn("ClipboardService: listProcess stderr:", text);
                }
            }
        }
        
        onExited: function(code) {
            if (code !== 0) {
                root.items = [];
                root.listCompleted();
                root._operationInProgress = false;
            }
        }
    }

    // One-shot request process: array arguments (no shell wrapper), collects
    // stdout, calls onDone(code, text) exactly once, then destroys itself.
    // Each call gets its own instance, so concurrent requests can't clobber
    // each other's request id (the shared-process race in the old
    // getContentProcess / loadImageProcess / linkPreviewProcess).
    property Component requestProcComp: Component {
        Process {
            property var cmd: []
            property var onDone: null
            command: cmd
            running: true
            stdout: StdioCollector {
                waitForEnd: true
            }
            onExited: (code) => {
                if (onDone) onDone(code, stdout.text || "");
                destroy();
            }
        }
    }

    function _numericId(id) {
        const s = String(id);
        return /^\d+$/.test(s) ? s : "";
    }

    function _utf8Hex(str) {
        const utf8 = unescape(encodeURIComponent(str));
        let hex = "";
        for (let i = 0; i < utf8.length; i++)
            hex += ("0" + utf8.charCodeAt(i).toString(16)).slice(-2);
        return hex;
    }

    function _sqliteCmd() {
        const args = ["sqlite3", dbPath, ".timeout 5000"];
        for (let i = 0; i < arguments.length; i++)
            args.push(arguments[i]);
        return args;
    }

    function _runRequest(cmd, onDone) {
        requestProcComp.createObject(root, { cmd: cmd, onDone: onDone });
    }

    // Get full content of an item
    function getFullContent(id) {
        if (!_initialized) return;
        const nid = _numericId(id);
        if (!nid) return;
        _runRequest(_sqliteCmd("SELECT full_content FROM clipboard_items WHERE id = " + nid + ";"), (code, text) => {
            root.fullContentRetrieved(id, code === 0 ? text : "");
        });
    }

    // Delete item
    property Process deleteProcess: Process {
        property string itemId: ""
        running: false
        
        stdout: StdioCollector {
            waitForEnd: true
            
            onStreamFinished: {
                var deletedHash = text.trim();
                if (deletedHash.length > 0) {
                    // Check if current clipboard content matches the deleted item
                    clearClipboardIfMatches.deletedHash = deletedHash;
                    clearClipboardIfMatches.running = true;
                }
            }
        }
        
        stderr: StdioCollector {
            onStreamFinished: {
                if (text.length > 0) {
                    console.warn("ClipboardService: deleteProcess stderr:", text);
                }
            }
        }
        
        onExited: function(code) {
            if (code === 0) {
                Qt.callLater(root.list);
            } else {
                root._operationInProgress = false;
            }
        }
    }
    
    // Clear system clipboard if it matches deleted item
    property Process clearClipboardIfMatches: Process {
        property string deletedHash: ""
        running: false
        
        command: ["bash", "-c",
            'CURRENT_HASH=""; ' +
            'if CONTENT=$(wl-paste --type text/uri-list 2>/dev/null); then ' +
            '  CURRENT_HASH=$(printf "%s" "$CONTENT" | tr -d "\\r" | md5sum | cut -d" " -f1); ' +
            'elif CONTENT=$(wl-paste --type text/plain 2>/dev/null); then ' +
            '  CURRENT_HASH=$(printf "%s" "$CONTENT" | md5sum | cut -d" " -f1); ' +
            'elif IMAGE_MIME=$(wl-paste --list-types 2>/dev/null | grep "^image/" | head -1); then ' +
            '  [ -n "$IMAGE_MIME" ] && CURRENT_HASH=$(wl-paste --type "$IMAGE_MIME" 2>/dev/null | md5sum | cut -d" " -f1); ' +
            'fi; ' +
            '[ "$CURRENT_HASH" = "$1" ] && wl-copy --clear >/dev/null 2>&1 || true',
            "clear-if-match", deletedHash
        ]
        
        stderr: StdioCollector {
            onStreamFinished: {
                if (text.length > 0 && !text.includes("No selection")) {
                    console.warn("ClipboardService: clearClipboardIfMatches stderr:", text);
                }
            }
        }
    }

    // Clear all items
    property Process clearProcess: Process {
        running: false
        
        onExited: function(code) {
            if (code === 0) {
                Qt.callLater(root.list);
                cleanBinaryDataDirProcess.running = true;
                root.wlCopyProc.command = ["wl-copy", "--clear"];
                root.wlCopyProc.running = false;
                root.wlCopyProc.running = true;
            }
        }
    }
    
    // Toggle pin status
    property Process togglePinProcess: Process {
        property string itemId: ""
        running: false
        
        stderr: StdioCollector {
            onStreamFinished: {
                if (text.length > 0) {
                    console.warn("ClipboardService: togglePinProcess stderr:", text);
                }
            }
        }
        
        onExited: function(code) {
            if (code === 0) {
                Qt.callLater(root.list);
            } else {
                root._operationInProgress = false;
            }
        }
    }
    
    // Set alias for item
    property Process setAliasProcess: Process {
        property string itemId: ""
        running: false
        
        stderr: StdioCollector {
            onStreamFinished: {
                if (text.length > 0) {
                    console.warn("ClipboardService: setAliasProcess stderr:", text);
                }
            }
        }
        
        onExited: function(code) {
            if (code === 0) {
                Qt.callLater(root.list);
            } else {
                root._operationInProgress = false;
            }
        }
    }
    
    // Clean binary data directory - only remove orphaned files
    property Process cleanBinaryDataDirProcess: Process {
        running: false
        command: [gcScriptPath, dbPath, binaryDataDir]
    }

    // Load image data
    function decodeToDataUrl(id, mime) {
        if (imageDataById[id]) {
            return;
        }
        
        for (var i = 0; i < items.length; i++) {
            if (items[i].id === id) {
                var binaryPath = items[i].binaryPath;
                if (binaryPath && binaryPath.length > 0) {
                    _runRequest(["base64", "-w", "0", binaryPath], (code, text) => {
                        if (code === 0 && text.length > 0) {
                            var cleanBase64 = text.replace(/\s/g, '');
                            root.imageDataById[id] = "data:" + mime + ";base64," + cleanBase64;
                            root.revision++;
                        }
                    });
                }
                break;
            }
        }
    }
    
    // Link preview metadata fetcher — one process per request so a slow fetch
    // can't be clobbered by a later one (url/itemId are per-call, not shared).
    function fetchLinkPreview(url, itemId) {
        if (!_initialized) return;
        
        // Check cache first
        if (linkPreviewCache[url]) {
            Qt.callLater(function() {
                root.linkPreviewFetched(url, linkPreviewCache[url], itemId);
            });
            return;
        }
        
        _runRequest(["python3", linkPreviewScriptPath, url, "5"], (code, text) => {
            if (code !== 0) {
                root.linkPreviewFetched(url, {'error': 'Failed to fetch preview'}, itemId);
                return;
            }
            try {
                var metadata = JSON.parse(text);
                // Use request_url from the response - this is the original URL we
                // requested (per-call now, so no cross-request clobbering)
                var responseUrl = metadata.request_url || metadata.url || url;
                
                // Cache the result if successful, using the URL from the response
                if (!metadata.error && responseUrl) {
                    root.linkPreviewCache[responseUrl] = metadata;
                }
                root.linkPreviewFetched(responseUrl, metadata, itemId);
            } catch (e) {
                console.warn("ClipboardService: Failed to parse link preview:", e);
                root.linkPreviewFetched(url, {'error': 'Failed to parse response'}, itemId);
            }
        });
    }

    signal fullContentRetrieved(string itemId, string content)
    signal linkPreviewFetched(string url, var metadata, string itemId)
    
    // Function to decode URL-encoded strings
    function decodeUriString(str) {
        try {
            return decodeURIComponent(str);
        } catch (e) {
            // If decoding fails, return original string
            return str;
        }
    }

    function initialize() {
        initDbProcess.command = ["sqlite3", dbPath, ".read '" + schemaPath.replace(/'/g, "''") + "'"];
        initDbProcess.running = true;
    }

    function ensureBinaryDataDir() {
        ensureDirProcess.command = ["mkdir", "-p", binaryDataDir];
        ensureDirProcess.running = true;
    }

    function checkClipboard() {
        if (!_initialized || _operationInProgress) return;
        _operationInProgress = true;
        checkAndInsertProcess.command = [checkScriptPath, dbPath, insertScriptPath, binaryDataDir];
        checkAndInsertProcess.running = true;
    }

    function list() {
        if (!_initialized) return;
        _operationInProgress = true;
        listProcess.command = _sqliteCmd(".mode json",
            "SELECT id, mime_type, preview, is_image, binary_path, content_hash, size, created_at, pinned, alias, display_index FROM clipboard_items ORDER BY pinned DESC, display_index ASC, updated_at DESC, id DESC LIMIT 100;");
        listProcess.running = true;
    }

    function deleteItem(id) {
        if (!_initialized) return;
        const nid = _numericId(id);
        if (!nid) return;
        _operationInProgress = true;
        deleteProcess.itemId = nid;
        deleteProcess.command = _sqliteCmd(
            "SELECT content_hash FROM clipboard_items WHERE id = " + nid + "; DELETE FROM clipboard_items WHERE id = " + nid + ";"
        );
        deleteProcess.running = true;
    }

    function clear() {
        if (!_initialized) return;
        clearProcess.command = ["sqlite3", dbPath, ".timeout 5000", "DELETE FROM clipboard_items WHERE pinned = 0;"];
        clearProcess.running = true;
    }

    function togglePin(id) {
        if (!_initialized) return;
        const nid = _numericId(id);
        if (!nid) return;
        _operationInProgress = true;
        togglePinProcess.itemId = nid;
        togglePinProcess.command = _sqliteCmd(
            "BEGIN TRANSACTION; " +
            "UPDATE clipboard_items SET pinned = CASE WHEN pinned = 1 THEN 0 ELSE 1 END WHERE id = " + nid + "; " +
            "UPDATE clipboard_items SET display_index = CASE " +
            "  WHEN id = " + nid + " THEN 0 " +
            "  ELSE display_index + 1 " +
            "END WHERE pinned = (SELECT pinned FROM clipboard_items WHERE id = " + nid + "); " +
            "WITH reindexed_pinned AS ( " +
            "  SELECT id, ROW_NUMBER() OVER (ORDER BY display_index ASC, updated_at DESC, id DESC) - 1 AS new_idx " +
            "  FROM clipboard_items WHERE pinned = 1 " +
            ") " +
            "UPDATE clipboard_items SET display_index = (SELECT new_idx FROM reindexed_pinned WHERE reindexed_pinned.id = clipboard_items.id) WHERE pinned = 1; " +
            "WITH reindexed_unpinned AS ( " +
            "  SELECT id, ROW_NUMBER() OVER (ORDER BY display_index ASC, updated_at DESC, id DESC) - 1 AS new_idx " +
            "  FROM clipboard_items WHERE pinned = 0 " +
            ") " +
            "UPDATE clipboard_items SET display_index = (SELECT new_idx FROM reindexed_unpinned WHERE reindexed_unpinned.id = clipboard_items.id) WHERE pinned = 0; " +
            "COMMIT;"
        );
        togglePinProcess.running = true;
    }

    function setAlias(id, alias) {
        if (!_initialized) return;
        const nid = _numericId(id);
        if (!nid) return;
        _operationInProgress = true;
        setAliasProcess.itemId = nid;
        if (String(alias).trim() === "") {
            setAliasProcess.command = _sqliteCmd("UPDATE clipboard_items SET alias = NULL WHERE id = " + nid + ";");
        } else {
            const hex = _utf8Hex(String(alias));
            setAliasProcess.command = _sqliteCmd("UPDATE clipboard_items SET alias = CAST(x'" + hex + "' AS TEXT) WHERE id = " + nid + ";");
        }
        setAliasProcess.running = true;
    }

    function getImageData(id) {
        return imageDataById[id] || "";
    }
    
    // Reorder item by moving it to a new index
    function reorderItem(itemId, newIndex) {
        if (!_initialized) return;
        
        // Get current item info
        var item = null;
        for (var i = 0; i < items.length; i++) {
            if (items[i].id === itemId) {
                item = items[i];
                break;
            }
        }
        
        if (!item) return;
        
        const nid = _numericId(itemId);
        if (!nid) return;
        var isPinned = item.pinned ? 1 : 0;
        
        // Validate newIndex is non-negative
        if (newIndex < 0) newIndex = 0;
        const idx = String(Math.floor(Number(newIndex)));
        if (!/^\d+$/.test(idx)) return;
        
        reorderProcess.command = _sqliteCmd(
            "BEGIN TRANSACTION; " +
            "UPDATE clipboard_items SET display_index = display_index + 1 WHERE pinned = " + isPinned + " AND display_index >= " + idx + " AND id != " + nid + "; " +
            "UPDATE clipboard_items SET display_index = " + idx + " WHERE id = " + nid + "; " +
            "WITH reindexed AS ( " +
            "  SELECT id, ROW_NUMBER() OVER (ORDER BY display_index ASC, updated_at DESC, id DESC) - 1 AS new_idx " +
            "  FROM clipboard_items WHERE pinned = " + isPinned + " " +
            ") " +
            "UPDATE clipboard_items SET display_index = (SELECT new_idx FROM reindexed WHERE reindexed.id = clipboard_items.id) WHERE pinned = " + isPinned + "; " +
            "COMMIT;"
        );
        reorderProcess.running = true;
    }
    
    // Move item up (decrease index)
    function moveItemUp(itemId) {
        var item = null;
        var currentIdx = -1;
        for (var i = 0; i < items.length; i++) {
            if (items[i].id === itemId) {
                item = items[i];
                currentIdx = i;
                break;
            }
        }
        
        if (!item || currentIdx < 0) return;
        
        // Can't move up if first item
        if (currentIdx === 0) return;
        
        // Check if previous item has same pinned status
        var prevItem = items[currentIdx - 1];
        if (prevItem.pinned !== item.pinned) return;
        
        // Optimistic update: Swap in local array
        var temp = items[currentIdx];
        items[currentIdx] = items[currentIdx - 1];
        items[currentIdx - 1] = temp;
        
        // Notify UI to update immediately
        listCompleted();
        
        // Swap indices with previous item
        swapItems(itemId, prevItem.id);
    }
    
    // Move item down (increase index)
    function moveItemDown(itemId) {
        var item = null;
        var currentIdx = -1;
        for (var i = 0; i < items.length; i++) {
            if (items[i].id === itemId) {
                item = items[i];
                currentIdx = i;
                break;
            }
        }
        
        if (!item || currentIdx < 0) return;
        
        // Can't move down if last item
        if (currentIdx >= items.length - 1) return;
        
        // Check if next item has same pinned status
        var nextItem = items[currentIdx + 1];
        if (nextItem.pinned !== item.pinned) return;
        
        // Optimistic update: Swap in local array
        var temp = items[currentIdx];
        items[currentIdx] = items[currentIdx + 1];
        items[currentIdx + 1] = temp;
        
        // Notify UI to update immediately
        listCompleted();
        
        // Swap indices with next item
        swapItems(itemId, nextItem.id);
    }
    
    // Swap display indices between two items
    function swapItems(itemId1, itemId2) {
        if (!_initialized) return;
        const a = _numericId(itemId1);
        const b = _numericId(itemId2);
        if (!a || !b) return;

        swapSqlProcess.command = _sqliteCmd(
            "BEGIN TRANSACTION; " +
            "WITH reindexed_pinned AS ( " +
            "  SELECT id, ROW_NUMBER() OVER (ORDER BY display_index ASC, updated_at DESC, id DESC) - 1 AS new_idx " +
            "  FROM clipboard_items WHERE pinned = 1 " +
            ") " +
            "UPDATE clipboard_items SET display_index = (SELECT new_idx FROM reindexed_pinned WHERE reindexed_pinned.id = clipboard_items.id) WHERE pinned = 1; " +
            "WITH reindexed_unpinned AS ( " +
            "  SELECT id, ROW_NUMBER() OVER (ORDER BY display_index ASC, updated_at DESC, id DESC) - 1 AS new_idx " +
            "  FROM clipboard_items WHERE pinned = 0 " +
            ") " +
            "UPDATE clipboard_items SET display_index = (SELECT new_idx FROM reindexed_unpinned WHERE reindexed_unpinned.id = clipboard_items.id) WHERE pinned = 0; " +
            "CREATE TEMP TABLE IF NOT EXISTS swap_temp (idx1 INTEGER, idx2 INTEGER); " +
            "DELETE FROM swap_temp; " +
            "INSERT INTO swap_temp (idx1, idx2) " +
            "  SELECT " +
            "    (SELECT display_index FROM clipboard_items WHERE id = " + a + "), " +
            "    (SELECT display_index FROM clipboard_items WHERE id = " + b + "); " +
            "UPDATE clipboard_items SET display_index = (SELECT idx2 FROM swap_temp) WHERE id = " + a + "; " +
            "UPDATE clipboard_items SET display_index = (SELECT idx1 FROM swap_temp) WHERE id = " + b + "; " +
            "DELETE FROM swap_temp; " +
            "COMMIT;"
        );
        swapSqlProcess.running = false;
        swapSqlProcess.running = true;
    }

    property Process swapSqlProcess: Process {
        running: false
        onExited: function(code) {
            if (code === 0) {
                Qt.callLater(root.list);
            } else {
                console.warn("ClipboardService: swapSqlProcess failed with code:", code);
            }
        }
    }
    

    property Process reorderProcess: Process {
        running: false
        
        stderr: StdioCollector {
            onStreamFinished: {
                if (text.length > 0) {
                    console.warn("ClipboardService: reorderProcess stderr:", text);
                }
            }
        }
        
        onExited: function(code) {
            if (code === 0) {
                Qt.callLater(root.list);
            }
        }
    }
    
    // Emoji paste process - persists even when dashboard closes
    property Process emojiTypeProcess: Process {
        running: false
        
        stderr: StdioCollector {
            onStreamFinished: {
                if (text.length > 0) {
                    console.warn("ClipboardService: emojiTypeProcess stderr:", text);
                }
            }
        }
        
        onExited: function(code) {
            if (code !== 0) {
                console.warn("ClipboardService: emojiTypeProcess failed with code:", code);
            }
        }
    }
    
    property Timer emojiTypeTimer: Timer {
        interval: 250
        repeat: false
        onTriggered: {
            // Simulate Ctrl+V: press Ctrl, press V, release V, release Ctrl
            emojiTypeProcess.command = ["wtype", "-M", "ctrl", "-P", "v", "-p", "v", "-m", "ctrl"];
            emojiTypeProcess.running = true;
        }
    }
    
    property Process wlCopyProc: Process {
        running: false
    }

    function copyAndTypeEmoji(emojiText) {
        wlCopyProc.command = ["wl-copy", emojiText];
        wlCopyProc.running = false;
        wlCopyProc.running = true;
        emojiTypeTimer.start();
    }

    Component.onCompleted: {
        Qt.callLater(() => initialize());
    }
}
