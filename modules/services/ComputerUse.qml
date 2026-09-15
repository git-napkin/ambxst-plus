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
    property string ydotoolSocket: ""
    property string lastAction: ""
    property string taskSummary: ""
    property string hudScreen: ""
    property real hudWidth: 360
    property int workUserIndex: -1
    property real sessionStartedAt: 0
    property bool injectingInput: false
    property bool steerOpen: false
    property bool escArmed: false
    property var _disabledMice: []
    property string _devicesIntent: ""

    signal sessionFinished(var userIndex, var durationMs)
    signal stopRequested
    signal rejectRequested

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
        const pid = c.pid || 0;
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
        const focusedAddr = AxctlService.focusedClient ? AxctlService.focusedClient.address : "";
        return clients.map(c => {
            const payload = root.windowPayload(c);
            if (focusedAddr && payload && payload.address === focusedAddr)
                payload.focused = true;
            return payload;
        });
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
            ydotool_socket: root.ydotoolSocket,
            screens: root.screenList(),
            focused_window: focused,
            windows: root.windowsPayload()
        };
    }

    function applyNoscreenshare() {
        Quickshell.execDetached(["hyprctl", "keyword", "layerrule", "no_screen_share,ambxst\\+:computer-use"]);
        root.noscreenshare = false;
    }

    function ensureYdotoold() {
        if (root.ydotoolStarted || ydoProc.running || ydoProbeProc.running)
            return;
        ydoProbeProc.running = true;
    }

    function ensureAtSpi() {
        if (atspiProc.running)
            return;
        atspiProc.command = ["sh", "-c", "for p in at-spi-bus-launcher /usr/libexec/at-spi-bus-launcher /usr/lib/at-spi-bus-launcher /usr/lib/at-spi2-core/at-spi-bus-launcher; do if command -v \"$p\" >/dev/null 2>&1; then exec \"$(command -v \"$p\")\" --launch-immediately; fi; if [ -x \"$p\" ]; then exec \"$p\" --launch-immediately; fi; done; exit 1"];
        atspiProc.running = true;
    }

    function luaQuote(value) {
        return '"' + String(value || "").replace(/\\/g, "\\\\").replace(/"/g, '\\"') + '"';
    }

    function setPointerDeviceEnabled(name, on) {
        const n = String(name || "").trim();
        if (!n)
            return;
        Quickshell.execDetached(["hyprctl", "eval", "hl.device({ name = " + root.luaQuote(n) + ", enabled = " + (on ? "true" : "false") + " })"]);
    }

    function formatWorkedDuration(ms) {
        const n = Math.max(0, Number(ms) || 0);
        if (n < 60000)
            return Math.max(1, Math.round(n / 1000)) + "s";
        if (n < 3600000)
            return Math.max(1, Math.round(n / 60000)) + "m";
        return Math.max(1, Math.round(n / 3600000)) + "h";
    }

    function begin(summary) {
        if (GlobalStates.lockscreenVisible)
            return Object.assign({ error: "computer use is blocked while the session is locked" }, root.sessionSnapshot());
        if (!root.sessionActive)
            root.sessionStartedAt = Date.now();
        root.taskSummary = summary || "";
        root.lastAction = "session started";
        root.userHasControl = false;
        root.hudCollapsed = false;
        root.hudHiddenForCapture = false;
        root.composerFocused = false;
        root.hudScreen = Visibilities.lastFocusedScreen || (root.pickScreen("") ? root.pickScreen("").name : "");
        root.applyNoscreenshare();
        root.ensureYdotoold();
        root.ensureAtSpi();
        root.injectingInput = false;
        root.steerOpen = false;
        root.escArmed = false;
        if (!root.sessionActive)
            root.lockPointer();
        root.sessionState = "agentDriving";
        if (Visibilities.currentActiveModule !== "assistant")
            Visibilities.setActiveModule("assistant");
        return root.sessionSnapshot();
    }

    function end(opts) {
        const restore = !opts || opts.restoreSpotlight !== false;
        const wasActive = root.sessionActive;
        const userIndex = root.workUserIndex;
        const durationMs = root.sessionStartedAt ? (Date.now() - root.sessionStartedAt) : 0;
        root.sessionState = "idle";
        root.userHasControl = false;
        root.composerFocused = false;
        root.hudHiddenForCapture = false;
        root.hudCollapsed = false;
        root.lastAction = "";
        root.taskSummary = "";
        root.workUserIndex = -1;
        root.sessionStartedAt = 0;
        root.injectingInput = false;
        root.steerOpen = false;
        root.escArmed = false;
        injectWatchdog.stop();
        captureWatchdog.stop();
        escArmTimer.stop();
        root.unlockPointer();
        if (restore && Visibilities.currentActiveModule !== "assistant")
            Visibilities.setActiveModule("assistant");
        if (wasActive)
            root.sessionFinished(userIndex, durationMs);
    }

    function stop() {
        root.end({ restoreSpotlight: true });
    }

    function takeControl() {
        if (!root.sessionActive)
            return;
        root.userHasControl = true;
        root.composerFocused = false;
        root.steerOpen = false;
        root.injectingInput = false;
        root.sessionState = "userControl";
        root.lastAction = "user has control";
        root.unlockPointer();
    }

    function handBack() {
        if (!root.sessionActive)
            return;
        root.userHasControl = false;
        root.sessionState = "agentDriving";
        root.lastAction = "agent driving";
        root.lockPointer();
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

    function armEscExit() {
        root.escArmed = true;
        escArmTimer.restart();
    }

    function handleEscape() {
        if (!root.sessionActive || root.userHasControl)
            return;
        if (root.sessionState === "approvalWait") {
            root.rejectRequested();
            return;
        }
        if (root.steerOpen) {
            root.steerOpen = false;
            root.composerFocused = false;
            root.armEscExit();
            return;
        }
        if (root.escArmed) {
            root.escArmed = false;
            escArmTimer.stop();
            root.stopRequested();
            return;
        }
        root.armEscExit();
    }

    function gate(action, summary) {
        if (GlobalStates.lockscreenVisible)
            return { locked: true, error: "computer use is blocked while the session is locked" };
        if (!root.sessionActive)
            return { error: "computer use session is not active" };
        if (summary)
            root.lastAction = String(summary);
        else if (action)
            root.lastAction = String(action);
        return {
            locked: false,
            user_control: root.userHasControl,
            session_state: root.sessionState,
            composer_focused: root.composerFocused,
            steer_open: root.steerOpen
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
        if (op === "inject_begin") {
            root.injectingInput = true;
            injectWatchdog.restart();
            return { ok: true };
        }
        if (op === "inject_end") {
            root.injectingInput = false;
            injectWatchdog.stop();
            return { ok: true };
        }
        return { error: "unknown computer_use_session op" };
    }

    function lockPointer() {
        if (root.userHasControl)
            return;
        root._devicesIntent = "lock";
        root.restartDevicesProc();
    }

    function unlockPointer() {
        root._devicesIntent = "unlock";
        const names = root._disabledMice || [];
        for (let i = 0; i < names.length; i++)
            root.setPointerDeviceEnabled(names[i], true);
        root.persistDisabledMice([]);
        if (devicesProc.running)
            devicesProc.running = false;
    }

    function recoverPointers() {
        if (!recoverProc.running)
            recoverProc.running = true;
    }

    function persistDisabledMice(names) {
        root._disabledMice = names || [];
        const path = (Quickshell.env("XDG_RUNTIME_DIR") || "/tmp") + "/ambxst+_cu_pointers";
        if (!root._disabledMice.length) {
            Quickshell.execDetached(["rm", "-f", path]);
            return;
        }
        Quickshell.execDetached(["sh", "-c", "umask 077; printf %s " + root.shellQuote(root._disabledMice.join("\n") + "\n") + " > " + root.shellQuote(path)]);
    }

    function shellQuote(value) {
        return "'" + String(value || "").replace(/'/g, "'\\''") + "'";
    }

    function restartDevicesProc() {
        if (devicesProc.running)
            devicesProc.running = false;
        devicesProc.running = true;
    }

    function isVirtualPointerName(name) {
        return /ydotool|ydotoold|virtual|uinput/i.test(String(name || ""));
    }

    function isKeyboardDeviceName(name) {
        return /keyboard|\bkbd\b/.test(String(name || "").toLowerCase());
    }

    function sharesKeyboardName(name, keyboardNames) {
        const n = String(name || "").toLowerCase();
        if (!n)
            return false;
        const list = keyboardNames || [];
        for (let i = 0; i < list.length; i++) {
            const k = String(list[i] || "").toLowerCase();
            if (!k || root.isVirtualPointerName(k))
                continue;
            if (n === k || n.indexOf(k) === 0)
                return true;
        }
        return false;
    }

    function shouldDisablePointer(name, keyboardNames) {
        if (!name || root.isVirtualPointerName(name))
            return false;
        if (root.isKeyboardDeviceName(name))
            return false;
        if (root.sharesKeyboardName(name, keyboardNames))
            return false;
        return true;
    }

    function pointerNamesFromDevices(data) {
        const groups = [(data && data.mice) || [], (data && data.touchpads) || [], (data && data.touch) || [], (data && data.tablets) || []];
        const names = [];
        const seen = {};
        for (let g = 0; g < groups.length; g++) {
            const list = groups[g] || [];
            for (let i = 0; i < list.length; i++) {
                const name = String(list[i].name || "").trim();
                if (!name || seen[name] || root.isVirtualPointerName(name))
                    continue;
                seen[name] = true;
                names.push(name);
            }
        }
        return names;
    }

    function keyboardNamesFromDevices(data) {
        const list = (data && data.keyboards) || [];
        const names = [];
        for (let i = 0; i < list.length; i++) {
            const name = String(list[i].name || "").trim();
            if (name)
                names.push(name);
        }
        return names;
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
            monitor: fullScreen ? "" : (mon ? mon.name : ""),
            origin_x: fullScreen ? 0 : (mon ? mon.origin_x : 0),
            origin_y: fullScreen ? 0 : (mon ? mon.origin_y : 0),
            monitor_scale: mon ? (mon.scale || 1) : 1,
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
        root.hudHiddenForCapture = true;
        root._pendingCapture = { opts: opts, cb: cb };
        hideTimer.restart();
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

    function parseCursorText(text) {
        const raw = String(text || "").trim();
        if (raw.charAt(0) === "{") {
            try {
                const obj = JSON.parse(raw);
                return { x: Number(obj.x) || 0, y: Number(obj.y) || 0, raw: raw };
            } catch (e) {
            }
        }
        const parts = raw.split(",");
        const x = parseInt(parts[0], 10);
        const y = parseInt(parts[1], 10);
        return { x: isNaN(x) ? 0 : x, y: isNaN(y) ? 0 : y, raw: raw };
    }

    function readCursor(cb) {
        root._actionCb = cb;
        cursorProc.running = true;
    }

    Process {
        id: ydoProc
        running: false
    }

    Process {
        id: atspiProc
        running: false
    }

    Component.onCompleted: {
        root.recoverPointers();
        root.ensureAtSpi();
    }

    Process {
        id: devicesProc
        running: false
        command: ["hyprctl", "devices", "-j"]
        stdout: StdioCollector {}
        onExited: () => {
            Qt.callLater(() => {
                let data = {};
                try {
                    data = JSON.parse((devicesProc.stdout && devicesProc.stdout.text) || "{}");
                } catch (e) {
                    return;
                }
                const pointers = root.pointerNamesFromDevices(data);
                const keyboards = root.keyboardNamesFromDevices(data);
                if (root._devicesIntent === "lock") {
                    if (root.userHasControl || !root.sessionActive)
                        return;
                    const names = [];
                    for (let i = 0; i < pointers.length; i++) {
                        const name = pointers[i];
                        if (!root.shouldDisablePointer(name, keyboards))
                            continue;
                        names.push(name);
                        root.setPointerDeviceEnabled(name, false);
                    }
                    root.persistDisabledMice(names);
                    return;
                }
            });
        }
    }

    Process {
        id: recoverProc
        running: false
        command: ["sh", "-c", "p=\"${XDG_RUNTIME_DIR:-/tmp}/ambxst+_cu_pointers\"; if [ -f \"$p\" ]; then cat \"$p\"; rm -f \"$p\"; fi"]
        stdout: StdioCollector {}
        onExited: () => {
            Qt.callLater(() => {
                const text = (recoverProc.stdout && recoverProc.stdout.text) || "";
                const names = text.split("\n");
                for (let i = 0; i < names.length; i++) {
                    const name = String(names[i] || "").trim();
                    if (name)
                        root.setPointerDeviceEnabled(name, true);
                }
            });
        }
    }

    Process {
        id: ydoProbeProc
        running: false
        command: ["sh", "-c", "for s in \"${YDOTOOL_SOCKET}\" \"${XDG_RUNTIME_DIR:-/tmp}/.ydotool_socket\" \"${XDG_RUNTIME_DIR:-/tmp}/ydotoold/socket\" /run/ydotoold/socket /tmp/.ydotool_socket; do [ -S \"$s\" ] && printf '%s' \"$s\" && exit 0; done; exit 1"]
        stdout: StdioCollector {}
        onExited: code => {
            const found = ((ydoProbeProc.stdout && ydoProbeProc.stdout.text) || "").trim();
            if (code === 0 && found) {
                root.ydotoolSocket = found;
                root.ydotoolStarted = true;
                return;
            }
            const runtime = Quickshell.env("XDG_RUNTIME_DIR") || "/tmp";
            const sock = runtime + "/.ydotool_socket";
            root.ydotoolSocket = sock;
            ydoProc.command = ["ydotoold", "--socket", sock];
            ydoProc.running = true;
            ydoWaitTimer.tries = 0;
            ydoWaitTimer.restart();
        }
    }

    Timer {
        id: ydoWaitTimer
        interval: 120
        repeat: true
        property int tries: 0
        onTriggered: {
            tries += 1;
            ydoReadyProc.running = true;
            if (tries >= 25)
                ydoWaitTimer.stop();
        }
    }

    Process {
        id: ydoReadyProc
        running: false
        command: ["sh", "-c", "sock=\"" + root.ydotoolSocket + "\"; [ -n \"$sock\" ] && [ -S \"$sock\" ]"]
        onExited: code => {
            if (code === 0) {
                root.ydotoolStarted = true;
                ydoWaitTimer.stop();
            }
        }
    }

    Process {
        id: cursorProc
        command: ["axctl", "system", "get-cursor-position"]
        stdout: StdioCollector {}
        onExited: () => {
            const cb = root._actionCb;
            root._actionCb = null;
            const parsed = root.parseCursorText((cursorProc.stdout && cursorProc.stdout.text) || "");
            if (cb)
                cb(parsed);
        }
    }

    Timer {
        id: hideTimer
        interval: 50
        repeat: false
        onTriggered: {
            const pending = root._pendingCapture;
            root._pendingCapture = null;
            if (pending && pending.opts)
                Screenshot.captureSilent(pending.opts);
        }
    }

    Timer {
        id: injectWatchdog
        interval: 15000
        repeat: false
        onTriggered: root.injectingInput = false
    }

    Timer {
        id: captureWatchdog
        interval: 8000
        repeat: false
        onTriggered: root.hudHiddenForCapture = false
    }

    Timer {
        id: escArmTimer
        interval: 1500
        repeat: false
        onTriggered: root.escArmed = false
    }

    onHudHiddenForCaptureChanged: {
        if (root.hudHiddenForCapture)
            captureWatchdog.restart();
        else
            captureWatchdog.stop();
    }

    onInjectingInputChanged: {
        if (root.injectingInput)
            injectWatchdog.restart();
        else
            injectWatchdog.stop();
    }

    Timer {
        id: raiseTimer
        interval: 80
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
