# Security audit: Ambxst 1.3.3 vs Ambxst[+]

**Date:** 2026-09-19  
**Subject:** `git-napkin/ambxst-plus` (`main`, version `1.1.5`)  
**Compared to:** Axenide/Ambxst tag [1.3.3](https://github.com/Axenide/Ambxst/releases/tag/1.3.3) (SECURITY UPDATE, 2026-09-09)  
**Related repo in this environment:** `git-napkin/axctl-plus` (flake input `github:git-napkin/axctl-plus/dev`)

This is an analysis-only document. No behavior was changed.

Upstream GitHub release notes for 1.3.3 are empty besides the changelog link. The security work is in three same-day commits on that tag:

| Upstream commit | What it fixed |
|---|---|
| [`1d7ef425`](https://github.com/Axenide/Ambxst/commit/1d7ef4257488442f4d4dc3f10c0140bf47a7ce87) `fix(network): pass SSID to nmcli via argv instead of shell interpolation` | High: malicious SSID executed as the user |
| [`0a4c183f`](https://github.com/Axenide/Ambxst/commit/0a4c183f4f0b14b1ad855a2c1bce61ff947cbcca) `fix(ipc): move keybind FIFO to the per-user runtime dir` | Local-user FIFO squat in `/tmp` |
| [`0c6bc7aa`](https://github.com/Axenide/Ambxst/commit/0c6bc7aad25b008c0bcf9d1db7d4ed7c4f8d2513) `fix(compositor): resolve axctl socket in the runtime dir` | Local-user axctl socket squat in `/tmp` |

Axenide/axctl additionally checks `SO_PEERCRED` on every accepted connection (`pkg/server/peercred_linux.go`, called from `handleConnection`). Clipboard injection was largely removed by the 1.3.2 Go rewrite ([`c581b36b`](https://github.com/Axenide/Ambxst/commit/c581b36b) `feat(clipboard): encrypted stores…` / tag 1.3.2) and then kept out of shell in 1.3.3 by not restoring the old `scripts/clipboard_*.sh` path.

| # | Bug | Verdict on Ambxst[+] |
|---|---|---|
| 1 | Command injection via Wi-Fi SSID (High) | **Not vulnerable** |
| 2 | IPC squatting (FIFO + axctl socket + peer creds) | **Partial** (FIFO) / **Vulnerable** (`axctl-plus`) |
| 3 | Clipboard injection vectors | **Partial** |

---

## 1. Command injection via Wi-Fi SSID — **Not vulnerable**

### Upstream bug and fix

Before 1.3.3, connecting with a password ran:

```go
cmd := exec.Command("bash", "-c", `nmcli connection modify "`+p.SSID+`" wifi-sec.psk "$PASSWORD"`)
```

A broadcast SSID such as `";touch /tmp/pwned;#` was interpolated into a shell and ran as the user. The fix switched to argv:

```go
_ = exec.Command("nmcli", "connection", "modify", p.SSID, "wifi-sec.psk", p.Password).Run()
// then:
exec.Command("nmcli", "dev", "wifi", "connect", p.SSID)
```

### Ambxst[+] paths

Ambxst[+] has no Go network daemon. All connect/password work is in QML.

`NetworkService.connectToWifiNetwork` and `changePassword` already pass SSID and password as `Process.command` **argv arrays**, not a shell string:

```137:176:modules/services/NetworkService.qml
    function connectToWifiNetwork(accessPoint: WifiAccessPoint): void {
        // ...
        runAsync(["nmcli", "dev", "wifi", "connect", accessPoint.ssid]).then(() => {
            // ...
        }).catch(e => {
            if (e.includes("Secrets were required")) {
                accessPoint.askingPassword = true;
            }
            // ...
        });
    }

    function changePassword(network: WifiAccessPoint, password: string): void {
        network.askingPassword = false;
        isUpdating = true;
        runAsync(["nmcli", "connection", "modify", network.ssid, "wifi-sec.psk", password]).then(() => {
            connectToWifiNetwork(network);
        })
```

`runAsync` feeds that array into `Quickshell.Io.Process.command` with no `sh -c` wrapper. The dashboard UI (`WifiNetworkItem.qml`) only calls these two functions; it never shells SSID/password.

Other `nmcli` calls in the same file are also argv (`radio wifi`, `dev wifi list`, `connection down`, `nmcli monitor`, network listing). The one `sh -c` in this module is a **hardcoded** status pipeline (device state / connectivity / radio / active name). It does not interpolate SSID or password.

Repo-wide search found no `bash -c` / `sh -c` construction that concatenates an SSID.

### Recommendation

None for this bug. Optional: add a contract test like upstream `TestConnectNeverInterpolatesSSIDIntoShell` that asserts `NetworkService.qml` still uses argv arrays (the fork already does this style of source assertion in `tests/test_scripts.py`).

---

## 2. IPC squatting — **Partial** (Ambxst[+] FIFO) / **Vulnerable** (`axctl-plus`)

Two distinct channels: the Ambxst[+] keybind FIFO, and the `axctl` / `axctl+` JSON-RPC socket. Axctl-plus is in this environment (`/agent/repos/axctl-plus`, flake input `github:git-napkin/axctl-plus/dev`).

### 2a. Keybind FIFO — **Partial** (already out of hardcoded `/tmp`, weaker fallback)

Upstream 1.3.3 moved `GlobalShortcuts.qml` from `/tmp/ambxst_ipc.pipe` to `${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/ambxst_ipc.pipe`. `/tmp` is world-shared; the sticky bit lets another local account plant a FIFO of that name and either block Hyprland keybinds or impersonate the shell.

Ambxst[+] already uses the per-user runtime dir:

```15:37:modules/services/GlobalShortcuts.qml
    readonly property string ipcPipe: (Quickshell.env("XDG_RUNTIME_DIR") || "/tmp") + "/ambxst+_ipc.pipe"
    // ...
        command: ["bash", "-c",
            "runtime=\"${XDG_RUNTIME_DIR:-/tmp}\"; " +
            "pipe=\"$runtime/ambxst+_ipc.pipe\"; " +
            "mkdir -p \"$runtime\"; " +
            "if [ ! -p \"$pipe\" ]; then rm -f \"$pipe\"; mkfifo -m 600 \"$pipe\"; fi; " +
            "chmod 600 \"$pipe\" 2>/dev/null || true; " +
            "while true; do cat \"$pipe\" || sleep 0.2; done"
        ]
```

`cli.sh` write path matches:

```253:255:cli.sh
write_ipc_pipe() {
	local payload="$1"
	local pipe="${XDG_RUNTIME_DIR:-/tmp}/ambxst+_ipc.pipe"
```

`scripts/colorpicker.py` uses the same `XDG_RUNTIME_DIR` / `/tmp` join. `tests/test_scripts.py::test_ipc_pipe_uses_runtime_dir` already forbids a hardcoded `PIPE="/tmp/ambxst+_ipc.pipe"`.

Gaps versus 1.3.3:

1. **Fallback is `/tmp`, not `/run/user/$UID`.** If `XDG_RUNTIME_DIR` is unset (some compositor sessions), the FIFO lands back in the shared namespace. Upstream’s fallback is still a per-user directory.
2. **Existing-FIFO reuse without ownership check.** `if [ ! -p "$pipe" ]; then rm -f; mkfifo -m 600; fi` keeps an already-present FIFO. On the `/tmp` fallback, a second local user can plant `ambxst+_ipc.pipe` first; the shell will `cat` their pipe. `chmod 600 … || true` does not fail closed.
3. **No unlink-if-not-ours.** Upstream still `rm -f` on start (they recreate every launch). Recreating is safer than trusting a leftover node.

On a normal systemd user session (`XDG_RUNTIME_DIR=/run/user/$UID`, mode `0700`) this is equivalent to upstream for the FIFO.

### 2b. axctl / axctl+ socket — **Vulnerable** (lives in `axctl-plus`, not this tree)

Upstream Ambxst 1.3.3 looks up `$XDG_RUNTIME_DIR/axctl.sock` first. Current Axenide/axctl `defaultSocketPath()` is:

```text
AXCTL_SOCKET, else $XDG_RUNTIME_DIR/axctl.sock, else /tmp/axctl-<uid>.sock
```

and `handleConnection` starts with `verifyPeerUID(conn)` (`SO_PEERCRED`, reject other UIDs).

`axctl-plus` still hardcodes the shared `/tmp` path and does **not** verify peer credentials:

```170:172:/agent/repos/axctl-plus/main.go
func daemonSocketPath() string {
	return fmt.Sprintf("/tmp/axctl-%d.sock", os.Getuid())
}
```

```167:181:/agent/repos/axctl-plus/pkg/server/server.go
func (s *Server) Start() error {
	_ = os.Remove(s.socketPath)
	l, err := net.Listen("unix", s.socketPath)
	// ...
		conn, err := l.Accept()
		go s.handleConnection(conn)
```

`handleConnection` has no `verifyPeerUID`. Grep over `axctl-plus` finds no `SO_PEERCRED` / `GetsockoptUcred` / `Ucred`.

Impact on a multi-user machine:

- Another UID can create `/tmp/axctl-<victim-uid>.sock` first. Sticky-bit `/tmp` prevents the victim from unlinking it. `net.Dial` then either talks to the attacker’s daemon (`Error: axctl daemon is already running`) or `Listen` fails — **DoS / impersonation**.
- `System.Execute`, `Config.BindKey`, `Config.RawBatch`, window/workspace control are on that socket. Without peer creds, a successful squat is compositor-level RCE as the victim.

Ambxst[+] itself never hardcodes the axctl socket; it execs `axctl` (`AxctlService.qml`, `cli.sh screen`, etc.). Fixing this belongs in **axctl-plus**, then bumping the flake input.

Related `/tmp` sockets **not** in the 1.3.3 notes (wallpaper / screenshot; out of scope for this PR):

- `/tmp/ambxst+_mpv_socket_${MONITOR}` (`modules/widgets/dashboard/wallpapers/`)
- `/tmp/ambxst+_freeze`, `/tmp/ambxst+_crop.png`, `/tmp/image.png`

### Recommendation

**P0 — axctl-plus (separate PR):**

1. Port Axenide/axctl `defaultSocketPath()` (`AXCTL_SOCKET` → `$XDG_RUNTIME_DIR/axctl.sock` → last-resort `/tmp/axctl-<uid>.sock`).
2. Port `pkg/server/peercred_linux.go` + `peercred_other.go` and call `verifyPeerUID` at the top of `handleConnection`.
3. `chmod` the socket to `0600` after listen (runtime dir is already `0700`).
4. Keep daemon and CLI on the same helper so Ambxst[+] needs no QML change.

**P1 — Ambxst[+] FIFO:**

1. Change the fallback from `/tmp` to `/run/user/$(id -u)` (QML, `cli.sh`, `colorpicker.py`).
2. Before using an existing FIFO: require it is a fifo, owned by `$UID`, mode `0600`; otherwise `rm -f` and recreate. Fail closed if `chmod` fails.
3. Tighten `test_ipc_pipe_uses_runtime_dir` so `${XDG_RUNTIME_DIR:-/tmp}` is no longer accepted as the only contract.

---

## 3. Clipboard injection vectors — **Partial**

### What 1.3.2 / 1.3.3 did

1.3.2 replaced `scripts/clipboard_*.sh` + sqlite CLI with a Go store (`backend/pkg/svc/clipboard/`). 1.3.3 left that Go path in place. Watcher still uses `wl-paste --watch`, but mime detection, hashing, and insert are `exec.Command` argv + parameterized SQL — clipboard bytes never become a shell string.

Ambxst[+] still uses the pre-daemon pipeline: `clipboard_watch.sh` → `clipboard_check.sh` → `clipboard_insert.sh` → `ClipboardService.qml` / `ClipboardTab.qml`.

### Already mitigated (not the original “slurp clip into `sh -c`” bug)

Insert path pipes content on **stdin** into a temp file and uses sqlite `readfile()`, instead of `CONTENT=$(cat)`:

```27:53:scripts/clipboard_insert.sh
# Preview without slurping the full clip into a shell variable
if [ "$IS_IMAGE" = "1" ]; then
	printf '%s' "[Image]" >"$PREVIEW_FILE"
else
	head -c 97 "$CONTENT_FILE" >"$PREVIEW_FILE"
	# ...
fi
sqlite3 "$DB_PATH" <<EOSQL
# ...
    readfile('${PREVIEW_FILE}'),
    readfile('${CONTENT_FILE}'),
```

`tests/test_scripts.py::test_clipboard_insert_skips_full_slurp` locks that in.

`clipboard_watch.sh` drains `wl-paste --watch` stdin (`cat >/dev/null`) and invokes the check script via `"$0" "$1" "$2" "$3"` (positional args, not interpolated clip bytes).

Text restore uses argv when content is already in QML:

```564:565:modules/widgets/dashboard/clipboard/ClipboardTab.qml
                        copyProcess.command = ["wl-copy", root.currentFullContent];
```

AI `copy_to_clipboard` is the same pattern (`NativeToolBridge.qml`: `["wl-copy", copyProc.text]`). OCR/QR pipe via `echo "$TEXT" | wl-copy` with the variable quoted.

So **clipboard payload as a command-injection string** is largely gone from the insert + default text-copy path.

### Remaining vectors

**A. MIME type interpolated into SQL (clipboard-controlled).**  
`clipboard_check.sh` takes image MIME from `wl-paste --list-types | grep '^image/'` and passes it as argv to `clipboard_insert.sh`, which then drops it into the SQL heredoc unescaped:

```50:51:scripts/clipboard_insert.sh
    '${HASH}',
    '${MIME_TYPE}',
```

A Wayland client in the session can advertise a MIME type such as  
`x', 'preview', 'full', 0, '', 0, 0, 0, 0, 0); UPDATE clipboard_items SET alias='INJECTED' WHERE 1; --`.

Reproduced 2026-09-19 against an isolated temp copy of `clipboard_init.sql`: a seed row (`id=1`, `mime_type=text/plain`) had `alias` flipped to `INJECTED`, and a second row with `mime_type=x` was inserted. HASH / paths from `mktemp` are not attacker-chosen; MIME is.

**B. Restore / query still `sh -c` + string-concatenated SQL.**  
`ClipboardTab.copyToClipboard` for images and file URIs, and the text fallback, build a shell:

```554:568:modules/widgets/dashboard/clipboard/ClipboardTab.qml
                    copyProcess.command = ["sh", "-c", "cat '" + item.binaryPath.replace(/'/g, "'\\''") + "' | wl-copy --type '" + item.mime.replace(/'/g, "") + "'"];
                } else if (item.isFile) {
                    copyProcess.command = ["sh", "-c", "sqlite3 '" + ClipboardService.dbPath + "' \"SELECT full_content FROM clipboard_items WHERE id = " + itemId + ";\" | tr -d '\\r' | wl-copy --type text/uri-list"];
                } else {
                    // ...
                        copyProcess.command = ["sh", "-c", "sqlite3 '" + ClipboardService.dbPath + "' \"SELECT full_content FROM clipboard_items WHERE id = " + itemId + ";\" | wl-copy"];
```

Image `binaryPath` is quote-escaped; MIME only has `'` stripped and is then wrapped in single quotes (metacharacters are literal). `itemId` is assumed numeric from sqlite. This is not the original “paste into `eval`” bug, but it is still a shell/SQL concatenation surface. Prefer `["wl-copy", "--type", mime]` with stdin from a file, or `sqlite3` argv + pipe, with `id` constrained to `/^[0-9]+$/`.

**C. `ClipboardService.qml` SQL via `sh -c`.**  
`getFullContent`, `deleteItem`, `togglePin`, `setAlias`, `reorderItem` concatenate `id` (and for alias, a partially escaped string) into `sh -c`. `setAlias` SQL-escapes `'` → `''` but embeds the alias in a **double-quoted** shell string, so `` ` `` / `$()` / `"` in an alias are command injection. Alias is typed in the UI (not clip bytes), but it is the same class of bug 1.3.3 closed by leaving sqlite.

**D. `clearClipboardIfMatches`.**  
Hashes clipboard types in a `sh -c` script. Clip bytes are quoted (`echo -n "$CONTENT"`). `deletedHash` is interpolated into that script; it should be an md5 hex from the DB. Secondary if A poisons hashes.

### Recommendation

Do **not** port the Go clipboard daemon (out of architecture scope; see `docs/upstream-gap-analysis.md`). Stay on bash/QML and close the remaining holes:

1. **P1:** Bind MIME (and HASH / BINARY_PATH) with sqlite parameters or a strict allow-list (`image/png|jpeg|gif|webp|bmp|svg+xml`). Never splice `wl-paste --list-types` into SQL.
2. **P1:** Restore clipboard items with argv only: `wl-copy --type …` + file/stdin; `sqlite3 "$db" "SELECT … WHERE id = ?"` with a numeric id check. Delete the `sh -c` copy branches.
3. **P2:** Same for `ClipboardService.qml` mutations: `sqlite3` argv + bound parameters; reject non-numeric ids; pass alias via env or a temp file, never a double-quoted `sh -c`.
4. Optional: add tests that a MIME / alias / SSID-like payload does not appear in a constructed shell string (source contracts, plus a `clipboard_insert.sh` sqlite round-trip).

---

## Ranked remediation

| Rank | Where | Work | Closes |
|---|---|---|---|
| **P0** | `axctl-plus` | Runtime-dir socket + `SO_PEERCRED` on accept (copy Axenide/axctl `defaultSocketPath` / `peercred_*.go`). Then bump this flake’s `axctl` input. | 2b — local-user compositor IPC squat |
| **P1** | `scripts/clipboard_insert.sh` | Stop interpolating MIME/paths into SQL | 3A |
| **P1** | `ClipboardTab.qml` `copyToClipboard` | Argv `wl-copy` / sqlite; drop `sh -c` | 3B |
| **P1** | `GlobalShortcuts.qml`, `cli.sh`, `colorpicker.py` | Fallback `/run/user/$UID`; ownership check before using a leftover FIFO | 2a |
| **P2** | `ClipboardService.qml` | Argv sqlite; alias not in `sh -c` | 3C |
| **P3** | Wallpaper / screenshot `/tmp` sockets and images | Move under `$XDG_RUNTIME_DIR` (separate from wallpaper-port work) | related squat, not a 1.3.3 item |
| — | Wi-Fi SSID | No code change | 1 already equivalent |

---

## Method notes

- Read Ambxst[+] `NetworkService.qml`, `WifiNetworkItem.qml`, `GlobalShortcuts.qml`, `cli.sh`, `ClipboardService.qml`, `ClipboardTab.qml`, `scripts/clipboard_*.sh`.
- Read axctl-plus `main.go` `daemonSocketPath` and `pkg/server/server.go` `Start` / `handleConnection`.
- Compared to Axenide/Ambxst 1.3.3 commits above, Axenide/axctl `defaultSocketPath` + `verifyPeerUID`, and upstream `backend/pkg/svc/clipboard/watch.go`.
- Did not implement fixes in this change.
- Did not touch wallpaper-port work.
