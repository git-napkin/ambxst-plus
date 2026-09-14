import QtQuick
import Quickshell
import Quickshell.Io
import qs.modules.services
import qs.modules.globals
import qs.config

QtObject {
    id: root

    signal resultReady(string callId, var result)

    property string pendingCallId: ""
    property string pendingName: ""

    function handle(name, args, callId) {
        pendingCallId = callId || "";
        pendingName = name || "";
        const a = args || {};
        if (name === "get_notes") {
            notesProc.callId = callId;
            notesProc.running = true;
            return;
        }
        if (name === "copy_to_clipboard") {
            copyProc.text = a.text || "";
            copyProc.callId = callId;
            copyProc.command = ["wl-copy", copyProc.text];
            copyProc.running = true;
            return;
        }
        if (name === "screenshot") {
            Screenshot.initialize();
            GlobalStates.screenshotToolVisible = true;
            Qt.callLater(() => root.resultReady(callId, { ok: true, opened: true }));
            return;
        }
        if (name === "computer_use_session") {
            Qt.callLater(() => root.resultReady(callId, ComputerUse.handleSession(a)));
            return;
        }
        if (name === "use_computer") {
            ComputerUse.handleAction(a, result => root.resultReady(callId, result || {}));
            return;
        }
        let result = {};
        try {
            result = dispatch(name, a);
        } catch (e) {
            result = { error: String(e) };
        }
        root.resultReady(callId, result);
    }

    function dispatch(name, args) {
        switch (name) {
        case "get_volume":
            return {
                volume: Audio.currentSlider(),
                muted: !!(Audio.sink && Audio.sink.audio && Audio.sink.audio.muted)
            };
        case "set_volume":
            Audio.setVolume(Number(args.value ?? args.volume ?? 0));
            return { ok: true, volume: Audio.currentSlider() };
        case "toggle_mute":
            Audio.toggleMute();
            return { ok: true, muted: !!(Audio.sink && Audio.sink.audio && Audio.sink.audio.muted) };
        case "get_brightness":
            {
                const mons = [];
                for (let i = 0; i < Brightness.monitors.length; i++) {
                    const m = Brightness.monitors[i];
                    mons.push({
                        name: m.screen ? m.screen.name : String(i),
                        brightness: m.brightness
                    });
                }
                return { monitors: mons };
            }
        case "set_brightness":
            {
                const value = Number(args.value ?? args.brightness ?? 0.5);
                const targetName = args.screen || args.monitor || "";
                for (let i = 0; i < Brightness.monitors.length; i++) {
                    const m = Brightness.monitors[i];
                    if (!targetName || (m.screen && m.screen.name === targetName))
                        m.setBrightness(value);
                }
                return { ok: true };
            }
        case "get_battery":
            return {
                available: Battery.available,
                percentage: Battery.percentage,
                charging: Battery.isCharging,
                timeToEmpty: Battery.timeToEmpty
            };
        case "get_weather":
            return {
                description: WeatherService.weatherDescription,
                temp: WeatherService.currentTemp,
                available: WeatherService.dataAvailable
            };
        case "get_media":
            {
                const p = MprisController.activePlayer;
                return p ? {
                    title: p.trackTitle || "",
                    artist: (p.trackArtists || []).join(", "),
                    playing: !!p.isPlaying,
                    identity: p.identity || ""
                } : { playing: false };
            }
        case "get_wifi":
            return {
                enabled: NetworkService.wifiEnabled,
                status: NetworkService.wifiStatus,
                ssid: NetworkService.active ? NetworkService.active.ssid : ""
            };
        case "get_clipboard":
            {
                const items = (ClipboardService.items || []).slice(0, 10).map(it => ({
                    preview: it.preview || "",
                    mime: it.mime_type || it.mime || ""
                }));
                return { items: items };
            }
        case "get_windows":
            return { windows: ComputerUse.windowsPayload() };
        case "get_notifications":
            {
                const list = (Notifications.list || []).slice(0, 15).map(n => ({
                    app: n.appName,
                    summary: n.summary,
                    body: n.body
                }));
                return { notifications: list };
            }
        case "notify":
            Notifications.notifyInternal({
                summary: args.summary || args.title || "Ambxst[+]",
                body: args.body || args.message || "",
                appName: "ambxst+"
            });
            return { ok: true };
        case "toggle_night_light":
            NightLightService.toggle();
            return { ok: true, active: NightLightService.active };
        case "lock":
            LockscreenService.lock();
            return { ok: true };
        case "focus_window":
            if (args.address)
                AxctlService.dispatch("focuswindow address:" + args.address);
            return { ok: true };
        case "load_preset":
            if (args.name)
                PresetsService.loadPreset(args.name);
            return { ok: true, name: args.name || "" };
        default:
            return { error: "unknown native tool: " + name };
        }
    }

    property Process copyProc: Process {
        id: copyProc
        property string callId: ""
        property string text: ""
        onExited: () => root.resultReady(copyProc.callId, { ok: true })
    }

    property Process notesProc: Process {
        id: notesProc
        property string callId: ""
        command: ["python3", "-c", "import os,json; p=os.path.expanduser((os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share'))+'/ambxst+-notes/notes'); print(json.dumps(sorted(os.listdir(p))[:30] if os.path.isdir(p) else []))"]
        stdout: StdioCollector { id: notesOut }
        onExited: () => {
            let names = [];
            try { names = JSON.parse(notesOut.text); } catch (e) { names = []; }
            root.resultReady(notesProc.callId, { notes: names });
        }
    }
}
