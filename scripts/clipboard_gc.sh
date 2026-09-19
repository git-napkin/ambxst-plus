#!/usr/bin/env bash
# Remove orphaned clipboard binary files not referenced by the DB.
# Paths are argv / temp files — never interpolated into SQL.
# Usage: clipboard_gc.sh <db_path> <binary_data_dir>
set -euo pipefail

DB_PATH="${1:-}"
BIN_DIR="${2:-}"
[ -n "$DB_PATH" ] || exit 1
[ -d "$BIN_DIR" ] || exit 0

shopt -s nullglob
for f in "$BIN_DIR"/*; do
	[ -f "$f" ] || continue
	path_file=$(mktemp)
	printf '%s' "$f" >"$path_file"
	count="$(sqlite3 "$DB_PATH" ".timeout 5000" "SELECT COUNT(*) FROM clipboard_items WHERE binary_path = readfile('${path_file}');" || true)"
	rm -f "$path_file"
	if [ "${count:-1}" = "0" ]; then
		rm -f "$f"
	fi
done
