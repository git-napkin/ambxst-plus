# Windows

- `get_windows` — `{ address, title, class, class_name, focused, at, size, workspace, monitor, floating, fullscreen, xwayland, pid }`
- `focus_window` — `{ address }` focuses that client

Addresses come from `get_windows`. Do not invent Hyprland `hyprctl` dispatches when these tools exist. For seeing the screen and clicking, use `request_computer_use` / `use_computer` (computer-use skill), not this tool.
