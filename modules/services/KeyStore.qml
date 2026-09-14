pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root

    property string dbPath: Quickshell.dataPath("keys.db")
    property string scriptPath: Qt.resolvedUrl("../../scripts/keystore.py").toString().replace("file://", "")

    property var keyList: []
    property var keyCache: ({})
    property bool initialized: false
    property int revision: 0

    property string lastSaveError: ""
    signal saveFinished(bool ok, string message)
    signal keysChanged

    Component.onCompleted: {
        refreshKeys();
    }

    function _applyList(list) {
        const entries = Array.isArray(list) ? list : [];
        const cache = {};
        for (let i = 0; i < entries.length; i++) {
            const item = entries[i];
            if (!item || !item.provider || cache[item.provider])
                continue;
            cache[item.provider] = {
                api_key: item.api_key || "",
                endpoint: item.endpoint || "",
                custom_curl: item.custom_curl || ""
            };
        }
        root.keyList = entries;
        root.keyCache = cache;
        root.revision++;
        root.initialized = true;
        root.keysChanged();
    }

    function _start(proc, args) {
        proc.running = false;
        proc.command = args;
        proc.running = true;
    }

    function keysFor(provider) {
        const list = root.keyList || [];
        const out = [];
        for (let i = 0; i < list.length; i++) {
            if (list[i] && list[i].provider === provider)
                out.push(list[i]);
        }
        return out;
    }

    function refreshKeys() {
        root._start(listProcess, ["python3", scriptPath, dbPath, "list"]);
    }

    function getKey(provider) {
        if (!provider)
            return "";
        const hash = String(provider).indexOf("#");
        if (hash >= 0) {
            const id = Number(String(provider).slice(hash + 1));
            const list = root.keyList || [];
            for (let i = 0; i < list.length; i++) {
                if (Number(list[i].id) === id)
                    return list[i].api_key || "";
            }
            return "";
        }
        const entry = keyCache[provider];
        return entry ? entry.api_key : "";
    }

    function getEndpoint(provider) {
        if (!provider)
            return "";
        const entry = keyCache[provider];
        return entry ? entry.endpoint : "";
    }

    function getCustomCurl(provider) {
        if (!provider)
            return "";
        const entry = keyCache[provider];
        return entry ? entry.custom_curl : "";
    }

    function hasKey(provider) {
        const keys = root.keysFor(provider);
        for (let i = 0; i < keys.length; i++) {
            if (keys[i] && keys[i].api_key)
                return true;
        }
        return false;
    }

    function addKey(provider, apiKey, label, endpoint, customCurl) {
        const next = (root.keyList || []).slice();
        next.push({
            id: -Date.now(),
            provider: provider,
            label: label || "",
            api_key: apiKey,
            endpoint: endpoint || "",
            custom_curl: customCurl || ""
        });
        root._applyList(next);
        const args = ["python3", scriptPath, dbPath, "add", provider, apiKey, label || ""];
        if (endpoint)
            args.push(endpoint);
        if (customCurl)
            args.push(customCurl);
        root._start(setProcess, args);
    }

    function setKey(provider, apiKey, endpoint, customCurl) {
        root.addKey(provider, apiKey, "", endpoint, customCurl);
    }

    function deleteKey(provider) {
        const next = (root.keyList || []).filter(item => item && item.provider !== provider);
        root._applyList(next);
        root._start(deleteProcess, ["python3", scriptPath, dbPath, "delete", provider]);
    }

    function deleteKeyById(id) {
        const nid = Number(id);
        const next = (root.keyList || []).filter(item => Number(item.id) !== nid);
        root._applyList(next);
        root._start(deleteProcess, ["python3", scriptPath, dbPath, "delete-id", String(nid)]);
    }

    Process {
        id: listProcess
        stdout: StdioCollector {
            id: listStdout
            waitForEnd: true
            onStreamFinished: {
                try {
                    const data = JSON.parse(text.trim() || "[]");
                    if (!Array.isArray(data))
                        return;
                    Qt.callLater(() => root._applyList(data));
                } catch (e) {
                    console.warn("KeyStore: Failed to parse keys list:", e);
                }
            }
        }
        stderr: StdioCollector {
            waitForEnd: true
        }
    }

    Process {
        id: setProcess
        stdout: StdioCollector {
            id: setStdout
            waitForEnd: true
        }
        stderr: StdioCollector {
            id: setStderr
            waitForEnd: true
        }
        onExited: exitCode => {
            const message = (setStdout.text || setStderr.text || "").trim();
            if (exitCode !== 0) {
                root.lastSaveError = message || "Couldn't save the key";
                console.warn("KeyStore: Failed to set key:", root.lastSaveError);
                root.saveFinished(false, root.lastSaveError);
            } else {
                root.lastSaveError = "";
                root.saveFinished(true, "");
            }
            root.refreshKeys();
        }
    }

    Process {
        id: deleteProcess
        stdout: StdioCollector {
            id: deleteStdout
            waitForEnd: true
        }
        stderr: StdioCollector {
            id: deleteStderr
            waitForEnd: true
        }
        onExited: exitCode => {
            if (exitCode !== 0)
                console.warn("KeyStore: Failed to delete key:", deleteStdout.text || deleteStderr.text);
            root.refreshKeys();
        }
    }
}
