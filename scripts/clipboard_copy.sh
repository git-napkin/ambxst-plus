#!/usr/bin/env bash
# Restore a clipboard history item to the Wayland clipboard.
# Paths, MIME, and ids are argv — not interpolated into a shell command string.
#
# Usage:
#   clipboard_copy.sh file <path> <mime>
#   clipboard_copy.sh db <db_path> <id> [mime]
set -euo pipefail

mode="${1:-}"
case "$mode" in
file)
	path="${2:-}"
	mime="${3:-application/octet-stream}"
	[ -n "$path" ] && [ -f "$path" ] || exit 1
	exec wl-copy --type "$mime" <"$path"
	;;
db)
	db="${2:-}"
	id="${3:-}"
	mime="${4:-text/plain}"
	[ -n "$db" ] || exit 1
	[[ "$id" =~ ^[0-9]+$ ]] || exit 1
	if [ "$mime" = "text/uri-list" ]; then
		sqlite3 "$db" ".timeout 5000" "SELECT full_content FROM clipboard_items WHERE id = ${id};" | tr -d '\r' | wl-copy --type text/uri-list
	else
		sqlite3 "$db" ".timeout 5000" "SELECT full_content FROM clipboard_items WHERE id = ${id};" | wl-copy --type "$mime"
	fi
	;;
*)
	echo "usage: $0 file <path> <mime> | $0 db <db> <id> [mime]" >&2
	exit 2
	;;
esac
