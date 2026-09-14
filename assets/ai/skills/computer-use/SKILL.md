# Computer use

Native desktop control for the AI panel. Policy default is **Never**. Advertise `request_computer_use` / `use_computer` only when Computer use is Always ask or Always allow.

## Start

1. Call `request_computer_use` with a short `task_summary`. Wait for the user to approve unless the profile is Always allow.
2. Call `use_computer` with `action=snapshot` before clicking. Snapshot does **not** take a screenshot. It returns windows, the focused node, and a slim accessibility tree with `element_index` values.
3. Prefer `element_index` (or role/name selectors) over pixels. Call `action=screenshot` only when `tree_usable` is false or you need a picture (canvas, games, layout). Pixel `x`/`y` are in that image (`coordinate_width` × `coordinate_height`).

## Actions

`screenshot`, `snapshot`, `click`, `scroll`, `drag`, `move`, `type`, `key`, `focus`, `move_window`, `resize_window`, `perform_action`, `set_value`, `wait`, `cursor`.

Do not screenshot after every action. Snapshot again (tree only) when the UI actually changed. Set `screenshot: true` on a call only if you need a new picture.

Do **not** use the native `screenshot` tool for this loop. That tool opens the human capture overlay and does not return pixels.

For web prices or page text, prefer `exa_search` / `run_shell_command` (curl) over scrolling a browser.

## HUD

The user sees a bottom-right response card while computer use is active. It is hidden for captures. Do not try to click it. Composer text in the HUD steers you; it is not typed into apps.

## Targeting

Window `address` is a string from `get_windows` / snapshot. Also: `pid`, `class`, title substring, and terminal `/proc` fields (`tty`, `terminal_pid`, `command`, `cwd`) when present. After `focus`, wait for verification before typing.

If accessibility is empty (`tree_usable` false), ask the user to export `GTK_A11Y=atspi` and `QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1` rather than guessing pixels first.
