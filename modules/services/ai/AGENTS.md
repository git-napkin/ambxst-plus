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

Write (execution-profile gated): set_volume, set_brightness, toggle_mute, notify, toggle_night_light, lock, screenshot, focus_window, copy_to_clipboard, load_preset.

Computer use (execution-profile `computerUse`, default Never): `computer_use_session` (begin/end/gate) and `use_computer` (screenshot/focus/move_window/resize_window/cursor). Python never talks to Quickshell; grim and HUD live in `ComputerUse.qml` / `Screenshot.captureSilent`.

Return JSON via `{ cmd: "native_result", call_id, result }` on the agent stdin.
