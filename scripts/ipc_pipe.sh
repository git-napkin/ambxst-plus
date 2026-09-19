#!/usr/bin/env bash
# Ensure and/or listen on the Ambxst[+] keybind FIFO.
# Lives in $XDG_RUNTIME_DIR (or /run/user/$UID), never shared /tmp.
# Fail closed if a leftover node is not a fifo owned by this user.
#
# Usage:
#   ipc_pipe.sh locate  print the pipe path (no create)
#   ipc_pipe.sh path    print the pipe path after ensuring it
#   ipc_pipe.sh listen  ensure, then cat the fifo forever
set -euo pipefail

uid="$(id -u)"
if [ -n "${XDG_RUNTIME_DIR:-}" ]; then
	runtime="$XDG_RUNTIME_DIR"
else
	runtime="/run/user/${uid}"
fi
pipe="${runtime}/ambxst+_ipc.pipe"

ensure_pipe() {
	mkdir -p "$runtime"
	if [ -e "$pipe" ]; then
		owner="$(stat -c '%u' "$pipe" 2>/dev/null || true)"
		if [ "$owner" != "$uid" ]; then
			echo "ipc_pipe: $pipe owned by uid ${owner:-unknown}, not ${uid}" >&2
			exit 1
		fi
		if [ ! -p "$pipe" ]; then
			rm -f "$pipe"
		fi
	fi
	if [ ! -p "$pipe" ]; then
		mkfifo -m 600 "$pipe"
	fi
	chmod 600 "$pipe" || {
		echo "ipc_pipe: chmod 600 failed for $pipe" >&2
		exit 1
	}
	owner="$(stat -c '%u' "$pipe" 2>/dev/null || true)"
	if [ "$owner" != "$uid" ] || [ ! -p "$pipe" ]; then
		echo "ipc_pipe: refusing to use $pipe" >&2
		exit 1
	fi
}

cmd="${1:-path}"
case "$cmd" in
locate)
	printf '%s\n' "$pipe"
	;;
path)
	ensure_pipe
	printf '%s\n' "$pipe"
	;;
listen)
	ensure_pipe
	while true; do
		cat "$pipe" || sleep 0.2
	done
	;;
*)
	echo "usage: $0 locate|path|listen" >&2
	exit 2
	;;
esac
