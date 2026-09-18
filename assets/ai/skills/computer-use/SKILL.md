# Computer use

Native desktop control for the AI panel. Policy default is **Never**. Advertise `request_computer_use` / `use_computer` only when Computer use is Always ask or Always allow.

## Start

1. Call `request_computer_use` with a short `task_summary`. Wait for the user to approve unless the profile is Always allow.
2. Call `use_computer` with `action=snapshot` before clicking. Snapshot is the accessibility tree + windows. It is **not** a screenshot. A grim JPEG is attached automatically only when `tree_usable` is false.
3. Prefer `element_index` (or role/name selectors) over pixels. Each slim node includes `frame: [x, y, w, h]` for grounding. Call `action=screenshot` only when you need pixels (canvas, games, layout). Pixel `x`/`y` are in the attached grim image (`width` × `height`), not compositor logical coords.
4. After the session is granted it stays granted across turns until the user hits Stop, the lockscreen, or `end_computer_use`. Do **not** call `request_computer_use` again for a follow-up in the same task. Routine actions (focus, click, type, scroll) run without asking. Set `critical: true` before payments, sending email or messages, purchases, account deletion, or other irreversible actions.

## Observe vs screenshot

| Call | What you get |
|---|---|
| `use_computer action=snapshot` | Windows + slim AT-SPI tree. No image unless the tree is empty. |
| `use_computer action=screenshot` | Silent grim JPEG for the **agent**. HUD is hidden. |
| Native `screenshot` | Human overlay. **No pixels.** During an active session this is aliased to grim `action=screenshot`. |

Do **not** screenshot after every action. After click/type/key/scroll/drag the harness already returns a fresh tree (and a JPEG only if the tree is unusable). Set `observe=none` only if you must skip that recapture. Set `screenshot: true` on a call only if you need a new picture anyway.

`actions[]` is an ordered batch and **is honored** even when top-level `action` is also set (`action` runs first). Serial; stops on first error; observes once at the end.

For web prices or page text, prefer `exa_search` / `run_shell_command` (curl) over scrolling a browser.

## HUD

The user sees a bottom-right response card while computer use is active. A separate steer box may appear when they type; both are hidden for captures and must not be clicked or typed into. Steer text is not typed into apps. After you finish a turn the desktop grant **stays**; the pointer is unlocked so the user can use the machine, then re-locked on the next mutating action. Do not tell the user to re-approve computer use unless they Stopped the session.

## Targeting

Window `address` is a string from `get_windows` / snapshot. Also: `pid`, `class`, title substring, and terminal `/proc` fields (`tty`, `terminal_pid`, `command`, `cwd`) when present. After `focus`, wait for verification before typing.

Cursor aiming teleports (one compositor `movecursor`). Do not plan multi-step mouse easing. Click via AT-SPI `DoAction` when the node has a click/press/toggle action; otherwise the runtime clicks the node's `frame` center. Pixel clicks need a grim shot first — if you omit one, the error includes `next` (and may already attach a shot).

If accessibility is empty (`tree_usable` false), the shell starts the AT-SPI bus when it can. Apps still need `GTK_A11Y=atspi` and `QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1` (restart them after exporting). Screenshot when the tree is empty.

Hyprland implements cursor move and sendshortcut. Niri and Mango do not — do not assume pixel aiming works there.
