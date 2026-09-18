# Upstream gap analysis: Axenide/Ambxst vs git-napkin/ambxst-plus

Comparison of **Axenide/Ambxst** 1.3.5 against this fork, plus a record of
what was actually ported. Ports are limited to features that fit Ambxst[+]
(`cli.sh` + Python computer-use). Go daemon, mods, presets, and native Go
capture are **out of scope**.

| | Ambxst[+] (`git-napkin/ambxst-plus`) | Upstream (`Axenide/Ambxst`) |
|---|---|---|
| Default branch | `main` | `main` (`dev` currently matches `main`) |
| HEAD used | `9dca345b` (2026-09-18) | `a392d270` (2026-09-16, tag **1.3.5**) |
| `version` file | `1.1.5` | `1.3.5` |
| Merge-base | `eb22d210` (2026-05-20, `1.1.5-2`) | same |
| Unique commits | 170 fork-only | 183 upstream-only |

Upstream URL: https://github.com/Axenide/Ambxst
Releases are tag-only (empty notes except **1.3.0** = mods PR
[#230](https://github.com/Axenide/Ambxst/pull/230) and **1.3.2** = pomodoro
[#235](https://github.com/Axenide/Ambxst/pull/235)). There is no in-repo
CHANGELOG; the advertised feature list is `README.md`.

**How to read this:** Ambxst[+] diverged at ~1.1.5 and kept the Bash/Python
`cli.sh` architecture. Upstream spent 1.2.x rewriting that layer into a Go
daemon, then shipped **mods** as 1.3.0. Many “new files” on upstream are
reimplementations of tools Ambxst[+] already has under `scripts/` — those are
called out as equivalent, not missing.

---

## Ranked gaps (what Ambxst[+] does not have)

1. **Mods** — native modification manager (confirmed; 1.3.0). Depends on the Go
   backend. **Hard.**
2. **Go `ambxst` daemon** replacing `cli.sh` — supervisor + JSON-RPC for qs,
   axctl, wl-paste, and most services. **Hard.** Prerequisite for (1), (4),
   (5), (6).
3. **Official presets** — nine bundled looks + Settings/overlay switcher +
   `ambxst preset`. **Medium** for the QML/assets; **hard** if tied to the
   daemon CLI.
4. **Encrypted clipboard** — SQLCipher stores, 50-item cap, image blobs, optional
   tmpfs for unpinned history. **Hard.**
5. **Native Wayland screenshot / color picker / OCR / QR** — DMS-style
   screencopy engine, layer-shell loupe, Go barcodes. **Hard.**
6. **Niri + MangoWC `install`/`remove`** plus generated TOML `[target]` paths.
   **Medium.**
7. **Monocle layout** in the layout picker and keybind catalog. **Easy /
   medium** (`axctl-plus` already special-cases monocle).
8. **Live compositor config eval** (`axctl config raw-batch` / `hl.config()`)
   so theme/gaps apply without a full reload. **Medium.**
9. **`axctl layout set` from the shell** — Ambxst[+] only writes
   `StateService`; upstream actually switches the compositor layout. **Easy.**
10. **Packaging** — `Makefile`, `nix/packages/backend.nix`, GitHub Actions
    prebuilt `ambxst-linux-{amd64,arm64}` on version tags. **Medium** after
    (2).
11. **Small QML bugfixes** still applicable on this tree (pomodoro input
    resync, lockscreen unlock timer when animations are off). **Easy /
    medium.**
12. **Fedora installer COPR** switched to `lionheartp/Hyprland` (“fedora 44”).
    **Easy**, independent of the daemon.

---

## 1. Mods (confirmed)

Shipped as **1.3.0** via
[Axenide/Ambxst#230](https://github.com/Axenide/Ambxst/pull/230)
(`feat(mods): add native modification manager`). Follow-up tags 1.3.1–1.3.5
are almost entirely mods hardening (three-way patch merge, load-order DnD,
trust prompt, version-check bypass, stale-generation rebuild).

### What it is

Declarative **source transformations**, not a plugin runtime. A package is a
directory (or zip/tar/git URL) with `ambxst.mod.json`, optional `settings.json`,
unified diffs under `patches/`, and overlay files under `payload/`. The manager
composes enabled packages onto a clean Ambxst tree and commits an immutable
**generation**. The running shell keeps the old tree until the user restarts.
On the next start there is an eight-second health window: if Quickshell dies,
the last known-good generation is restored.

This is **not** equivalent to Ambxst[+]’s computer-use / Spotlight stack.

### How it works

1. User installs/enables/reorders packages (Settings → Mods, or `ambxst mods …`).
2. Manager builds a temp git repo that borrows the base object store, applies
   overlays + patches in load order (verbatim `git apply`, then three-way merge
   against the patch pre-image if context moved).
3. Two mods inserting at the same anchor both keep their lines; two mods
   rewriting the same lines fail the build and leave the active generation
   unchanged.
4. Success writes `$XDG_CONFIG_HOME/ambxst/mods.json` and a generation under
   `$XDG_DATA_HOME/ambxst/mods/generations`.
5. Daemon launches qs from that generation. After an Ambxst update, a stale
   generation is skipped; `ambxst update` re-composes first.
6. `AMBXST_MODS_DISABLED=1 ambxst` bypasses generations for recovery.

### Entry points

| Layer | Path | Role |
|---|---|---|
| Docs | `docs/mods/README.md`, `docs/mods/manifest.schema.json`, `docs/mods/settings.schema.json` | Contract |
| Example | `examples/mods/compact-player-volume-scroll/` | Patch-only sample |
| CLI | `backend/cmd/ambxst/cmds_mods.go` | `ambxst mods list\|install\|enable\|disable\|move\|update\|rebuild\|rollback\|bypass` |
| IPC | `backend/pkg/mods/service.go` | JSON-RPC `mods.*` on the daemon socket |
| Engine | `backend/pkg/mods/{manager,manifest,version}.go` | Compose, validate, generations |
| QML client | `modules/services/ModsService.qml` | Talks to `BackendService` |
| UI | `modules/widgets/dashboard/controls/ModsPanel.qml` (~1428 lines) | Settings → Mods (puzzle icon, **before** the Ambxst section) |
| Index | `modules/widgets/dashboard/controls/SettingsIndex.qml` | Section 10 |
| Shell | `shell.qml` | No extra window; generation is the source tree qs loads |

### Config

Mods **do not** add keys to `config/defaults/*.js` / `Config.qml`. State lives
outside the reactive config system:

- `$XDG_CONFIG_HOME/ambxst/mods.json` — active/previous generation, enable
  set, load order, **global** `bypassVersionCheck`
- `$XDG_DATA_HOME/ambxst/mods/generations/` — immutable composed trees
- Per-mod `settings.json` (schema-driven booleans/strings/numbers/enums),
  read from QML via `ModsService.getSettings(id)` / `onSettingChanged`

`compatibility.ambxst` is a hard semver range unless the user turns on
**Bypass Ambxst version check** (Settings or `ambxst mods bypass on`).
`testedBaseCommits` is advisory.

### Fork conflicts

- Command and paths are `ambxst` / `~/.config/ambxst`. Ambxst[+] is `ambxst+`
  / `~/.config/ambxst+/`.
- Settings section numbering: fork Settings is 0–9 (Ambxst[+]); upstream
  inserted Mods as section 10 and reordered it before the shell section.
- `Config.qml` and `SettingsTab.qml` have diverged heavily (pauseAutoSave is
  an int here, bool upstream; computer-use keys only here).
- Composition assumes a clean upstream source tree. Ambxst[+] patches (Spotlight,
  fingerprint, camera, `ambxst+` rebrand) would make community mods fail
  context matching unless they are written against this fork.
- **Porting without the Go daemon is not realistic.** `ModsService` is a thin
  JSON-RPC client over `BackendService`.

---

## 2. Go backend (1.2.0 architectural break)

Upstream deleted `cli.sh` and most of `scripts/*.py` / `scripts/*.sh`, replacing
them with `backend/` (Go module, vendored). One `ambxst` process:

- listens on a Unix JSON-RPC socket
- supervises Quickshell, axctl, and `wl-paste`
- implements services that QML used to shell out for

Key paths: `backend/cmd/ambxst/main.go`, `backend/pkg/daemon/daemon.go`,
`backend/pkg/ipc/`, `modules/services/BackendService.qml`. Build:
`Makefile` → `./ambxst`. Nix: `nix/packages/backend.nix`. Releases:
`.github/workflows/release.yml` builds `ambxst-linux-amd64` / `arm64` on
version tags.

**QML service rename (not missing features):**

| Ambxst[+] (still here) | Upstream |
|---|---|
| `CaffeineService.qml` | `CaffeineClient.qml` |
| `GameModeService.qml` | `GameModeClient.qml` |
| `NightLightService.qml` | `NightLightClient.qml` |
| `PowerProfile.qml` | `PowerProfileClient.qml` |
| `IdleInhibitor.qml` | folded into Go caffeine/idle |
| `scripts/keystore.py` etc. | `backend/pkg/svc/*` |

User-facing caffeine / game mode / night light / power profiles **already
exist** here. Do not port the clients without the daemon.

New CLI surface Ambxst[+] lacks (beyond mods):

```
ambxst install|remove niri|mango
ambxst colorpicker          # native loupe, not hyprpicker
ambxst preset [-l|"Name"]
ambxst ipc call <method> <json>
ambxst lockwall|thumbs|dthumbs   # Go ports of existing Python helpers
```

`ambxst wallpaper` already exists in `cli.sh`.

**Fork conflict:** Ambxst[+] `cli.sh` plus `scripts/ai/` (computer-use, Jev,
MCP, fingerprint) are the opposite direction of upstream’s “drop Python.”
A naive merge would delete the fork’s assistant backend. Any port should keep
`cli.sh` or wrap it until the daemon can host those Python tools.

---

## 3. User-facing features

### Official presets — missing

Nine bundled presets under `assets/presets/`: Ambxst Default, Caelestiax,
Dotsquared, Frutiger Aero, Frutiger Aqua, GNOME, Liquid Glass, Manga, Retro.

QML: `modules/services/PresetsService.qml`,
`modules/widgets/presets/{PresetsButton,PresetsPopup,PresetsTab}.qml`,
`shell.qml` loader gated on `Visibilities.presets`. CLI:
`PresetCommandService.qml` + `ambxst preset`. Copies JSON domains into
`~/.config/ambxst/config/`, excluding `system.json` / `ai.json` /
`prefix.json` / `weather.json`.

Ambxst[+] has no presets tree and no preset widgets.

**Port:** medium if you copy assets + QML and retarget paths to `ambxst+`.
Hard if you also want the daemon CLI. Watch `Config.qml` (`presetDir`) and
dashboard tab layout.

### Monocle layout — missing

Upstream `GlobalStates.availableLayouts` is
`["dwindle", "master", "scrolling", "monocle"]` and uses `axctl layout set`.
Keybinds: `monocle.focus` / `monocle.move-window` in `config/KeybindActions.js`.
Icon in `modules/theme/Icons.qml`. Bar:
`modules/bar/LayoutSelectorButton.qml`.

Ambxst[+] lists only dwindle/master/scrolling and `setCompositorLayout()`
**does not dispatch to axctl** — it only updates `StateService`.

`axctl-plus` already emits monocle-aware Hyprland Lua
(`pkg/ipc/hyprland/generator_lua.go`), so the compositor side is ahead of
this shell.

**Port:** easy/medium. Add the layout + icon + keybinds, and actually call
`axctl layout set`. Little mods interaction.

### Niri / MangoWC install targets — missing

`ambxst install niri` / `ambxst install mango` (and `remove`) in
`backend/cmd/ambxst/commands.go`. Generated compositor TOML includes:

```toml
[target]
niri = "niri.kdl"
mango = "mango.conf"
```

Ambxst[+] `cli.sh` only documents `install hyprland`. Assets already include
niri/mango compositor icons.

**Port:** medium. Pattern already exists for Hyprland in `cli.sh`; TOML
`[target]` is a small `CompositorTomlWriter.qml` / backend change. Full
compositor parity is still axctl’s job.

### Native color picker / screenshot / OCR / QR — missing as *implementations*

Ambxst[+] already exposes color picker, screenshot, OCR, and QR in the tools
menu (`Screenshot.captureMode = "ocr"|"qr"`). Upstream replaced the helpers:

- Color picker: DMS layer-shell loupe (`backend/internal/colorpicker/`,
  `cmds_colorpicker.go`) instead of `scripts/colorpicker.py` / hyprpicker.
- Screenshot: ported DankMaterialShell screencopy engine with CICP/HDR PNG
  and **frozen session buffers** (`backend/internal/screenshot/`,
  `backend/pkg/capture/`, fix `a705748a`).
- OCR / QR: `ambxst ocr` / `ambxst qr` in Go (`backend/pkg/svc/ocr/`,
  pure-Go barcodes via gozxing). Region selection reuses the screenshot
  overlay.

**Port:** hard (Wayland protocols, shm, layer-shell). User-visible gap is
mainly the loupe picker and more reliable capture, not the menu entries.

### Encrypted clipboard — missing

Upstream 1.3.4-ish: encrypted SQLite (pinned + unpinned), 50-item cap, images
as blobs, `Config.system.clipboard.tmpfs` to keep unpinned history on tmpfs
(`config/defaults/system.js`, `backend/pkg/svc/clipboard/`).

Ambxst[+] still uses `scripts/clipboard_*.sh` + `clipboard_init.sql`.

**Port:** hard (daemon + migration). New config key must land in both
`config/defaults/system.js` and `Config.qml`.

---

## 4. Services / integrations

| Upstream addition | Ambxst[+] status | Port |
|---|---|---|
| `BackendService.qml` JSON-RPC client | Absent | Hard (needs daemon) |
| `WallpaperCommandService.qml` | `cli.sh wallpaper` already talks to the shell | Skip / equivalent |
| `PresetCommandService.qml` | Absent | With presets |
| `TerminalService.qml` + configurable terminal | **Already here** (`Config.system.terminal*`, not `general.js`) | Equivalent |
| `PywalZenGenerator.qml` | **Already here** | Equivalent |
| GTK `axctl darkmode` sync | **Already here** (`GtkGenerator.qml`) | Equivalent |
| Live `hl.config()` eval via axctl `raw-batch` | Absent (`CompositorTomlWriter.qml` writes files only) | Medium |
| Notify IPC (`backend/pkg/svc/notify`) so CLI tools use the shell notification service | Absent; pomodoro still uses a mixed path | Medium with daemon |
| Network: SSID passed to nmcli via argv | Ambxst[+] QML already uses argv arrays (`NetworkService.qml`) | Equivalent; the Go fix does not apply |
| IPC FIFO moved to `$XDG_RUNTIME_DIR/ambxst_ipc.pipe` | Ambxst[+] already uses `$XDG_RUNTIME_DIR/ambxst+_ipc.pipe` | Equivalent (name differs) |
| `TMUX_TMPDIR` defaulted to the user runtime dir | Absent | Easy |

`modules/notch/NotchWindow.qml` exists upstream but the `PanelWindow` body is
commented out — not a real feature.

Upstream `modules/services/ai/strategies/*` (OpenAI, Anthropic, Gemini, Groq,
MiniMax, Mistral, Ollama) is the **old QML HTTP assistant**. Ambxst[+] replaced
that with `scripts/ai/` + Spotlight. Not a gap; fork is ahead. Groq/MiniMax/
Mistral icons exist here; first-class Python providers do not (OpenRouter /
custom cover them).

---

## 5. Config keys / defaults

| Key | Upstream | Ambxst[+] | Notes |
|---|---|---|---|
| `config/defaults/general.js` (`terminal`, `terminalAdvanced`, `terminalCommand`) | New domain | Same fields live under **`system.js`** | Equivalent; do not add a second copy |
| `system.clipboard.tmpfs` | Yes | No | Real gap; pair with encrypted clipboard |
| Mods state | `mods.json` (not Config) | — | See §1 |
| `osdHideInterval` / `osdSuppressOnDrag` | Mentioned in 1.2.x brightness commits, **not present** on current `upstream/main` | — | Reverted with the brightness 1.1.5 restore |
| `screenshotToolMode` on `GlobalStates` | Documented **deprecated** in upstream `AGENTS.md` | Still used in fork tools | Deprecation only |

No other new defaults files. Brightness OSD “two-flag / OSDManager” work was
landed then largely reverted (`1f1bcf25 revert(brightness): restore 1.1.5
implementation`). Do not chase those commits.

---

## 6. Scripts / packaging / Nix

**Deleted upstream (still in this fork, by design):** `cli.sh`,
`scripts/{brightness_list,clipboard_*,colorpicker,desktop_thumbgen,keystore,link_preview,lockwall,loginlock,ocr,qr_scan,sleep_monitor,system_monitor,thumbgen,weather,wf-record}*`.

**Added upstream:** `backend/**` (including a large `vendor/`), `Makefile`,
`docs/mods/`, `examples/mods/`, `nix/packages/backend.nix`,
`.github/workflows/release.yml`.

Nix `tools.nix` on upstream **drops** Python, grim, slurp, ImageMagick, zbar,
ydotool, at-spi2-core, fprintd/pam — all of which Ambxst[+] still needs for
computer-use, fingerprint, and the Python scripts. Do not copy that list.

`install.sh`: Fedora COPR `solopasha/hyprland` → `lionheartp/Hyprland`;
`git pull` now syncs the current branch instead of skipping non-`main`; leftover
pipx/python deps removed. The COPR change is a one-line, low-risk cherry-pick.
The python drop is **not** safe here.

README: NixOS + home-manager `hyprland.lua` guidance (Hyprland ≥0.56). Useful
docs; paths would need `ambxst+`.

---

## 7. Bugfixes on upstream that still apply here

Cherry-pick candidates that do **not** require the Go daemon:

| Fix | Upstream | Why it still matters | Port |
|---|---|---|---|
| Pomodoro timer inputs desync | `c0730be9` / PR [#235](https://github.com/Axenide/Ambxst/pull/235) (`resyncTimerInputs`) | Diff against this tree still shows the missing resync | Easy. Ignore the `YEEZY.md` noise in that commit |
| Lockscreen unlock timer interval 0 never fires | `db4f58be` | Fork still has `interval: Config.animDuration * 2` in `LockScreen.qml` | Medium: lockscreen has fingerprint code that must be preserved |
| Settings window screen set before map | `8ea605ed` | Fork already has the “resolve screen before create” comment; remaining delta is branding + focus/workspace behavior | Easy / skip after a 5-line review |

Daemon-only fixes (skip until §2): screenshot frozen buffers, wallpaper
symlink/`~` expansion, network SSID interpolation, gamemode TOML live eval,
brightness pipe keybinds, compositor axctl socket in the runtime dir.

**Already here / equivalent:** GTK darkmode, terminal command, Pywal Zen,
wallpaper CLI, BarPopup `groupId` mutual exclusion, NvChad wallsync, workspace
`slidefade` vs `slidefadevert` in `CompositorTomlWriter.qml`, IPC pipe under
`XDG_RUNTIME_DIR`.

---

## 8. Deprecations / renames / breaking changes

- Binary/command: `ambxst` vs this fork’s `ambxst+`.
- `cli.sh` **removed**; `AGENTS.md` says so explicitly.
- Python/Bash backends → Go services; Nix no longer ships a Python env.
- QML `*Service.qml` → `*Client.qml` for caffeine/gamemode/nightlight/power
  profile.
- Lockscreen helper dir `lockscreen/ambxst-auth` vs `lockscreen/ambxst+-auth`
  (rebrand, not a feature).
- `screenshotToolMode` deprecated upstream.
- Brightness keybinds write a FIFO instead of `ambxst brightness +/-5`
  (after several reverts). Fork still uses the CLI brightness path.
- Upstream `Config.pauseAutoSave` is a boolean; fork uses a ref-counted int.
  Any shared QML from upstream will be wrong until adapted.

---

## 9. Intentional non-gaps (fork already has it, or different name)

- Configurable terminal (`system.terminal*` vs upstream `general.js`).
- `TerminalService.qml`, `PywalZenGenerator.qml`, GTK `axctl darkmode`.
- Wallpaper CLI with `-scheme` / `-oled` / `-tint` / `-monitor`.
- Tools menu OCR/QR using the screenshot overlay.
- Caffeine, game mode, night light, power profiles, weather, keystore,
  clipboard history, thumbs, lockwall, system monitor (Python/Bash here, Go
  there).
- Computer-use / Spotlight / Jev / fingerprint / camera indicator — **fork-only**;
  upstream does not have them.

---

## What this fork will not port

Ambxst[+] keeps `cli.sh`, `scripts/ai/` (Spotlight / computer-use), fingerprint,
and camera. These upstream pieces **do not fit** that architecture and are
**out of scope**:

- Go `ambxst` daemon (would replace or dual-path `cli.sh`; computer-use stays Python)
- Mods (requires that daemon; community mods target upstream paths)
- Official presets (intentionally removed here)
- Packaging for a Go daemon (`Makefile`, `nix/packages/backend.nix`, release binaries)
- Encrypted clipboard / native Wayland screenshot / loupe / Go OCR-QR *as
  upstream Go backend ports* (tools menu entries already exist via Python/Bash)

---

## Suggested port order (acted on)

1. Easy QML fixes: pomodoro resync; lockscreen unlock timer; Fedora COPR;
   optional `TMUX_TMPDIR`. **Done.**
2. `axctl layout set` + monocle in the picker/keybinds. **Done.**
3. `cli.sh install niri|mango` and TOML `[target]`. **Done.**
4. Live compositor `hl.config()` via `axctl config raw-batch` (no Go daemon).
   **Done.**
5. Presets / mods / Go daemon / native Go capture: **out of scope** (see above).

---

## Method notes

Compared `origin/main` (`git-napkin/ambxst-plus`) to `upstream/main`
(`Axenide/Ambxst`) via merge-base `eb22d210`, file-tree `comm`,
`git log origin/main..upstream/main`, GitHub releases, and upstream
`README.md` / `docs/mods/` / `AGENTS.md`. Ignored `backend/vendor/**`,
`flake.lock`, whitespace, and commented-out `NotchWindow.qml`.

---

## Porting progress

Only ports that make sense without a Go daemon. `cli.sh` and `scripts/ai/` stay.

| Item | Status | Notes |
|---|---|---|
| Pomodoro `resyncTimerInputs` (#235) | **Done** | `modules/bar/clock/Pomodoro.qml` |
| Lockscreen unlock timer when `animDuration` is 0 | **Done** | Fingerprint success path unchanged |
| Monocle in picker/keybinds/icons + `axctl layout set` | **Done** | `GlobalStates.setCompositorLayout` now dispatches |
| Niri + MangoWC `install`/`remove` | **Done** | `cli.sh`; paths under `~/.local/share/ambxst+/` |
| TOML `[target]` hyprland/niri/mango | **Done** | `CompositorTomlWriter.qml`; axctl-plus still writes `hyprland.conf` until it reads `[target]` |
| Live `hl.config()` via `axctl config raw-batch` | **Done** | `CompositorConfig.qml`; skips live eval while Game Mode is on |
| Fedora COPR `lionheartp/Hyprland` | **Done** | `install.sh` |
| `TMUX_TMPDIR` → `$XDG_RUNTIME_DIR` | **Done** | `cli.sh` launch path; existing value wins |
| Go `ambxst` daemon | **Out of scope** | Fork keeps Python/`cli.sh` computer-use |
| Mods manager | **Out of scope** | Requires the Go daemon |
| Official presets | **Out of scope** | Intentionally removed here |
| Encrypted clipboard / SQLCipher | **Out of scope** | Upstream Go backend port |
| Native screenshot / loupe / Go OCR-QR | **Out of scope** | Tools menu already uses Python/Bash helpers |
| Packaging (Makefile, nix backend, release binaries) | **Out of scope** | Only exists to ship the Go daemon |
