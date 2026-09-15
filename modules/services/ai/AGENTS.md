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

Write (execution-profile gated): set_volume, set_brightness, toggle_mute, notify, toggle_night_light, lock, screenshot, focus_window, copy_to_clipboard.

Computer use (execution-profile `computerUse`, default Never): `computer_use_session` (begin/end/gate) and `use_computer` (screenshot/focus/move_window/resize_window/cursor). After the session grant, routine actions auto-run; pay/send/purchase (`critical`) still ask. Python never talks to Quickshell; grim and HUD live in `ComputerUse.qml` / `Screenshot.captureSilent`. `gate` does not start a session — if the user already stopped computer use, further actions error instead of grabbing the desktop again. The QML session ends on agent `done` / error / cancel.

Return JSON via `{ cmd: "native_result", call_id, result }` on the agent stdin.
