import QtQuick
import Quickshell.Io
import qs.config
import qs.modules.globals
import "../../config/KeybindActions.js" as KeybindActions

QtObject {
    id: root

    property int _batchRetries: 0

    property Process compositorProcess: Process {
        stdout: StdioCollector {
            onStreamFinished: {
                const out = text.trim();
                if (out.length > 0) console.log("CompositorKeybinds: axctl stdout:", out);
            }
        }
        stderr: StdioCollector {
            onStreamFinished: {
                const err = text.trim();
                if (err.length > 0) console.warn("CompositorKeybinds: axctl stderr:", err);
            }
        }
        onExited: (code, status) => {
            if (code !== 0 || status !== 0) {
                // Bounded retry — covers Hyprland restart races without
                // spinning forever if axctl is permanently broken.
                if (_batchRetries < 3) {
                    _batchRetries++;
                    console.warn("CompositorKeybinds: keybinds-batch failed code=" + code + " status=" + status + " – retry " + _batchRetries + "/3 in 500ms");
                    if (!retryTimer.running) retryTimer.restart();
                } else {
                    console.warn("CompositorKeybinds: keybinds-batch failed " + _batchRetries + " times, giving up until next trigger");
                }
            } else {
                _batchRetries = 0;
                console.log("CompositorKeybinds: keybinds-batch succeeded");
            }
        }
    }

    property Timer retryTimer: Timer {
        interval: 500
        repeat: false
        onTriggered: applyKeybindsInternal()
    }

    property var previousAmbxstPlusBinds: ({})
    property var previousCustomBinds: []
    property bool hasPreviousBinds: false

    property Timer applyTimer: Timer {
        interval: 100
        repeat: false
        onTriggered: applyKeybindsInternal()
    }

    function applyKeybinds() {
        applyTimer.restart();
    }

    // Helper function to check if an action is compatible with the current layout
    function isActionCompatibleWithLayout(action) {
        // If no layouts specified or empty array, action works in all layouts
        if (!action.layouts || action.layouts.length === 0)
            return true;

        // Check if current layout is in the allowed list
        const currentLayout = GlobalStates.compositorLayout;
        return action.layouts.indexOf(currentLayout) !== -1;
    }

    function cloneKeybind(keybind) {
        return {
            modifiers: keybind.modifiers ? keybind.modifiers.slice() : [],
            key: keybind.key || ""
        };
    }

    function storePreviousBinds() {
        if (!Config.keybindsLoader.loaded)
            return;

        const ambxstPlus = Config.keybindsLoader.adapter.ambxstPlus;

        // Store ambxst+ core keybinds
        previousAmbxstPlusBinds = {
            ambxstPlus: {
                launcher: cloneKeybind(ambxstPlus.launcher),
                dashboard: cloneKeybind(ambxstPlus.dashboard),
                assistant: cloneKeybind(ambxstPlus.assistant),
                clipboard: cloneKeybind(ambxstPlus.clipboard),
                emoji: cloneKeybind(ambxstPlus.emoji),
                notes: cloneKeybind(ambxstPlus.notes),
                tmux: cloneKeybind(ambxstPlus.tmux),
                wallpapers: cloneKeybind(ambxstPlus.wallpapers)
            },
            system: {
                overview: cloneKeybind(ambxstPlus.system.overview),
                powermenu: cloneKeybind(ambxstPlus.system.powermenu),
                config: cloneKeybind(ambxstPlus.system.config),
                lockscreen: cloneKeybind(ambxstPlus.system.lockscreen),
                tools: cloneKeybind(ambxstPlus.system.tools),
                screenshot: cloneKeybind(ambxstPlus.system.screenshot),
                screenrecord: cloneKeybind(ambxstPlus.system.screenrecord),
                lens: cloneKeybind(ambxstPlus.system.lens),
                reload: ambxstPlus.system.reload ? cloneKeybind(ambxstPlus.system.reload) : null,
                quit: ambxstPlus.system.quit ? cloneKeybind(ambxstPlus.system.quit) : null
            }
        };

        // Store custom keybinds
        const customBinds = Config.keybindsLoader.adapter.custom;
        previousCustomBinds = [];
        if (customBinds && customBinds.length > 0) {
            for (let i = 0; i < customBinds.length; i++) {
                const bind = customBinds[i];
                if (bind.keys) {
                    let keys = [];
                    for (let k = 0; k < bind.keys.length; k++) {
                        keys.push(cloneKeybind(bind.keys[k]));
                    }
                    previousCustomBinds.push({
                        keys: keys
                    });
                } else {
                    previousCustomBinds.push(cloneKeybind(bind));
                }
            }
        }

        hasPreviousBinds = true;
    }

    // Build an unbind target object (modifiers + key only). Bare modkeys are
    // expanded to both SUPER+key and bare key so stale forms are cleared.
    function makeUnbindTarget(keybind) {
        return KeybindActions.expandUnbindTargets(keybind || {});
    }

    function pushUnbind(payload, keybind) {
        if (!keybind)
            return;
        const targets = makeUnbindTarget(keybind);
        for (let i = 0; i < targets.length; i++)
            payload.unbinds.push(targets[i]);
    }

    // Build a structured bind object from a core keybind (has all fields inline).
    function resolveBindAction(action, fallback) {
        const resolved = KeybindActions.resolveAction(action || fallback);
        if (!resolved) return null;
        return {
            dispatcher: resolved.dispatcher || "",
            argument: resolved.argument || "",
            flags: resolved.flags || ""
        };
    }

    function makeBindFromCore(keybind) {
        const resolved = resolveBindAction(keybind.action, keybind);
        if (!resolved) return [];
        return KeybindActions.makeExpandedBinds(
            keybind.modifiers || [],
            keybind.key || "",
            resolved.dispatcher,
            resolved.argument,
            resolved.flags
        );
    }

    // Build a structured bind object from a key + action pair (custom keybinds).
    function makeBindFromKeyAction(keyObj, action) {
        const resolved = resolveBindAction(action, action);
        if (!resolved) return [];
        return KeybindActions.makeExpandedBinds(
            keyObj.modifiers || [],
            keyObj.key || "",
            resolved.dispatcher,
            resolved.argument,
            resolved.flags
        );
    }

    function applyKeybindsInternal() {
        // Ensure adapter is loaded.
        if (!Config.keybindsLoader.loaded) {
            console.log("CompositorKeybinds: Esperando que se cargue el adapter...");
            return;
        }

        // Wait for layout to be ready.
        if (!GlobalStates.compositorLayoutReady) {
            console.log("CompositorKeybinds: Esperando que se detecte el layout de AxctlService...");
            return;
        }

        console.log("CompositorKeybinds: Aplicando keybindings (layout: " + GlobalStates.compositorLayout + ")...");

        // Build structured payload.
        let payload = { binds: [], unbinds: [] };

        // First, unbind previous keybinds if we have them stored
        if (hasPreviousBinds) {
            // Unbind previous ambxst+ core keybinds
            if (previousAmbxstPlusBinds.ambxstPlus) {
                pushUnbind(payload, previousAmbxstPlusBinds.ambxstPlus.launcher);
                pushUnbind(payload, previousAmbxstPlusBinds.ambxstPlus.dashboard);
                pushUnbind(payload, previousAmbxstPlusBinds.ambxstPlus.assistant);
                pushUnbind(payload, previousAmbxstPlusBinds.ambxstPlus.clipboard);
                pushUnbind(payload, previousAmbxstPlusBinds.ambxstPlus.emoji);
                pushUnbind(payload, previousAmbxstPlusBinds.ambxstPlus.notes);
                pushUnbind(payload, previousAmbxstPlusBinds.ambxstPlus.tmux);
                pushUnbind(payload, previousAmbxstPlusBinds.ambxstPlus.wallpapers);
            }

            // Unbind previous ambxst+ system keybinds
            if (previousAmbxstPlusBinds.system) {
                pushUnbind(payload, previousAmbxstPlusBinds.system.overview);
                pushUnbind(payload, previousAmbxstPlusBinds.system.powermenu);
                pushUnbind(payload, previousAmbxstPlusBinds.system.config);
                pushUnbind(payload, previousAmbxstPlusBinds.system.lockscreen);
                pushUnbind(payload, previousAmbxstPlusBinds.system.tools);
                pushUnbind(payload, previousAmbxstPlusBinds.system.screenshot);
                pushUnbind(payload, previousAmbxstPlusBinds.system.screenrecord);
                pushUnbind(payload, previousAmbxstPlusBinds.system.lens);
                if (previousAmbxstPlusBinds.system.reload) pushUnbind(payload, previousAmbxstPlusBinds.system.reload);
                if (previousAmbxstPlusBinds.system.quit) pushUnbind(payload, previousAmbxstPlusBinds.system.quit);
            }

            // Unbind previous custom keybinds
            for (let i = 0; i < previousCustomBinds.length; i++) {
                const prev = previousCustomBinds[i];
                if (prev.keys) {
                    for (let k = 0; k < prev.keys.length; k++) {
                        pushUnbind(payload, prev.keys[k]);
                    }
                } else {
                    pushUnbind(payload, prev);
                }
            }
        }

        // Process core keybinds.
        const ambxstPlus = Config.keybindsLoader.adapter.ambxstPlus;

        // Unbind current core keybinds (ensures clean state before rebinding)
        pushUnbind(payload, ambxstPlus.launcher);
        pushUnbind(payload, ambxstPlus.dashboard);
        pushUnbind(payload, ambxstPlus.assistant);
        pushUnbind(payload, ambxstPlus.clipboard);
        pushUnbind(payload, ambxstPlus.emoji);
        pushUnbind(payload, ambxstPlus.notes);
        pushUnbind(payload, ambxstPlus.tmux);
        pushUnbind(payload, ambxstPlus.wallpapers);

        // Bind current core keybinds
        [ambxstPlus.launcher, ambxstPlus.dashboard, ambxstPlus.assistant, ambxstPlus.clipboard, ambxstPlus.emoji, ambxstPlus.notes, ambxstPlus.tmux, ambxstPlus.wallpapers].forEach(bind => {
            payload.binds.push(...makeBindFromCore(bind));
        });

        // System keybinds
        const system = ambxstPlus.system;

        // Unbind current system keybinds
        pushUnbind(payload, system.overview);
        pushUnbind(payload, system.powermenu);
        pushUnbind(payload, system.config);
        pushUnbind(payload, system.lockscreen);
        pushUnbind(payload, system.tools);
        pushUnbind(payload, system.screenshot);
        pushUnbind(payload, system.screenrecord);
        pushUnbind(payload, system.lens);
        if (system.reload) pushUnbind(payload, system.reload);
        if (system.quit) pushUnbind(payload, system.quit);

        // Bind current system keybinds
        [system.overview, system.powermenu, system.config, system.lockscreen, system.tools, system.screenshot, system.screenrecord, system.lens, system.reload, system.quit].forEach(bind => {
            if (!bind) return;
            payload.binds.push(...makeBindFromCore(bind));
        });

        // Process custom keybinds (keys[] and actions[] format).
        const customBinds = Config.keybindsLoader.adapter.custom;
        if (customBinds && customBinds.length > 0) {
            for (let i = 0; i < customBinds.length; i++) {
                const bind = customBinds[i];

                // Check if bind has the new format
                if (bind.keys && bind.actions) {
                    // Unbind all keys first (always unbind regardless of layout)
                    for (let k = 0; k < bind.keys.length; k++) {
                        pushUnbind(payload, bind.keys[k]);
                    }

                    // Only create binds if enabled
                    if (bind.enabled !== false) {
                        // For each key, bind only compatible actions
                        for (let k = 0; k < bind.keys.length; k++) {
                            for (let a = 0; a < bind.actions.length; a++) {
                                const action = bind.actions[a];
                                // Check if this action is compatible with the current layout
                                if (isActionCompatibleWithLayout(action)) {
                                    payload.binds.push(...makeBindFromKeyAction(bind.keys[k], action));
                                }
                            }
                        }
                    }
                } else {
                    // Fallback for old format (shouldn't happen after normalization)
                    pushUnbind(payload, bind);
                    if (bind.enabled !== false) {
                        payload.binds.push(...makeBindFromCore(bind));
                    }
                }
            }
        }

        storePreviousBinds();

        // Send structured payload via axctl keybinds-batch.
        console.log("CompositorKeybinds: Enviando keybinds-batch (" + payload.unbinds.length + " unbinds, " + payload.binds.length + " binds)");
        compositorProcess.command = ["axctl", "config", "keybinds-batch", JSON.stringify(payload)];
        compositorProcess.running = true;
    }

    property Connections configConnections: Connections {
        target: Config.keybindsLoader
        function onFileChanged() {
            applyKeybinds();
        }
        function onLoaded() {
            applyKeybinds();
        }
        function onAdapterUpdated() {
            applyKeybinds();
        }
    }

    // Re-apply keybinds when layout changes
    property Connections globalStatesConnections: Connections {
        target: GlobalStates
        function onCompositorLayoutChanged() {
            console.log("CompositorKeybinds: Layout changed to " + GlobalStates.compositorLayout + ", reapplying keybindings...");
            applyKeybinds();
        }
        function onCompositorLayoutReadyChanged() {
            if (GlobalStates.compositorLayoutReady) {
                applyKeybinds();
            }
        }
    }

    // Hyprland config reloads wipe runtime-applied binds; the axctl daemon
    // regenerates config on toml changes and broadcasts Event.ConfigReloaded.
    property Connections compositorConnections: Connections {
        target: AxctlService
        function onRawEvent(event) {
            if (event.name === "configreloaded") {
                console.log("CompositorKeybinds: Detectado configreloaded, reaplicando keybindings...");
                applyKeybinds();
            }
        }
    }

    Component.onCompleted: {
        // Apply immediately if loader is ready.
        if (Config.keybindsLoader.loaded) {
            applyKeybinds();
        }
    }
}
