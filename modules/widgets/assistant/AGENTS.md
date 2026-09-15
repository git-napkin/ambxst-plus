# AGENTS.md — modules/widgets/assistant/

## OVERVIEW
Spotlight-style AI overlay. Compact bar on the focused monitor; transcript grows down from top/center, or up from the bottom. Not a sidebar and not hosted in the notch launcher.

## STRUCTURE

| File | Role |
|------|------|
| `AssistantPopup.qml` | PanelWindow, Overlay, namespace `ambxst+:assistant`, FocusGrab, scrim |
| `ComputerUseHud.qml` | HUD-sized PanelWindow, namespace `ambxst+:computer-use`; last assistant text via `AssistantMessage`; 3s auto-hide output card; type-to-open steer box (Esc once closes, Esc twice in 1.5s exits); Exclusive keys while the agent is driving, with compositor binds (workspace switch) replayed |
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
- Super+A and `ambxst+ run assistant` toggle `Visibilities` module `"assistant"`. During computer use the Spotlight scrim drops and `ComputerUseHud` takes over; Super+A still closes the session. Typing opens a separate steer box; Esc closes it, Esc twice within 1.5s stops computer use and restores Spotlight. Agent turns finishing do **not** end the session. The screen frame ring keeps the user's `srBg` opacity/halftone and tints it with `Config.theme.computerUseFrameColor1/2/3`.

## ANTI-PATTERNS

- Do not host this in the notch StackView or restore the old sidebar exclusive zone
- Do not put API keys on curl argv; the Python agent reads KeyStore
