# AGENTS.md — modules/widgets/assistant/

## OVERVIEW
Spotlight-style AI overlay. Compact bar on the focused monitor; transcript grows down from top/center, or up from the bottom. Not a sidebar and not hosted in the notch launcher.

## STRUCTURE

| File | Role |
|------|------|
| `AssistantPopup.qml` | PanelWindow, Overlay, namespace `ambxst+:assistant`, FocusGrab, scrim |
| `ComputerUseHud.qml` | HUD-sized overlay on a fullscreen click-through PanelWindow, namespace `ambxst+:computer-use`; last assistant text via `AssistantMessage`; 2.5s auto-hide after the last assistant token (not while the agent is merely thinking); type-to-open steer box (Esc once closes, Esc twice in 1.5s exits); Exclusive keys on a fullscreen key sink while the agent is driving, with compositor binds (workspace switch) replayed. No clickable Stop/Take-control chrome while the pointer is locked. Actual `use_computer wait` shows a live "Waiting for Ns" countdown. Stays mapped during captures so Escape never goes nowhere. |
| `AssistantBar.qml` | Search input, send/stop |
| `AssistantIdleList.qml` | Saved commands, slash hints |
| `AssistantTranscript.qml` | Message list |
| `AssistantMessage.qml` | Query + document rendering (markdown, math, tables, code) |
| `ComputerUseWorkChip.qml` | Post-session "Worked for Ns" expander wrapping tool calls and intermediate replies |
| `ApprovalCard.qml` | Approve / Reject |
| `DiffPreviewCard.qml` | File edit preview |
| `QuestionCard.qml` | `ask_user_question` multiple choice |
| `message_content.js` | Split fenced code, display math, and GFM tables; convert LaTeX to unicode |
| `MathBlock.qml` | Display-math block |
| `MarkdownTable.qml` | Rendered markdown table |

CodeBlock and ModelSelectorPopup live in `modules/sidebar/` and are imported from there. Slash hints in the idle list appear only when the input starts with `/`.

## WHERE TO LOOK

| Task | File |
|------|------|
| Window recipe | `AssistantPopup.qml` (copy OverviewPopup: exclusive keyboard, ExclusionMode.Ignore) |
| Computer-use HUD | `ComputerUseHud.qml` + `modules/services/ComputerUse.qml` |
| Chat / agent IPC | `modules/services/Ai.qml` |
| Native tools | `modules/services/ai/NativeToolBridge.qml` |
| Config | `Config.ai.*` (`overlayWidth`, `overlayAnchor`, `overlayOffsetX`, `overlayOffsetY`, `showScrim`, `executionProfile`) |

## CONVENTIONS

- Colors via `Colors.*`, radii via `Styling.popupRadius()`, no hardcoded hex
- Hover/press: `Styling.hoverAlpha` / `pressAlpha`, icon buttons scale 0.96
- Mutate `Ai.currentChat` from Process handlers only via `Qt.callLater`
- Super+A and `ambxst+ run assistant` toggle `Visibilities` module `"assistant"`. During computer use the Spotlight scrim drops and `ComputerUseHud` takes over; Super+A still closes the session. Typing opens a separate steer box (printable keys, including when Wayland omits `event.text` until a TextInput is focused); Esc closes it, Esc twice within 1.5s stops computer use and restores Spotlight. Agent-driving HUD chrome is keyboard-only: hide the Stop/Take-control/Hide buttons because physical pointers are disabled. The output card hides 2.5s after the last assistant token even if the model is still thinking; a real `wait` action replaces the card with a "Waiting for Ns" countdown that stays up until the wait ends. The computer-use **grant** stays after the agent turn finishes (`done`); exclusive keys and pointer lock drop while idle (`grantedIdle`) so the user can use the desktop, then re-lock on the next mutating action. End the session on Stop / lock / error / cancel. Physical pointer devices are disabled while driving, but never devices whose name looks like a keyboard (Hyprland lists some keyboards under `mice`). During an approval prompt the pointer is re-enabled so Reject/Approve can be clicked, then locked again; Left/Right highlights Reject/Approve and Enter confirms (Esc still rejects). After the session grant, only irreversible actions (pay, send mail, purchase) ask again. The screen frame ring keeps the user's `srBg` opacity/halftone and tints it with `Config.theme.computerUseFrameColor1/2/3`.

## ANTI-PATTERNS

- Do not host this in the notch StackView or restore the old sidebar exclusive zone
- Do not put API keys on curl argv; the Python agent reads KeyStore
