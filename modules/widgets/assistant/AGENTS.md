# AGENTS.md — modules/widgets/assistant/

## OVERVIEW
Spotlight-style AI overlay. Compact bar in the upper third of the focused monitor; transcript grows down. Not a sidebar and not hosted in the notch launcher.

## STRUCTURE

| File | Role |
|------|------|
| `AssistantPopup.qml` | PanelWindow, Overlay, namespace `ambxst+:assistant`, FocusGrab, scrim |
| `ComputerUseHud.qml` | HUD-sized PanelWindow, namespace `ambxst+:computer-use`; last assistant text only, auto-hides, Warp-style footer |
| `AssistantBar.qml` | Search input, send/stop |
| `AssistantIdleList.qml` | Recent chats, saved commands, slash hints |
| `AssistantTranscript.qml` | Message list |
| `AssistantMessage.qml` | Query + document rendering (markdown, math, tables, code) |
| `ToolCallChip.qml` | Collapsed tool call |
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
| Config | `Config.ai.*` (`overlayWidth`, `overlayYFraction`, `showScrim`, `executionProfile`) |

## CONVENTIONS

- Colors via `Colors.*`, radii via `Styling.popupRadius()`, no hardcoded hex
- Hover/press: `Styling.hoverAlpha` / `pressAlpha`, icon buttons scale 0.96
- Mutate `Ai.currentChat` from Process handlers only via `Qt.callLater`
- Super+A and `ambxst+ run assistant` toggle `Visibilities` module `"assistant"`. During computer use the Spotlight scrim drops and `ComputerUseHud` takes over; Super+A still closes the session.

## ANTI-PATTERNS

- Do not host this in the notch StackView or restore the old sidebar exclusive zone
- Do not put API keys on curl argv; the Python agent reads KeyStore
