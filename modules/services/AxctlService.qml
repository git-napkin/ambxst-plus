pragma Singleton

import QtQuick
import Quickshell
import Quickshell.Io
import qs.config
import "../../config/KeybindActions.js" as KeybindActions

Singleton {
    id: root

    property var focusedMonitor: null
    property var focusedWorkspace: null
    property var focusedClient: null

    // Becomes true once the axctl daemon socket is up and the subscribe stream
    // has delivered its first state. Services that query axctl at startup should
    // gate on this instead of racing the daemon (which spawns socket errors).
    property bool ready: false

    property int focusHistoryCounter: 0

    // Saved focus address — set before a shell overlay (notch/launcher/dashboard)
    // captures exclusive keyboard focus, and dispatched to the compositor to
    // restore focus when the overlay closes.
    property string savedFocusAddress: ""

    // Captures the address of the window that is focused *right now* so it can be
    // restored later. If no window is currently focused (e.g. the active
    // workspace is empty), nothing is saved so closing the overlay leaves the
    // user where they are instead of pulling focus to a stale window.
    // overlayFocusHeld stays true for the whole overlay even when no window was
    // saved: exclusive grabs keep the previous client marked focused/urgent,
    // which must not be treated as activation.
    property bool overlayFocusHeld: false

    function saveFocus() {
        let clients = root.clients.values || [];
        let current = clients.find(c => c.is_focused);
        root.savedFocusAddress = (current && current.address) ? current.address : "";
        root.overlayFocusHeld = true;
    }

    // Re-focus the saved window after an overlay closes. Deferred (see below).
    function restoreFocus() {
        root.overlayFocusHeld = false;
        if (root.savedFocusAddress)
            restoreFocusTimer.restart();
    }

    // The refocus is deferred for two reasons:
    //  1. The shell overlay only drops its exclusive keyboard grab a frame or two
    //     after the module closes; dispatching focuswindow before that happens is
    //     ignored by the compositor, leaving the app unfocused until the user
    //     clicks it (and breaking things like emoji paste that type into it).
    //  2. We only refocus if the saved window is still on the *current* active
    //     workspace, so a stale saved address can never yank the user to another
    //     workspace (e.g. opening settings jumping back to workspace 1).
    property Timer restoreFocusTimer: Timer {
        interval: 60
        repeat: false
        onTriggered: {
            const addr = root.savedFocusAddress;
            root.savedFocusAddress = "";
            if (!addr)
                return;
            const clients = root.clients.values || [];
            const win = clients.find(c => c.address === addr);
            const fmon = root.focusedMonitor;
            const activeWs = fmon && fmon.activeWorkspace ? fmon.activeWorkspace.id : -1;
            if (win && win.workspace && win.workspace.id === activeWs) {
                // Hyprland's focuswindow warps the cursor. Toggle cursor:no_warps around the focus.
                noWarpsOffComp.createObject(root, { addr: addr });
            }
        }
    }

    Component {
        id: noWarpsOffComp
        Process {
            property string addr: ""
            command: ["hyprctl", "keyword", "cursor:no_warps", "1"]
            running: true
            onExited: {
                focusRestoreComp.createObject(root, { addr: addr });
                destroy();
            }
        }
    }

    Component {
        id: focusRestoreComp
        Process {
            property string addr: ""
            command: ["axctl", "window", "focus", addr]
            running: true
            onExited: {
                noWarpsOnComp.createObject(root);
                destroy();
            }
        }
    }

    Component {
        id: noWarpsOnComp
        Process {
            command: ["hyprctl", "keyword", "cursor:no_warps", "0"]
            running: true
            onExited: destroy()
        }
    }

    function clearSavedFocus() {
        restoreFocusTimer.stop();
        root.savedFocusAddress = "";
        root.overlayFocusHeld = false;
    }

    property QtObject clients: QtObject {
        property var values: []
    }

    property QtObject monitors: QtObject {
        property var values: []
    }

    property QtObject workspaces: QtObject {
        property var values: []
    }

    signal rawEvent(var event)

    // Fired every time the subscribe stream (re)connects — the daemon always
    // sends a State.Dump as the first event of a connection. Consumers use
    // this to re-sync state that may have changed while the stream was down.
    signal subscribed()

    // Config path for axctl daemon
    property string configPath: (Quickshell.env("XDG_DATA_HOME") || (Quickshell.env("HOME") + "/.local/share")) + "/ambxst+/axctl.toml"

    function dispatch(command) {
        if (!command) return;

        let spaceIdx = command.indexOf(' ');
        let action = spaceIdx !== -1 ? command.substring(0, spaceIdx).trim() : command.trim();
        let rawArgs = spaceIdx !== -1 ? command.substring(spaceIdx + 1).trim() : "";

        let getAddr = (str) => {
            let m = str.match(/address:([^\s,]+)/);
            return m ? m[1] : str.trim();
        };

        let cmdArgs = [];

        if (action === "workspace") {
            cmdArgs = ["workspace", "switch", rawArgs];
        } else if (action === "closewindow") {
            cmdArgs = ["window", "close", getAddr(rawArgs)];
        } else if (action === "focuswindow") {
            cmdArgs = ["window", "focus", getAddr(rawArgs)];
        } else if (action === "movetoworkspacesilent") {
            let subParts = rawArgs.split(',');
            cmdArgs = ["window", "move-to-workspace-silent", subParts[0].trim()];
            if (subParts.length > 1) {
                cmdArgs.push(getAddr(subParts[1]));
            }
        } else if (action === "focusmonitor") {
            cmdArgs = ["monitor", "focus", rawArgs];
        } else if (action === "togglespecialworkspace") {
            cmdArgs = ["workspace", "toggle-special"];
            if (rawArgs) cmdArgs.push(rawArgs);
        } else {
            cmdArgs = ["system", "execute", command];
        }

        Quickshell.execDetached(["axctl"].concat(cmdArgs.filter(x => x !== "" && x !== undefined)));
    }

    function qtKeyToBindName(event) {
        const key = event ? event.key : 0;
        if (key >= Qt.Key_0 && key <= Qt.Key_9)
            return String(key - Qt.Key_0);
        if (key >= Qt.Key_A && key <= Qt.Key_Z)
            return String.fromCharCode(key);
        if (key === Qt.Key_Escape)
            return "Escape";
        if (key === Qt.Key_Return || key === Qt.Key_Enter)
            return "Return";
        if (key === Qt.Key_Space)
            return "SPACE";
        if (key === Qt.Key_Tab)
            return "Tab";
        if (key === Qt.Key_Backspace)
            return "BackSpace";
        if (key === Qt.Key_Left)
            return "left";
        if (key === Qt.Key_Right)
            return "right";
        if (key === Qt.Key_Up)
            return "up";
        if (key === Qt.Key_Down)
            return "down";
        if (key === Qt.Key_Comma)
            return "comma";
        if (key === Qt.Key_Period)
            return "period";
        if (key === Qt.Key_Minus)
            return "minus";
        if (key === Qt.Key_Equal)
            return "equal";
        if (key === Qt.Key_Slash)
            return "slash";
        if (key === Qt.Key_Super_L || key === Qt.Key_Super_R || key === Qt.Key_Meta)
            return "";
        const text = String((event && event.text) || "").trim();
        if (text.length === 1)
            return text.toUpperCase();
        return "";
    }

    function eventModifierNames(event) {
        const mods = [];
        if (!event)
            return mods;
        if (event.modifiers & Qt.MetaModifier)
            mods.push("SUPER");
        if (event.modifiers & Qt.ShiftModifier)
            mods.push("SHIFT");
        if (event.modifiers & Qt.ControlModifier)
            mods.push("CTRL");
        if (event.modifiers & Qt.AltModifier)
            mods.push("ALT");
        mods.sort();
        return mods;
    }

    function modsEqual(a, b) {
        const left = (a || []).map(m => String(m || "").toUpperCase()).sort();
        const right = (b || []).map(m => String(m || "").toUpperCase()).sort();
        if (left.length !== right.length)
            return false;
        for (let i = 0; i < left.length; i++) {
            if (left[i] !== right[i])
                return false;
        }
        return true;
    }

    function pushBindTarget(out, modifiers, key, dispatcher, argument) {
        const name = String(key || "").trim();
        if (!name || name.toLowerCase().indexOf("mouse") === 0)
            return;
        if (name === "Super_L" || name === "Super_R" || name === "SUPER_L" || name === "SUPER_R")
            return;
        out.push({
            modifiers: modifiers || [],
            key: name,
            dispatcher: dispatcher || "",
            argument: argument || ""
        });
    }

    function collectBindTargets() {
        const out = [];
        if (!Config.keybindsLoader || !Config.keybindsLoader.loaded || !Config.keybindsLoader.adapter)
            return out;
        const adapter = Config.keybindsLoader.adapter;
        const custom = adapter.custom || [];
        for (let i = 0; i < custom.length; i++) {
            const bind = custom[i];
            if (!bind || bind.enabled === false)
                continue;
            const keys = bind.keys && bind.keys.length ? bind.keys : [bind];
            const actions = bind.actions || [];
            for (let k = 0; k < keys.length; k++) {
                const keyObj = keys[k] || {};
                for (let a = 0; a < actions.length; a++) {
                    const action = actions[a] || {};
                    root.pushBindTarget(out, keyObj.modifiers || [], keyObj.key || "", action.dispatcher || "", action.argument || "");
                }
            }
        }
        function pushCore(keybind) {
            if (!keybind)
                return;
            const resolved = KeybindActions.resolveAction(keybind.action, keybind);
            if (!resolved)
                return;
            root.pushBindTarget(out, keybind.modifiers || [], keybind.key || "", resolved.dispatcher, resolved.argument);
        }
        const plus = adapter.ambxstPlus;
        if (plus) {
            pushCore(plus.launcher);
            pushCore(plus.dashboard);
            pushCore(plus.assistant);
            pushCore(plus.clipboard);
            pushCore(plus.emoji);
            pushCore(plus.notes);
            pushCore(plus.tmux);
            pushCore(plus.wallpapers);
            const sys = plus.system || {};
            pushCore(sys.overview);
            pushCore(sys.powermenu);
            pushCore(sys.config);
            pushCore(sys.lockscreen);
            pushCore(sys.tools);
            pushCore(sys.screenshot);
            pushCore(sys.screenrecord);
            pushCore(sys.lens);
            pushCore(sys.reload);
            pushCore(sys.quit);
        }
        return out;
    }

    // Exclusive layer-shell grabs eat Hyprland binds (workspace switch while
    // the dashboard or computer-use HUD is open). Replay matching binds here.
    function forwardBoundKey(event) {
        const name = root.qtKeyToBindName(event);
        if (!name)
            return false;
        const mods = root.eventModifierNames(event);
        const targets = root.collectBindTargets();
        let hit = false;
        for (let i = 0; i < targets.length; i++) {
            const bind = targets[i];
            if (!root.modsEqual(mods, bind.modifiers))
                continue;
            if (String(bind.key || "").toUpperCase() !== name.toUpperCase())
                continue;
            if (bind.dispatcher)
                root.dispatch(bind.dispatcher + (bind.argument ? " " + bind.argument : ""));
            hit = true;
        }
        return hit;
    }

    function monitorFor(screen) {
        if (!screen) return null;
        let screenName = screen.name || screen;
        let values = root.monitors.values || [];
        for (let i = 0; i < values.length; i++) {
            if (values[i].name === screenName) return values[i];
        }
        return null;
    }

    // Hyprland 0.56 dropped numeric workspace id (JSON has name/address only).
    // axctl may put the number in id, name, or workspace_id — never treat 0
    // from a failed parseInt as a real workspace.
    function parseWorkspaceId(a, b, c) {
        const vals = [a, b, c];
        for (let i = 0; i < vals.length; i++) {
            const n = parseInt(vals[i], 10);
            if (n > 0)
                return n;
        }
        return 0;
    }

    // Fingerprint of the last applied state. Every axctl event carries the full
    // state, and most events (title changes, geometry, focus moves) touch only a
    // handful of fields — but the old code unconditionally rebuilt and reassigned
    // all three arrays, firing change notifications to every consumer (bar, dock,
    // workspaces, taskbar, notch) even when nothing actually changed. This cheap
    // string compare lets us skip the whole mapping pass when the state is
    // bit-identical.
    property string _stateFingerprint: ""

    // Debounce guard for workspace-following. When the compositor focuses a
    // window on a workspace that isn't active (a link click activating the
    // browser on another workspace, a file opening in an app already running
    // elsewhere, …), we dispatch a workspace switch. If that dispatch is
    // ignored or fails, every subsequent state event would re-trigger the same
    // switch, so identical follow targets are throttled to once per window.
    property string _lastFollowKey: ""
    property int _lastFollowTime: 0
    property string _lastFocusedAddress: ""

    // Mirrors KDE/GNOME behaviour: when a window is activated on a workspace
    // that isn't the active one of its monitor, follow it there. Hyprland only
    // does this reliably when the app performed a proper xdg-activation request
    // with misc:focus_on_activate enabled; some apps (or configs) skip that, so
    // the compositor ends up with a focused window on a non-active workspace —
    // which is exactly the state this watches for. Called after every state
    // application; at steady state the focused window is always on the active
    // workspace of its monitor, so the mismatch is transient by construction.
    function followActivatedWorkspace() {
        if (!root.ready)
            return;
        if (!(Config.compositor?.switchToActivatedWorkspace ?? true))
            return;

        const monitors = root.monitors.values || [];
        const focused = root.focusedClient;
        const focusedAddr = (focused && focused.is_focused && focused.address) ? String(focused.address) : "";

        // Exclusive overlays keep the previous client marked focused/urgent.
        // Chasing that after a user workspace switch snaps back a frame later.
        if (root.overlayFocusHeld) {
            if (focusedAddr)
                root._lastFocusedAddress = focusedAddr;
            return;
        }

        // Path 1 — the compositor actually focused a window on a non-active
        // workspace (xdg-activation succeeded, e.g. misc:focus_on_activate is
        // enabled). Only follow when THIS window newly became focused. The same
        // client staying focused while the active workspace changes is a user
        // switch (or an empty workspace), not an activation.
        if (focused && focused.is_focused && (focused.workspace?.id ?? 0) > 0) {
            const fmon = monitors.find(m => m.id === focused.monitor);
            if (fmon && fmon.activeWorkspace && fmon.activeWorkspace.id !== focused.workspace.id) {
                if (focusedAddr && focusedAddr !== root._lastFocusedAddress) {
                    root.followTo(focused.address, focused.workspace.id, focused.monitor, false);
                    root._lastFocusedAddress = focusedAddr;
                    return;
                }
            }
        }

        if (focusedAddr)
            root._lastFocusedAddress = focusedAddr;

        // Path 2 — a window is demanding attention (urgent) on a non-active
        // workspace. This is what Hyprland reports when an activation request
        // is denied (misc:focus_on_activate disabled) or an app explicitly
        // demands attention (notification popup, new message, file open into
        // an existing window on another workspace, …). Switch to its workspace
        // and focus the window so the attention request is actually answered.
        const urgent = (root.clients.values || []).find(w => w.urgent && (w.workspace?.id ?? 0) > 0);
        if (!urgent)
            return;
        const umon = monitors.find(m => m.id === urgent.monitor);
        if (umon && umon.activeWorkspace && umon.activeWorkspace.id !== urgent.workspace.id) {
            root.followTo(urgent.address, urgent.workspace.id, urgent.monitor, true);
        }
    }

    // Switch the focused monitor to the target workspace and optionally focus
    // the target window explicitly (needed for urgent windows, which are not
    // focused yet; a normally activated window already has focus). Throttled
    // per window so a failed or ignored dispatch can't re-trigger on every
    // state event until the compositor settles.
    function followTo(address, wsId, monitorId, focusWindow) {
        const now = Date.now();
        const key = address + "|" + wsId;
        if (root._lastFollowKey === key && now - root._lastFollowTime < 750)
            return;
        root._lastFollowKey = key;
        root._lastFollowTime = now;

        // axctl's workspace switch acts on the focused monitor, so a window on
        // another screen needs that monitor focused first.
        const mon = (root.monitors.values || []).find(m => m.id === monitorId);
        if (root.focusedMonitor && mon && mon.id !== root.focusedMonitor.id)
            root.dispatch("focusmonitor " + mon.id);
        root.dispatch("workspace " + wsId);
        if (focusWindow)
            root.dispatch("focuswindow " + address);
    }

    function applyState(state) {
        if (!state) return;

        // Only the three tracked collections matter for change detection; the
        // event object may carry extra metadata that changes per event.
        const fingerprint = JSON.stringify([state.windows, state.workspaces, state.monitors]);
        if (fingerprint === root._stateFingerprint)
            return;
        root._stateFingerprint = fingerprint;

        // --- Windows ---
        if (state.windows) {
            let existingClients = root.clients.values || [];
            // Index existing clients by address once (O(n)) so the per-window
            // lookup below is O(1) instead of O(n²) on every compositor event.
            let existingMap = {};
            for (let i = 0; i < existingClients.length; i++) {
                existingMap[existingClients[i].address] = existingClients[i];
            }
            let mappedClients = state.windows.map(win => {
                let existing = existingMap[win.id];
                let prevFocus = existing && existing.focusHistoryID !== undefined ? existing.focusHistoryID : 999999;
                let newFocus = win.is_focused ? (existing && existing.is_focused ? prevFocus : --root.focusHistoryCounter) : prevFocus;
                return {
                    address: win.id,
                    class: win.app_id,
                    title: win.title,
                    workspace: { id: root.parseWorkspaceId(win.workspace_id), name: win.workspace_id },
                    monitor: parseInt(win.metadata ? win.metadata.monitor_id : 0) || 0,
                    floating: win.is_floating,
                    fullscreen: win.is_fullscreen,
                    hidden: win.is_hidden,
                    urgent: win.is_urgent || false,
                    mapped: true,
                    at: [win.metadata ? (win.metadata.x || 0) : 0, win.metadata ? (win.metadata.y || 0) : 0],
                    size: [win.metadata ? (win.metadata.width || 100) : 100, win.metadata ? (win.metadata.height || 100) : 100],
                    xwayland: (win.metadata ? win.metadata.xwayland : false) || false,
                    pid: parseInt(win.metadata ? (win.metadata.pid || 0) : 0) || 0,
                    is_focused: win.is_focused || false,
                    focusHistoryID: newFocus
                };
            });
            root.clients.values = mappedClients;
            // Prefer the window the compositor actually reports as focused. Only
            // fall back to the previously tracked client when nothing is focused
            // (e.g. a shell overlay is holding exclusive keyboard focus), so the
            // last real focus is preserved for restoreFocus().
            let focused = mappedClients.find(w => w.is_focused) || mappedClients.find(w => w.address === (root.focusedClient ? root.focusedClient.address : undefined)) || null;
            if (focused !== root.focusedClient) {
                root.focusedClient = focused;
            }
        }

        // --- Workspaces ---
        if (state.workspaces) {
            let mappedWorkspaces = state.workspaces.map(ws => ({
                id: root.parseWorkspaceId(ws.id, ws.name),
                name: ws.name,
                monitor: ws.monitor_id,
                active: ws.is_active,
                windows: 0
            }));
            root.workspaces.values = mappedWorkspaces;
            let focused = mappedWorkspaces.find(ws => ws.active) || null;
            if (focused !== root.focusedWorkspace) {
                root.focusedWorkspace = focused;
            }
        }

        // --- Monitors ---
        if (state.monitors) {
            let mappedMonitors = state.monitors.map(mon => ({
                id: parseInt(mon.id) || 0,
                name: mon.name,
                focused: mon.is_focused,
                width: mon.width,
                height: mon.height,
                refreshRate: mon.refresh_rate,
                x: mon.metadata ? (mon.metadata.x || 0) : 0,
                y: mon.metadata ? (mon.metadata.y || 0) : 0,
                scale: mon.scale,
                activeWorkspace: { id: root.parseWorkspaceId(mon.metadata ? mon.metadata.active_workspace : 0), name: mon.metadata ? mon.metadata.active_workspace : "" }
            }));
            root.monitors.values = mappedMonitors;
            let focused = mappedMonitors.find(m => m.focused) || null;
            if (focused !== root.focusedMonitor) {
                root.focusedMonitor = focused;
            }
        }

        root.followActivatedWorkspace();
    }

    property Process ensureConfigDir: Process {
        command: ["mkdir", "-p", (Quickshell.env("XDG_DATA_HOME") || (Quickshell.env("HOME") + "/.local/share")) + "/ambxst+"]
        running: true
    }

    // Restart the daemon if it dies (rebuild races, stale sockets, missing HYPR
    // env for a moment). Without this, subscribe loops forever on a dead socket.
    property int _daemonRestarts: 0
    property bool _shuttingDown: false
    property bool _restartingDaemon: false

    function restartDaemon() {
        if (root._shuttingDown || root._restartingDaemon)
            return;
        root._restartingDaemon = true;
        daemonRestartTimer.interval = Math.min(8000, 500 * Math.pow(2, Math.min(4, root._daemonRestarts)));
        if (axctlProcess.running)
            axctlProcess.running = false;
        daemonRestartTimer.restart();
    }

    Timer {
        id: daemonRestartTimer
        interval: 500
        repeat: false
        onTriggered: {
            if (root._shuttingDown) {
                root._restartingDaemon = false;
                return;
            }
            root._daemonRestarts += 1;
            axctlProcess.running = true;
            root._restartingDaemon = false;
        }
    }

    property Process axctlProcess: Process {
        command: ["axctl", "-c", root.configPath, "daemon"]
        running: true
        stderr: SplitParser {
            onRead: line => {
                if (line && String(line).trim().length)
                    console.warn("axctl daemon:", line);
            }
        }
        onExited: (code) => {
            console.warn("axctl daemon exited with code:", code);
            root.ready = false;
            if (root._shuttingDown || root._restartingDaemon)
                return;
            root.restartDaemon();
        }
        onRunningChanged: {
            if (running)
                console.log("axctl daemon starting");
        }
    }

    // Brief delay to let daemon start before subscribing
    Timer {
        id: subscribeDelay
        interval: 500
        running: true
        onTriggered: axctlSubscribe.running = true
    }

    // Auto-reconnect on unexpected subscribe exit
    Timer {
        id: reconnectTimer
        interval: 1000
        onTriggered: {
            if (!root._shuttingDown)
                axctlSubscribe.running = true;
        }
    }

    property Process axctlSubscribe: Process {
        command: ["axctl", "subscribe"]
        running: false
        stdout: SplitParser {
            onRead: (data) => {
                if (!data) return;
                const line = String(data).trim();
                if (!line.length)
                    return;
                // Connection errors go to stdout as plain text; don't treat as JSON.
                if (line.charAt(0) !== "{" && line.charAt(0) !== "[") {
                    console.warn("axctl subscribe:", line);
                    return;
                }
                try {
                    let parsedJson = JSON.parse(line);

                    // Apply inline state immediately (every event carries full state)
                    if (parsedJson.state) {
                        root.applyState(parsedJson.state);
                        if (!root.ready)
                            root.ready = true;
                        root._daemonRestarts = 0;
                    }

                    // Emit raw event for consumers
                    parsedJson.name = parsedJson.method ? parsedJson.method.split('.').pop().toLowerCase() : "";
                    parsedJson.data = parsedJson.params;
                    root.rawEvent(parsedJson);

                    if (parsedJson.method === "State.Dump") {
                        root.subscribed();
                    }
                } catch (e) {
                    console.error("AxctlService subscribe JSON parse error:", e);
                }
            }
        }
        onExited: (code) => {
            console.warn("axctl subscribe exited:", code);
            reconnectTimer.restart();
        }
    }

    Component.onDestruction: {
        root._shuttingDown = true;
        daemonRestartTimer.stop();
        reconnectTimer.running = false
        axctlProcess.running = false
        axctlSubscribe.running = false
    }
}
