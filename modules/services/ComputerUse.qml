pragma Singleton

import QtQuick
import Quickshell
import Quickshell.Io
import qs.modules.globals
import qs.config

Singleton {
    id: root

    property string sessionState: "idle"
    readonly property bool sessionActive: sessionState !== "idle"
    property bool userHasControl: false
    property bool hudCollapsed: false
    property bool hudHiddenForCapture: false
    property bool noscreenshare: false
    property bool composerFocused: false
    property bool ydotoolStarted: false
    property string lastAction: ""
    property string taskSummary: ""
    property string hudScreen: ""
    property real hudWidth: 360
    property var pidByAddress: ({})

    property var _actionCb: null
    property var _pendingCapture: null
    property string _focusAddress: ""
    property bool _focusWarp: false
    property int _focusTries: 0
    property bool _hideThenCapture: false

    readonly property int inset: 24
    readonly property int barReserve: {
        const pos = (Config.bar && Config.bar.position) ? Config.bar.position : "top";
        const pinned = Config.bar && Config.bar.pinnedOnStartup !== false;
        if (!pinned)
            return 0;
        if (pos === "bottom" || pos === "right")
            return 56;
        return 0;
    }
    readonly property int insetRight: inset + ((Config.bar && Config.bar.position === "right") ? barReserve : 0)
    readonly property int insetBottom: inset + ((Config.bar && Config.bar.position === "bottom") ? barReserve : 0)

    function screenList() {
        const out = [];
        const screens = Quickshell.screens;
        for (let i = 0; i < screens.length; i++) {
            const s = screens[i];
            out.push({
                name: s.name,
                origin_x: s.x,
                origin_y: s.y,
                width: s.width,
                height: s.height,
                scale: s.scale || 1
            });
        }
        return out;
    }

    function pickScreen(name) {
        const screens = screenList();
        if (name) {
            for (let i = 0; i < screens.length; i++) {
                if (screens[i].name === name)
                    return screens[i];
            }
        }
        const focused = AxctlService.focusedMonitor;
        if (focused && focused.name) {
            for (let i = 0; i < screens.length; i++) {
                if (screens[i].name === focused.name)
                    return screens[i];
            }
        }
        return screens.length ? screens[0] : null;
    }

    function windowPayload(c) {
        if (!c)
            return null;
        const addr = c.address || "";
        const pid = c.pid || root.pidByAddress[addr] || 0;
        return {
            address: addr,
            title: c.title || "",
            class: c.class || c.class_name || "",
            class_name: c.class || c.class_name || "",
            focused: !!c.is_focused,
            at: c.at || [0, 0],
            size: c.size || [0, 0],
            workspace: c.workspace || {},
            monitor: c.monitor,
            floating: !!c.floating,
            fullscreen: !!c.fullscreen,
            xwayland: !!c.xwayland,
            pid: pid || 0
        };
    }

    function windowsPayload() {
        const clients = AxctlService.clients.values || [];
        return clients.map(c => root.windowPayload(c));
    }

    function findWindow(args) {
        args = args || {};
        const windows = root.windowsPayload();
        const address = String(args.address || args.window_id || "").trim();
        if (address) {
            for (let i = 0; i < windows.length; i++) {
                if (String(windows[i].address) === address)
                    return windows[i];
            }
            return null;
        }
        if (args.pid !== undefined && args.pid !== null && args.pid !== "") {
            const hits = windows.filter(w => String(w.pid) === String(args.pid));
            return hits.length === 1 ? hits[0] : null;
        }
        const cls = String(args.class || args.app_id || args.wm_class || "").toLowerCase().trim();
        if (cls) {
            for (let i = 0; i < windows.length; i++) {
                if (String(windows[i].class || "").toLowerCase() === cls)
                    return windows[i];
            }
        }
        const title = String(args.title || args.window_title || "").toLowerCase().trim();
        if (title) {
            for (let i = 0; i < windows.length; i++) {
                if (String(windows[i].title || "").toLowerCase().indexOf(title) !== -1)
                    return windows[i];
            }
        }
        return null;
    }

    function sessionSnapshot() {
        const focused = root.windowPayload(AxctlService.focusedClient);
        return {
            locked: !!GlobalStates.lockscreenVisible,
            noscreenshare: root.noscreenshare,
            screens: root.screenList(),
            focused_window: focused,
            windows: root.windowsPayload()
        };
    }

    function applyNoscreenshare() {
        Quickshell.execDetached(["hyprctl", "keyword", "layerrule", "noscreenshare,ambxst+:computer-use"]);
        root.noscreenshare = true;
    }

    function ensureYdotoold() {
        if (root.ydotoolStarted || ydoProc.running)
            return;
        const runtime = Quickshell.env("XDG_RUNTIME_DIR") || "/tmp";
        ydoProc.command = ["ydotoold", "--socket", runtime + "/.ydotool_socket"];
        ydoProc.running = true;
        root.ydotoolStarted = true;
    }

    function begin(summary) {
        if (GlobalStates.lockscreenVisible)
            return Object.assign({ error: "computer use is blocked while the session is locked" }, root.sessionSnapshot());
        root.taskSummary = summary || "";
        root.lastAction = "session started";
        root.userHasControl = false;
        root.hudCollapsed = false;
        root.hudHiddenForCapture = false;
        root.composerFocused = false;
        root.hudScreen = Visibilities.lastFocusedScreen || (root.pickScreen("") ? root.pickScreen("").name : "");
        root.applyNoscreenshare();
        root.ensureYdotoold();
        root.refreshPids();
        root.sessionState = "agentDriving";
        if (Visibilities.currentActiveModule !== "assistant")
            Visibilities.setActiveModule("assistant");
        return root.sessionSnapshot();
    }

    function end(opts) {
        const restore = !opts || opts.restoreSpotlight !== false;
        root.sessionState = "idle";
        root.userHasControl = false;
        root.composerFocused = false;
        root.hudHiddenForCapture = false;
        root.hudCollapsed = false;
        root.lastAction = "";
        root.taskSummary = "";
        if (restore && Visibilities.currentActiveModule !== "assistant")
            Visibilities.setActiveModule("assistant");
    }

    function stop() {
        root.end({ restoreSpotlight: true });
    }

    function takeControl() {
        if (!root.sessionActive)
            return;
        root.userHasControl = true;
        root.composerFocused = false;
        root.sessionState = "userControl";
        root.lastAction = "user has control";
    }

    function handBack() {
        if (!root.sessionActive)
            return;
        root.userHasControl = false;
        root.sessionState = "agentDriving";
        root.lastAction = "agent driving";
        root.syncFromChat(false);
    }

    function syncFromChat(approvalPending) {
        if (!root.sessionActive)
            return;
        if (approvalPending)
            root.sessionState = "approvalWait";
        else if (root.userHasControl)
            root.sessionState = "userControl";
        else
            root.sessionState = "agentDriving";
    }

    function gate(action, summary) {
        if (GlobalStates.lockscreenVisible)
            return { locked: true, error: "computer use is blocked while the session is locked" };
        if (!root.sessionActive) {
            const started = root.begin(summary || action || "");
            if (started.error)
                return started;
        }
        if (summary)
            root.lastAction = String(summary);
        else if (action)
            root.lastAction = String(action);
        return {
            locked: false,
            user_control: root.userHasControl,
            session_state: root.sessionState
        };
    }

    function handleSession(args) {
        const op = (args && args.op) || "";
        if (op === "begin")
            return root.begin((args && args.task_summary) || "");
        if (op === "end") {
            root.end({ restoreSpotlight: true });
            return { ok: true };
        }
        if (op === "gate")
            return root.gate((args && args.action) || "", (args && args.summary) || "");
        return { error: "unknown computer_use_session op" };
    }

    function handleAction(args, cb) {
        const done = result => Qt.callLater(() => {
            if (cb)
                cb(result || {});
        });
        args = args || {};
        const action = args.action || "";
        if (action === "screenshot") {
            root.captureScreenshot(args, done);
            return;
        }
        if (action === "focus") {
            root.focusWindow(args, args.warp === true || args.warp === "true", done);
            return;
        }
        if (action === "move_window") {
            root.moveOrResize(args, "move", done);
            return;
        }
        if (action === "resize_window") {
            root.moveOrResize(args, "resize", done);
            return;
        }
        if (action === "cursor") {
            root.readCursor(done);
            return;
        }
        done({ error: "unknown use_computer action: " + action });
    }

    function captureScreenshot(args, cb) {
        const win = root.findWindow(args);
        const raiseWindow = args.raise_window !== false && args.raise_window !== "false";
        if (win && raiseWindow) {
            root._pendingCapture = { args: args, cb: cb, win: win };
            root.focusWindow({ address: win.address }, true, result => {
                if (result && result.error) {
                    cb(result);
                    return;
                }
                raiseTimer.restart();
            });
            return;
        }
        root._runCapture(args, win, cb);
    }

    function _runCapture(args, win, cb) {
        const screens = root.screenList();
        const fullScreen = !!args.full_screen;
        let mon = root.pickScreen(args.monitor || args.target || "");
        if (win && !fullScreen) {
            const at = win.at || [0, 0];
            for (let i = 0; i < screens.length; i++) {
                const s = screens[i];
                if (at[0] >= s.origin_x && at[0] < s.origin_x + s.width && at[1] >= s.origin_y && at[1] < s.origin_y + s.height) {
                    mon = s;
                    break;
                }
            }
        }
        if (!mon && !fullScreen) {
            cb({ error: "no monitor available for screenshot" });
            return;
        }
        const opts = {
            includeCursor: args.include_cursor !== false && args.include_cursor !== "false",
            fullScreen: fullScreen,
            monitor: fullScreen ? "" : mon.name,
            origin_x: fullScreen ? 0 : mon.origin_x,
            origin_y: fullScreen ? 0 : mon.origin_y,
            monitor_scale: fullScreen ? 1 : (mon.scale || 1),
            window_title: win ? (win.title || "") : ""
        };
        if (win && !fullScreen) {
            const scale = mon.scale || 1;
            const at = win.at || [0, 0];
            const size = win.size || [0, 0];
            let cropX = Math.round((at[0] - mon.origin_x) * scale);
            let cropY = Math.round((at[1] - mon.origin_y) * scale);
            let cropW = Math.round(size[0] * scale);
            let cropH = Math.round(size[1] * scale);
            const physW = Math.round(mon.width * scale);
            const physH = Math.round(mon.height * scale);
            const off = cropX + cropW <= 0 || cropY + cropH <= 0 || cropX >= physW || cropY >= physH;
            opts.window_off_screen = off;
            if (!off) {
                cropX = Math.max(0, cropX);
                cropY = Math.max(0, cropY);
                cropW = Math.min(cropW, physW - cropX);
                cropH = Math.min(cropH, physH - cropY);
                opts.cropX = cropX;
                opts.cropY = cropY;
                opts.cropW = cropW;
                opts.cropH = cropH;
                opts.cropped_to_window = true;
            }
        }
        root._actionCb = cb;
        if (!root.noscreenshare) {
            root.hudHiddenForCapture = true;
            root._pendingCapture = { opts: opts, cb: cb };
            hideTimer.restart();
            return;
        }
        Screenshot.captureSilent(opts);
    }

    function focusWindow(args, warp, cb) {
        const win = root.findWindow(args);
        if (!win || !win.address) {
            cb({ error: "window not found" });
            return;
        }
        root._focusAddress = win.address;
        root._focusWarp = !!warp;
        root._actionCb = cb;
        root._focusTries = 0;
        if (!warp)
            Quickshell.execDetached(["hyprctl", "keyword", "cursor:no_warps", "true"]);
        AxctlService.dispatch("focuswindow address:" + win.address);
        focusTimer.restart();
    }

    function moveOrResize(args, kind, cb) {
        const win = root.findWindow(args);
        if (!win || !win.address) {
            cb({ error: "window not found" });
            return;
        }
        if (kind === "move") {
            const x = Math.round(Number(args.x || 0));
            const y = Math.round(Number(args.y || 0));
            AxctlService.dispatch("movewindowpixel exact " + x + " " + y + ", address:" + win.address);
        } else {
            const w = Math.round(Number(args.width || win.size[0] || 0));
            const h = Math.round(Number(args.height || win.size[1] || 0));
            AxctlService.dispatch("resizewindowpixel exact " + w + " " + h + ", address:" + win.address);
        }
        cb({ ok: true, address: win.address });
    }

    function readCursor(cb) {
        root._actionCb = cb;
        cursorProc.running = true;
    }

    function refreshPids() {
        pidProc.running = true;
    }

    Timer {
        id: hideTimer
        interval: 40
        repeat: false
        onTriggered: {
            const pending = root._pendingCapture;
            root._pendingCapture = null;
            if (pending && pending.opts)
                Screenshot.captureSilent(pending.opts);
        }
    }

    Timer {
        id: raiseTimer
        interval: 250
        repeat: false
        onTriggered: {
            const pending = root._pendingCapture;
            root._pendingCapture = null;
            if (pending)
                root._runCapture(pending.args, pending.win, pending.cb);
        }
    }

    Timer {
        id: focusTimer
        interval: 50
        repeat: true
        onTriggered: {
            root._focusTries += 1;
            const clients = AxctlService.clients.values || [];
            const match = clients.find(c => c.address === root._focusAddress && c.is_focused);
            if (match || root._focusTries >= 20) {
                focusTimer.stop();
                if (!root._focusWarp)
                    Quickshell.execDetached(["hyprctl", "keyword", "cursor:no_warps", "false"]);
                const cb = root._actionCb;
                root._actionCb = null;
                if (cb)
                    cb({ ok: true, address: root._focusAddress, verified: !!match });
            }
        }
    }

    Process {
        id: ydoProc
        running: false
    }

    Process {
        id: cursorProc
        command: ["axctl", "system", "get-cursor-position"]
        stdout: StdioCollector {}
        onExited: () => {
            const cb = root._actionCb;
            root._actionCb = null;
            const text = ((cursorProc.stdout && cursorProc.stdout.text) || "").trim();
            const parts = text.split(",");
            const x = parseInt(parts[0], 10);
            const y = parseInt(parts[1], 10);
            if (cb)
                cb({ x: isNaN(x) ? 0 : x, y: isNaN(y) ? 0 : y, raw: text });
        }
    }

    Process {
        id: pidProc
        command: ["hyprctl", "clients", "-j"]
        stdout: StdioCollector {}
        onExited: exitCode => {
            if (exitCode !== 0)
                return;
            try {
                const clients = JSON.parse(pidProc.stdout.text || "[]");
                const map = {};
                for (let i = 0; i < clients.length; i++) {
                    const item = clients[i] || {};
                    const addr = String(item.address || "");
                    if (addr)
                        map[addr] = item.pid || 0;
                }
                Qt.callLater(() => {
                    root.pidByAddress = map;
                });
            } catch (e) {
            }
        }
    }

    Connections {
        target: Screenshot
        function onSilentCaptureReady(result) {
            if (root.hudHiddenForCapture)
                root.hudHiddenForCapture = false;
            const cb = root._actionCb;
            root._actionCb = null;
            if (cb)
                cb(result);
        }
    }

    Connections {
        target: Visibilities
        function onCurrentActiveModuleChanged() {
            if (root.sessionActive && Visibilities.currentActiveModule !== "assistant")
                root.end({ restoreSpotlight: false });
        }
    }

    Connections {
        target: GlobalStates
        function onLockscreenVisibleChanged() {
            if (GlobalStates.lockscreenVisible && root.sessionActive)
                root.end({ restoreSpotlight: false });
        }
    }

    Connections {
        target: Config.ai.executionProfile
        function onComputerUseChanged() {
            if (String(Config.ai.executionProfile.computerUse) === "Never" && root.sessionActive)
                root.end({ restoreSpotlight: true });
        }
    }
}
