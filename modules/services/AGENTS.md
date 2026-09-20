# SERVICES KNOWLEDGE BASE

## OVERVIEW
Backend singletons bridging Wayland protocols, CLI tools (nmcli, upower, wpctl, etc.), and AI providers to the QML UI layer. 30+ services following a "Reactive Singleton" pattern — internal state derived from async system calls, exposed as QML properties.

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| **Audio/Volume** | `Audio.qml` | PipeWire/PulseAudio via `wpctl`. Sink/source management |
| **Network/WiFi** | `NetworkService.qml` | `nmcli` wrapper. WiFi scanning, connection, status |
| **Battery/Power** | `Battery.qml` | UPower integration. Percentage, charging state, time remaining |
| **Bluetooth** | `BluetoothService.qml` | Device listing, connect/disconnect |
| **Brightness** | `Brightness.qml` | Per-monitor brightness via `brightnessctl` |
| **AI Assistant** | `Ai.qml` + `scripts/ai/` | Spotlight overlay agent. Python NDJSON loop, Warp-shaped tools, native bridge |
| **Computer use** | `ComputerUse.qml` + `scripts/ai/computer_use/` | Session HUD (output card auto-hides 2.5s after last assistant token, type-to-open steer, hide visuals for grim), silent grim, JPEG-space clicks, **teleport** Hyprland cursor (no eased targeting), physical mice/trackpads disabled via `hyprctl eval hl.device` while driving (never keyboard-named devices; re-enabled during approvalWait so Reject/Approve can be clicked, and while the grant is idle between turns), ydotool clicks, AT-SPI bus started if missing. Exclusive HUD/dashboard replay compositor binds (workspace switch). Cross-workspace targeting is one-step `focuswindow address:…` (axctl `window focus`) plus `activewindow` verify, one retry, then a hard error — never `workspace` then hope. `wait` is a native `wait_begin`/`wait_end` so the HUD can countdown. Session stays granted across turns until Stop / double-Esc / Super+A / lock / error / cancel / `end_computer_use` — not on agent `done`. `ambxst+ run cu-stop` and `cu-escape` are IPC failsafes. Uses `Config.ai.computerUseModel` when set, otherwise the current Spotlight model; refuses grant (and screenshot actions) if the resolved model is known not to accept images — error + end session, no model fallback. Chat's selected model is not changed. OpenRouter `auto` and unknown IDs fail open. |

| **Clipboard** | `ClipboardService.qml` | Persistent clipboard via `clipboard.db` + helper scripts. sqlite via argv (`_sqliteCmd`); aliases as hex blobs; restore via `clipboard_copy.sh` |
| **Media** | `MprisController.qml` | MPRIS D-Bus player control |
| **Notifications** | `Notifications.qml` | D-Bus notification server with persistence |
| **System Monitor** | `SystemResources.qml` | CPU, RAM, GPU, temps via Python script |
| **Compositor** | `AxctlService.qml` | Abstraction layer for compositor IPC (focus, dispatch). Spawns `axctl daemon` and restarts it with backoff if it exits (rebuild/socket races). |
| **Visibility** | `Visibilities.qml` | Per-screen UI visibility/layering orchestration |
| **State** | `StateService.qml` | JSON persistence for session state (tab positions, etc.) |
| **Focus** | `FocusGrabManager.qml` | Input focus coordination across overlays |
| **Desktop** | `DesktopService.qml` | Desktop icon grid positioning and management |
| **App Search** | `AppSearch.qml` | Application indexing for launcher |
| **Weather** | `WeatherService.qml` | Forecast, sunrise/sunset, day/night detection |
| **Keybinds** | `GlobalShortcuts.qml` | Compositor-level keybind management. FIFO via `scripts/ipc_pipe.sh` (`$XDG_RUNTIME_DIR` or `/run/user/$UID`, ownership fail-closed) |
| **Camera** | `CameraService.qml` | Camera enumeration + in-use privacy indicator (`camera_monitor.py`, long-running) |

## CONVENTIONS
- **Singleton pattern**: `pragma Singleton` + `Singleton { id: root }` root component.
- **System access**: Prefer `Quickshell.Io.Process` with `SplitParser` for line-by-line stdout handling.
- **Naming**: Properties in camelCase (`wifiEnabled`, `isCharging`). Methods: `update()` for polling, `toggleX()` for booleans. Signals: past-tense or action-based (`initDone`, `discard`).
- **Persistence**: `FileView` for direct JSON manipulation. Reference `Config` for global settings; keep service-specific state local.
- **Async safety**: `Qt.callLater()` when modifying lists/models inside process handlers.
- **Self-init**: Services handle own lifecycle via `Component.onCompleted: update()`.
- **Error handling**: Always provide safe fallback values (`available: device !== null`).

## ANTI-PATTERNS
- Polling without a timer guard (use `Timer` with configurable intervals).
- Modifying list models synchronously inside `Process.onStdout` handlers.
- Creating new services without registering them in `shell.qml` init sequence.
