# Volume

Control Ambxst[+] output volume through native tools.

- `get_volume` — current perceptual slider (0–1) and mute state
- `set_volume` — `{ value: 0.0-1.0 }` perceptual slider, not raw gain
- `toggle_mute`

Prefer these over `wpctl`/`pamixer` via the shell.
