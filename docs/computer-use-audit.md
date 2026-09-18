# Computer-use audit: is this the best way to do it?

**Verdict: not competitive with Codex-class computer use.** The shape is right
(hybrid accessibility + screenshot pixels, session grant, tree-first observe).
The loop, observation, Linux a11y coverage, and input backends are not.

This is an audit and roadmap, not a rewrite. Claims about Ambxst[+] are from
this checkout. Claims about Codex / Claude / peers are labeled **public**
(docs, blog, API reference) or **inferred**.

HUD / takeover UX was recently hardened (exclusive keys, pointer unlock on
approval, session end on agent `done`). Those are treated as settled unless
they cap capability.

---

## Architecture map

```
  Spotlight model  (default: gemini-2.0-flash)
        │  tool_calls: request_computer_use / use_computer
        ▼
  scripts/ai/agent.py          NDJSON stdin/stdout, no iter cap while CU granted
        │  native_request()    round-trip, AGENT_WAIT=120s
        ▼
  Ai.qml → NativeToolBridge.qml
        │
        ├─ computer_use_session  ComputerUse.qml (begin/end/gate/inject_*)
        ├─ use_computer          screenshot / focus / move / resize / cursor
        └─ get_windows           AxctlService clients
        │
        ▼
  QML native side                         Python local side
  ───────────────                         ─────────────────
  grim (Screenshot.captureSilent)         AT-SPI D-Bus walk (atspi.py)
  hide HUD 50ms then capture              JPEG downscale (screenshot.py)
  Axctl/hyprctl focus + verify            ydotool clicks / wheel / drag
  hyprctl device disable (mice)           wtype type; hyprctl sendshortcut
  exclusive layer-shell keyboard          compositor movecursor (eased)
  frame ring + HUD                        doctor.py readiness
```

**Control plane:** `request_computer_use` then `use_computer` in
`scripts/ai/tools/computer_use.py`. Policy lives in
`scripts/ai/execution_profile.py` (`computerUse`: Never / AlwaysAsk /
AlwaysAllow; default **Never** in `config/defaults/ai.js`).

**Session plane:** `modules/services/ComputerUse.qml`. Begin starts ydotoold
and AT-SPI if missing, disables physical pointers, applies a Hyprland
`no_screen_share` layerrule, and puts the HUD on
`ambxst+:computer-use`. Gate refuses mutating actions while the user has
control, is steering, the session is ending, or the lockscreen is up.

**Observe plane:** `action=snapshot` is tree-only (windows + AT-SPI, no
image). `action=screenshot` is grim PNG → optional ImageMagick crop →
Python JPEG ≤1280px, q70, 2 MiB → base64 attachment. Agent keeps the newest
**2** images (`MAX_IMAGE_ATTACHMENTS` in `scripts/ai/agent.py`).

**Act plane:** AT-SPI `DoAction` / `SetTextContents` when
`element_index` resolves and the first action is click/press/toggle;
otherwise compositor cursor + ydotool. Keys prefer `hyprctl sendshortcut`,
then axctl, then wtype, then ydotool. Window move/resize/focus go through
Axctl/Hyprland only.

**End:** QML session and Python grant both die on agent `done` / error /
cancel (`Ai.qml` `finishComputerUseSession`). Skill text tells the model to
call `request_computer_use` again for another pass.

axctl-plus is the compositor IPC daemon. Hyprland implements
`MoveCursor` / `SendShortcut` / `GetCursorPosition`. Niri and Mango return
`ErrNotSupported` for all three (`pkg/ipc/niri/client.go`,
`pkg/ipc/mango/client.go`). Computer use is Hyprland-shaped with a
ydotool/wtype escape hatch, not compositor-portable.

---

## Current design choices (confirmed)

| Surface | Choice | Where |
|---|---|---|
| Action representation | Hybrid: `element_index` → AT-SPI; pixel `x/y` in **attached image** space | `UseComputerTool`, `coords.preview_to_logical` |
| Snapshot | Tree + windows, **no screenshot** unless `screenshot: true` | `computer_use.py` `_dispatch("snapshot")` |
| Public tree | Cap 150 nodes, 200 chars text; **bounds stripped** | `atspi.public_tree` / `slim_node` |
| Pixel clicks | Require a prior screenshot; last-shot meta maps scale/crop/origin/monitor scale | `PIXEL_SHOT_NEEDED`, tests |
| Cursor | Hyprland `hl.dsp.cursor.move` with ease-in-out, 4–8 steps, 80–350 ms | `input.movecursor` |
| Click / scroll / drag | ydotool uinput; **never** `ydotool --absolute` | `input.py` header + `click`/`scroll`/`drag` |
| Type | `wtype` stdin; ydotool `type --file -` fallback | `input.type_text` |
| Key chords | `hyprctl dispatch sendshortcut` to `activewindow` or address | `input.press_key` |
| Wait | `time.sleep`, cap 5 s, **no** visual/tree sync | `WAIT_CAP_MS` |
| Observe after act | None unless the model sets `screenshot: true` | `_maybe_shot` |
| Type follow-up | Full AT-SPI re-walk via `focused_element()` | `atspi.focused_element` → `snapshot_tree` |
| Screenshots | grim `-c` (cursor on), per-monitor or window crop, JPEG 1280/q70 | `Screenshot.qml`, `screenshot.py` |
| Multi-monitor | `Quickshell.screens` origins + per-output scale; pick focused monitor | `ComputerUse.screenList` / `pickScreen` |
| Focus | Axctl `focuswindow`, poll up to 20×50 ms, `verified` flag, 50 ms settle | `focusTimer`, `FOCUS_SETTLE` |
| Session lifetime | One Spotlight turn; grab released on `done` | `Ai.qml` case `"done"` |
| Round-trips | Every action: native `gate`; type/key also `inject_begin`/`inject_end`; screenshot is a second native call | `_one`, `_with_inject`, `_capture` |
| Safety | Session ask once; regex + `critical: true` for pay/send/purchase; lockscreen blocks; Jev may only **add** review | `action_is_critical`, `require_critical_review` |
| Human takeover | Disable physical mice (not keyboard-named devices); exclusive HUD keys; replay compositor binds; unlock pointer in `approvalWait` | `ComputerUse.qml`, `ComputerUseHud.qml` |
| Default model | `gemini-2.0-flash` — general chat, not a CU-trained toolset | `config/defaults/ai.js` |

---

## Gap analysis vs Codex-class computer use

Sources:

- **Public — Claude:** [Computer use tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool.md), [best practices](https://claude.com/blog/best-practices-for-computer-and-browser-use-with-claude) (1280×720, screenshot-pixel coords, `zoom`, batched member tools, screenshot after a batch).
- **Public — Codex / ChatGPT CU:** [ChatGPT Computer Use](https://learn.chatgpt.com/docs/computer-use) (macOS Screen Recording + Accessibility; Windows takes the foreground; app allowlist). Codex harness loop: [Unrolling the Codex agent loop](https://openai.com/index/unrolling-the-codex-agent-loop/).
- **Public / third-party — open-codex-computer-use:** [On Computer Use](https://web.navan.dev/posts/2026-08-19-on-computer-use.html) (`get_app_state` = screenshot **and** AX tree; semantic click prefers `element_index`; post-action state recapture; Windows UIA / Linux AT-SPI / macOS AX). Treat as a description of that runtime, not an official OpenAI spec.
- **Inferred:** Codex macOS background cursor (separate from the user’s pointer) from the Codex CU demo talk. Not independently re-verified here.

### Clicking / pointing / dragging

| | Ambxst (confirmed) | Best-of-breed (public / inferred) |
|---|---|---|
| Semantic click | AT-SPI `DoAction` only if the **first** action name is click/press/toggle | AX/UIA InvokePattern **or** AX press; richer action vocabulary |
| Pixel click | Image pixels → logical via last shot; **refused** without a shot | Screenshot-pixel coords with a stable full-display space |
| Drag | ydotool button-down, eased move, button-up | Interpolated motion; often compositor/CGEvent, not uinput |
| Missed clicks | No hit-test, no post-click observe, no bounds fallback | Recapture state; tree `frame` lets the runtime click the box if Invoke fails |

Ambxst already prefers `element_index`. It then throws away the information
that would make the fallback cheap: `slim_node` drops `bounds`, and click
does not use `GetExtents` when `DoAction` is absent. Pixel path then forces
a grim round-trip. Codex-class runtimes keep bounds on the runtime side even
when the model only sees an index.

Cursor easing is the wrong place to spend 80–350 ms. Codex’s flying cursor
**(inferred)** is a **display** cursor, not the targeting loop. Ambxst eases
the real compositor cursor **before** the click, via 4–8 `hyprctl` processes.

### Typing / chords / IME

wtype is the correct Wayland text path. It still bypasses IME composition
(CJK, dead keys). ydotool `type` is worse (uinput keycodes). `sendshortcut`
is Hyprland-only and the right call for Ctrl+C / Ctrl+Enter; Niri/Mango
cannot do it through axctl.

After every `type`, `focused_element()` walks AT-SPI again (up to 10 s,
400 nodes). That is a reliability check implemented as a second full
snapshot. Codex-class loops recapture **once** after the action, not a
second unrelated tree walk.

### Scrolling, focus, multi-monitor

Scroll is ydotool wheel ticks (`pages * 5`), optionally after moving the
cursor. No AX ScrollPattern, no DOM `scrollIntoView`, no “until element
visible”.

Focus is one of the stronger pieces: address/pid/class/title, terminal
`/proc` enrichment, verified flag, settle sleep. Multi-monitor origin +
per-output scale in `preview_to_logical` is correct and tested.

Still Hyprland-first. Window crop uses compositor logical `at`/`size`
times **one** monitor scale. Mixed-scale, XWayland, and off-screen windows
are flagged (`window_off_screen`) but not repaired.

### Screenshots / observation loop

This is the largest effectiveness gap.

Claude **(public):** dedicated `screenshot` and `zoom`; coordinates stay in
**full-screenshot** space after zoom; batches usually end with a screenshot;
the harness can attach one if the model forgets.

Codex-class **(public, open-codex-computer-use):** `get_app_state` returns
pixels **and** tree together; after an act, state is collected again because
the old tree is stale.

Ambxst **(confirmed):**

1. Snapshot has no image (good for tokens; bad when `tree_usable` is false,
   which is common on Linux).
2. Mutating actions return `{status: ok}` with no new tree and no pixels.
3. The model must spend a whole inference to ask for `screenshot` or
   `snapshot` again.
4. JPEG 1280/q70, no zoom. Dense UI (settings, IDE, 4K) becomes unreadable
   **and** click targets shrink to a few pixels.
5. Only two images survive in history; older visual context is dropped.
6. HUD hide is 50 ms opacity, not compositor `no_screen_share` as the
   capture path — `applyNoscreenshare()` sets the layerrule then
   `noscreenshare = false`. Doctor reports `hide_for_capture: true`.

Tree-first is the right default. Missing **forced observe after mutate** is
not.

### Action representation

Hybrid is the competitive design. Ambxst is halfway there:

- Good: index-based clicks, slim tree, `tree_usable` hint, skill says
  “screenshot only if the tree is empty”.
- Weak: no DOM/CDP browser path (Claude splits **browser use** from
  computer use **(public)**; Codex ships a browser extension **(public)**).
- Weak: public tree has no `frame`; model cannot point at “the node whose
  box is here”.
- Weak: one fat `use_computer` tool with 16 actions vs Claude’s 17 **member**
  tools the model was trained on **(public)**. Generic function-calling
  against `gemini-2.0-flash` will lose to a CU-trained toolset even with
  identical backends.

### Latency and round-trips

A routine pixel click, today:

1. Model tool call (LLM round-trip).
2. Native `gate`.
3. Optional native `focus` + ≤1 s poll + 50 ms settle.
4. `cursor_position` subprocess + 4–8 `hyprctl dispatch` + up to 350 ms ease.
5. ydotool click.
6. Next model call with **no new pixels**.

A screenshot:

1. Native `gate`.
2. Native `use_computer` screenshot.
3. Optional focus + 80 ms `raiseTimer`.
4. 50 ms HUD hide.
5. grim PNG to `/tmp`.
6. `convert -crop` or `cp`.
7. Python ImageMagick resize/jpeg.
8. base64 on the tool result, then another LLM call.

Claude **(public)** runs click → type → screenshot as **one model response**
(sequential batch). Ambxst `actions[]` exists but is ignored whenever
`action` is set, and is documented as non-visual (key/type only).
`use_computer` is not in `PARALLEL_TOOLS` (correct — mutations must be
serial) but there is no **ordered batch** path that ends with observe.

### Reliability (Wayland)

Strong instincts, fragile stack:

- Aim with compositor cursor, not ydotool absolute: **correct** on Wayland.
- ydotool for buttons: works only if ydotoold + `/dev/uinput` are alive;
  doctor knows this (`can_click`).
- Exclusive HUD keyboard vs wtype: `inject_begin` drops exclusive focus so
  typing can land. That is a race with the 15 s inject watchdog and with
  compositor binds.
- AT-SPI on Linux is optional in practice. GTK/Qt need
  `GTK_A11Y=atspi` / `QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1` **and a restart**.
  Chromium, Electron, games, canvases, and many Wayland clients will yield
  `tree_usable: false`. Codex on macOS has a much denser AX tree
  **(public: OS permissions model)**. Treating AT-SPI as equivalent is a
  dead end.
- XWayland windows are labeled, not specially clicked.
- IME: unsolved.
- Session teardown on `done` means a follow-up “now click Submit” pays
  another grant + doctor + AT-SPI launch.

### Safety / permissions

Better than a raw xdotool demo; weaker than ChatGPT CU **(public)**:

| Ambxst | Codex / ChatGPT CU (public) | Claude (public) |
|---|---|---|
| Default Never; session grant | Plugin install + OS permissions + **per-app** allowlist | VM/container advice; prompt-injection classifiers on screenshots; confirm consequential actions |
| Regex on labels (`Pay now`, `Send`, Ctrl+Enter) + optional Jev **add-only** | App-scoped + sandbox for files/shell | Classifier steers to confirmation |
| Lockscreen blocks; user steer blocks mutate | Windows: foreground takeover; macOS: can run in background **(docs)** | Isolate from credentials |

Regex critical-action detection is bypassable (icon-only buttons, localized
labels, “Confirm” that is not in the list). There is no app allowlist, no
domain allowlist for the driven browser, no screenshot prompt-injection
classifier.

### HUD / takeover

Recently fixed and **not** the main capability limiter: exclusive keys,
bind replay, pointer unlock on approval, double-Esc, Super+A, lock end,
`cu-stop` IPC. Two capability side-effects remain:

1. Grab ends on turn `done`, so the agent cannot keep the desktop across
   a user “yes, continue”.
2. Physical mice are disabled instead of a virtual pointer. That is a
   safety/UX choice that also prevents Codex-style “agent clicks in the
   other app while I type” **(inferred from Codex CU demo)**.

---

## What is already strong

- **Hybrid intent.** Tree-first snapshot, pixel fallback, JPEG-space
  clicks with real scale/crop/origin math. This is the Codex-shaped
  design, not 2024 screenshot-only CU.
- **Coordinate honesty.** Tests lock `preview_to_logical` and “pixel click
  requires last shot”. Claude’s whole “don’t let the API resize behind
  you” lesson is already applied.
- **Fail-closed policy.** Default Never; tools not advertised; lockscreen
  and steer gates; critical path still asks after grant.
- **Doctor.** Binary/socket/uinput/AT-SPI/grim probes before the model
  flails.
- **Focus + window targeting.** Addresses as strings, terminal `/proc`,
  verified focus. Matches axctl’s “IDs are strings” rule.
- **Wayland-correct aiming.** Compositor `movecursor`, not absolute
  ydotool. Documented in `input.py`.
- **Shell-native HUD.** Hide-for-capture, frame ring, steer box not in
  the grim. Capability aside, this is a real desktop product, not a
  VNC bot.

## What is mediocre

- Observation: no recapture after mutate; no zoom; JPEG 1280/q70 as the
  only visual; two-image history.
- Round-trips: native gate + grim + convert + ImageMagick + LLM, per
  step; `actions[]` too weak to replace Claude batches.
- AT-SPI used as if it were macOS AX: 10 s D-Bus BFS, 150 nodes to the
  model, bounds dropped, extra full walk after `type`.
- Input split-brain: hyprctl cursor, ydotool buttons, wtype text,
  sendshortcut chords. Each has a different failure mode.
- Session = one turn. Competitive CU is a **held desktop**, not a grant
  that dies when the model says hello.
- Model: generic Spotlight model, default Flash, generic JSON tool.
  Backends cannot outrun that.
- Hyprland-only cursor/shortcut in axctl; Niri/Mango are stubs.
- Safety: label regex, no app allowlist, no injection classifier.

## What is a dead end

Do not invest further in these as the **core** loop:

1. **Eased compositor cursor as targeting.** Teleport to the click;
   animate a HUD cursor if you want theatre.
2. **AT-SPI-only semantic UI.** Keep it as a fast path for GTK/Qt. Linux
   CU that works in browsers and Electron needs DOM/CDP or pixels+zoom.
3. **ydotool absolute coordinates.** Already rejected; stay rejected.
4. **Per-action native `gate` as a QML round-trip.** Gate in the Python
   process against a cached session flag; QML pushes steer/lock/end
   events.
5. **Re-grant every turn.** User already approved the desktop.
6. **Copying Claude “screenshot every action” blindly.** Tokens and grim
   will drown Flash. Recapture **cheaply** (tree, or one JPEG) from the
   **harness**, don’t make the model ask.
7. **Disabling the user’s mice as the isolation model.** Fine as a v1
   safety lock. Not how you get background CU. Virtual pointer /
   `zwlr_virtual_pointer` / Hyprland virtual device is the path.

---

## Ranked recommendations

Impact: **E**ffectiveness (task success), **F**fficiency (latency/tokens),
**R**eliability. Effort is engineering scope, not calendar time.

### P0 — harness, not HUD (quick wins)

1. **Harness-side observe after mutate** (E/F, small)
   After click/type/key/scroll/drag, default `observe: "tree"`. If
   `tree_usable` is false, take one JPEG. Stop making the model spend an
   inference to see whether the click landed.
   Files: `scripts/ai/tools/computer_use.py`, skill text.

2. **Teleport cursor; drop targeting ease** (F/R, tiny)
   `movecursor` one `hyprctl`/`axctl` dispatch. Keep a 30 ms settle if
   needed. Optional HUD cursor for humans.
   File: `scripts/ai/computer_use/input.py`.

3. **Click `element_index` via cached bounds when `DoAction` is missing** (E/R, small)
   Runtime already has `bounds` on the fat tree. Map extents → logical →
   ydotool. Do **not** dump bounds into the model payload if you want to
   keep tokens slim.
   Files: `atspi.py`, `computer_use.py` click path.

4. **Stop the post-`type` full AT-SPI walk** (F, tiny)
   Use `focused_from_nodes` on the last snapshot, or skip. The current
   `focused_element()` is a hidden 10 s worst case.
   File: `computer_use.py` `action == "type"`.

5. **Auto-screenshot when snapshot `tree_usable` is false** (E, tiny)
   One extra grim only when AT-SPI is empty. Skill already tells the
   model to do this; the harness should.

6. **Ordered action batch that may end with observe** (E/F, small)
   Honor `actions: [{click},{type},{screenshot}]` even with a dummy
   top-level `action`, or split Claude-style member tools later. Serial,
   stop on first error.
   File: `UseComputerTool.execute`.

### P1 — observation quality (structural-ish)

7. **`zoom` / region capture in last-shot coordinate space** (E, medium)
   Claude’s rule **(public):** zoom image for reading; clicks stay in the
   **full** screenshot grid. Ambxst already has crop math. Add
   `action=screenshot` + `geometry` that **does not** rewrite
   `computer_use_last_shot` origin, or store a separate `zoom` payload.

8. **`get_app_state` native bundle** (F, medium)
   One QML hop: windows + focus + optional grim path. Python attaches
   tree + JPEG. Today snapshot is `get_windows` native + AT-SPI local +
   optional second native grim.

9. **Cache session flags in Python** (F, small)
   Push `user_control` / `steer_open` / `locked` on change. Skip native
   `gate` on every keystroke. Keep QML as source of truth for HUD.

10. **Wait-until** (E/F, small)
    Replace blind sleep with: poll tree hash or focused role, or grim
    pixel-hash, timeout ≤5 s, return the new state. Claude still has
    `wait` **(public)**; the winning harness observes at the end.

11. **grim JPEG / wlr-screencopy; skip double ImageMagick** (F, medium)
    grim can emit jpeg. Crop in one convert, or capture the window
    geometry in grim (`-g`) instead of full output + crop.

### P2 — competitive capability (structural)

12. **Session lives across turns until Stop / lock / timeout** (E, medium)
    User grant is for the **task**, not the first assistant message.
    Keep mice locked, keep last_shot and nodes. Re-ask only for
    critical actions. This is the single biggest product mismatch with
    “the agent is using my computer”.

13. **Browser path** (E, large)
    CDP or a Chrome extension for DOM, network, and
    `scrollIntoView`. Desktop CU stays for native apps. Claude and
    Codex both split this **(public)**. Do not scrape the web with
    grim+scroll when `exa_search` / curl already exist (skill already
    says this — enforce it in the tool description).

14. **Virtual pointer** (E/R, large)
    `zwlr_virtual_pointer_v1` or a Hyprland virtual mouse so physical
    devices stay enabled and the agent has its own cursor. Then
    background CU is possible. Until then, disabling mice is acceptable
    safety.

15. **App allowlist** (R, medium)
    ChatGPT CU **(public)** gates by app. Ambxst should at least
    constrain `focus`/`click` to the focused window at grant time plus
    an explicit extra-app ask.

16. **Provider-native computer toolset when the model is Claude** (E, medium)
    If `provider == anthropic`, advertise `computer_toolset_20260801`
    member tools and map them onto the existing backends. Do not expect
    Flash + a 16-way enum to match Opus+toolset.

17. **axctl cursor/shortcut for Niri, or document Hyprland-only** (R, medium)
    Stubs that return `ErrNotSupported` plus a ydotool fallback that
    cannot move the cursor absolutely = silent failure on Niri/Mango.

18. **IME / text-input** (R, medium)
    Prefer clipboard-paste or `text-input-v3` for non-ASCII. Keep wtype
    for ASCII and shortcuts.

### P3 — safety that matches the capability

19. Prompt-injection stance on screenshots (warn + force `critical`
    ask when the shot contains “ignore previous” / payment UI). Claude
    classifiers **(public)** are the bar; a small local regex/Jev on
    OCR or the tree is a start.
20. Do not send CU screenshots to Jev (already in the Jev plan). Keep
    that non-goal.

---

## Explicit non-goals / what not to copy blindly

- **Do not** screenshot after every action by default. Recapture from
  the harness; prefer tree when `tree_usable`.
- **Do not** switch to X11 xdotool. The compositor-cursor + ydotool-button
  split is the Wayland-correct split.
- **Do not** expose full AT-SPI dumps (object paths, 1000 nodes, raw
  text) to the model. Slim tree is right; bounds can stay runtime-only.
- **Do not** rebuild the HUD/takeover model unless a P2 virtual pointer
  needs it.
- **Do not** use Jev to *clear* a critical action (`require_critical_review`
  already add-only).
- **Do not** aim for macOS-style background CU before a virtual pointer
  exists; on Windows, even ChatGPT CU takes the foreground **(public)**.
- **Do not** treat axctl as a CU runtime. It is window/workspace IPC. CU
  input and a11y belong in Ambxst until a dedicated input protocol exists.
- **Do not** train or fine-tune a model in this repo. Pick CU-capable
  models and native toolsets; the harness is the lever we own.

---

## Evidence

Computer-use unit tests in this checkout (`python3 tests/test_scripts.py
TestComputerUse`): 19 tests, OK. They pin policy advertising, critical
asks after grant, JPEG/scale caps, compact tree, pixel-shot requirement,
preview→logical mapping, snapshot-without-image, cursor easing, and steer
blocking. They do **not** cover grim, ydotool, AT-SPI against a live bus,
or Niri.

Primary files:

- `scripts/ai/tools/computer_use.py`
- `scripts/ai/computer_use/{input,coords,screenshot,atspi,windows,doctor}.py`
- `scripts/ai/agent.py` (prune images, no iter cap, end grant)
- `modules/services/ComputerUse.qml`
- `modules/services/Screenshot.qml` (`captureSilent`)
- `modules/services/ai/NativeToolBridge.qml`
- `modules/widgets/assistant/ComputerUseHud.qml`
- `assets/ai/skills/computer-use/SKILL.md`
- axctl: `pkg/ipc/hyprland/client.go` vs niri/mango `ErrNotSupported`
