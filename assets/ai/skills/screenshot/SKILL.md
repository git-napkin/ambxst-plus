# Screenshot

Native `screenshot` opens the Ambxst[+] **human** screenshot overlay (region/window/monitor). It does **not** dump pixels into the chat.

After the user captures, they can attach or paste. Do not shell out to `grim` unless asked for a file path capture.

To see the screen as the agent:

- `use_computer action=screenshot` — silent grim JPEG (HUD hidden). Coordinates for later clicks are this image's `width` × `height`.
- `use_computer action=snapshot` — accessibility tree + windows. **No image**, unless `tree_usable` is false (the harness then attaches one grim JPEG).

Do not confuse snapshot (tree) with screenshot (pixels) or with native `screenshot` (overlay, no pixels). During an active computer-use session, native `screenshot` is aliased to grim `use_computer action=screenshot`.
