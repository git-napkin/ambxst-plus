# Screenshot

`screenshot` opens the Ambxst[+] screenshot overlay (region/window/monitor). It does not dump pixels into the chat.

After the user captures, they can attach or paste. Do not shell out to `grim` unless asked for a file path capture.

To see pixels as the agent, use `request_computer_use` then `use_computer action=screenshot`. `action=snapshot` is the accessibility tree only (no grim). Neither opens this overlay.

