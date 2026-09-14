# Computer use

Native desktop control for the AI panel. Policy default is **Never**. Advertise `request_computer_use` / `use_computer` only when Computer use is Always ask or Always allow.

## Start

1. Call `request_computer_use` with a short `task_summary`. Wait for the user to approve unless the profile is Always allow.
2. Call `use_computer` with `action=snapshot` before clicking. Snapshot does **not** raise windows. It returns a screenshot plus a compacted accessibility tree with `element_index` values.
3. Prefer `element_index` (or role/name selectors) over pixels. Pixel `x`/`y` are in the **image** the tool returned (`coordinate_width` × `coordinate_height`), not the raw display.

## Actions

`screenshot`, `snapshot`, `click`, `scroll`, `drag`, `move`, `type`, `key`, `focus`, `move_window`, `resize_window`, `perform_action`, `set_value`, `wait`, `cursor`.

Mutating actions return a follow-up screenshot unless `screenshot` is false. Coordinates on later clicks still refer to the latest image space.

Do **not** use the native `screenshot` tool for this loop. That tool opens the human capture overlay and does not return pixels.

## HUD

The user sees a bottom-right HUD while computer use is active. It is tagged `noscreenshare` and **will not appear in captures**. Do not try to click it. Composer text in the HUD steers you; it is not typed into apps.

## Targeting

Window `address` is a string from `get_windows` / snapshot context. Also: `pid`, `class`, title substring, and terminal `/proc` fields (`tty`, `terminal_pid`, `command`, `cwd`) when present. After `focus`, wait for verification before typing.

If accessibility is empty, ask the user to export `GTK_A11Y=atspi` and `QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1` rather than guessing pixels first.
