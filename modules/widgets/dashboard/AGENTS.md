# DASHBOARD KNOWLEDGE BASE

## OVERVIEW
Central interactive hub of Ambxst[+]. Tabbed interface with LRU-based lazy-loading for widgets, system controls, media, clipboard, notes, and tmux management. Opened via the Notch overlay. AI chat is the Spotlight overlay (Super+A), not a dashboard tab.

## STRUCTURE
- **Root**: `Dashboard.qml` — Orchestrates LRU logic, tab layout, and open/close animations.
- **Side Tabs**: Vertical navigation bar on the left for switching main views.
- **Sub-tabs** (each a directory):
  - `widgets/`: `WidgetsTab` — Main grid: `FullPlayer`, `Calendar`, `NotificationHistory`, weather, quick toggles.
  - `controls/`: Settings panels — `ShellPanel`, `ThemePanel`, `BindsPanel`, `CompositorPanel`, `SystemPanel`, `VariantEditor`.
  - `clipboard/`: `ClipboardTab` — Searchable clipboard history with categories.
  - `notes/`: `NotesTab` (3505 lines) — Rich text editor with file management.
  - `tmux/`: `TmuxTab` (2250 lines) — Tmux session manager.
  - `emoji/`: `EmojiTab` (934 lines) — Emoji picker with search.
  - `metrics/`: `MetricsTab` (987 lines) — Real-time CPU/RAM/GPU/disk monitoring.
  - `wallpapers/`: `WallpapersTab` / `Wallpaper.qml` — Wallpaper browser and manager.
  - `kanban/`: Kanban board for task management.

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| **Tab loading** | `Dashboard.qml` | `TabLoader` + `shouldTabBeLoaded(index)` LRU logic |
| **System settings** | `controls/ShellPanel.qml` | Bar, dock, notch configuration UI |
| **Theme settings** | `controls/ThemePanel.qml` | Colors, gradients, fonts, opacity, computer-use frame ring |
| **Keybindings** | `controls/BindsPanel.qml` | Compositor keybind editor |
| **AI settings** | `modules/widgets/config/AiPanel.qml` | Keys, execution profile, overlay, tools. Chat UI is the Spotlight overlay |
| **Clipboard** | `clipboard/ClipboardTab.qml` | Largest file (3615 lines). Category filtering |
| **Notes** | `notes/NotesTab.qml` | Rich text, file tree, search |

## CONVENTIONS
- **LRU management**: Use `shouldTabBeLoaded(index)` for conditional `Loader.active`. Tabs evicted when exceeding cache limit.
- **Keyboard flow**: Components implement `focusSearchInput()` so root can forward focus on open.
- **UI primitives**: ALWAYS use `StyledRect` variants (`"pane"`, `"internalbg"`, `"focus"`) for containers.
- **Settings controls**: Use `SettingsRow` / `SettingsGroup` / `SettingsSwitch` / `SettingsSpinBox` / `SettingsField` / `SettingsButton` / `SegmentedSwitch`. Never drop raw Qt `Switch`, `CheckBox`, `SpinBox`, or `TextField` into a settings panel.
- **Service bindings**: Connect directly to service singletons (`NetworkService`, `Audio`). No prop-drilling.
- **Large files**: Most tabs exceed 900 lines. Edit with care; use targeted line ranges.

## ANTI-PATTERNS
- Creating tab content without LRU integration via `TabLoader`.
- Prop-drilling service state through parent components instead of importing singletons directly.
- Using `Rectangle` instead of `StyledRect` for any container.
- Using stock Qt `Switch` / `CheckBox` / `SpinBox` / `TextField` in settings panels.
