# AGENTS.md — modules/services/ai/

## OVERVIEW
Python-backed AI agent glue. `Ai.qml` is the facade; executors live in `scripts/ai/`. Native desktop actions are handled here in QML so the Python process never talks to Quickshell APIs.

## STRUCTURE

| File | Role |
|------|------|
| `AiModel.qml` | Model descriptor (name, provider, endpoint) |
| `NativeToolBridge.qml` | Maps `native_request` events onto Audio, Brightness, Notifications, Axctl, ComputerUse, etc. |

Legacy `strategies/*.qml` curl clients are unused; HTTP is in `scripts/ai/providers/`.

## NATIVE TOOLS

Read: volume, brightness, battery, weather, media, wifi, clipboard, windows, notifications, notes.

Write (execution-profile gated): set_volume, set_brightness, toggle_mute, notify, toggle_night_light, lock, screenshot, focus_window, copy_to_clipboard. `focus_window` goes through `ComputerUse.focusWindow` (axctl `window focus` by address, verify `activewindow`, one retry, hard error).

Computer use (execution-profile `computerUse`, default Never): `computer_use_session` (begin/end/gate/inject_begin/inject_end/wait_begin/wait_end) and `use_computer` (screenshot/focus/move_window/resize_window/cursor/wait). After the session grant, routine actions auto-run; pay/send/purchase (`critical`) still ask. Computer use uses `Config.ai.computerUseModel` when that string is non-empty, otherwise the current Spotlight/session model (`lastAiModel`). It does not change the chat selection. Grant and screenshot-dependent actions error and end the session if the resolved model is known not to accept images (unknown IDs and OpenRouter `auto` fail open; no model fallback). Python never talks to Quickshell; grim and HUD live in `ComputerUse.qml` / `Screenshot.captureSilent`. Cross-workspace window targeting focuses by address (axctl `window focus`) and verifies the compositor active window before click/type/screenshot; one retry then a hard error, no hyprctl loops. `wait` notifies QML before sleeping so the HUD can show a countdown. `gate` does not start a session — if the user already stopped computer use, further actions error instead of grabbing the desktop again. The grant stays across assistant `done`; QML ends on Stop / lock / error / cancel / `end_computer_use`. Native `screenshot` during an active session is aliased to grim `use_computer action=screenshot`.

Return JSON via `{ cmd: "native_result", call_id, result }` on the agent stdin.
