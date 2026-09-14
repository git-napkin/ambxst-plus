# Brightness

Per-monitor brightness via Ambxst[+] Brightness service.

- `get_brightness` — list of `{ name, brightness }` where brightness is 0–1
- `set_brightness` — `{ value: 0.0-1.0, screen?: name }`. Omit screen to set all.

Do not call `brightnessctl` unless the native tool fails.
