#!/usr/bin/env bash
# Insert clipboard item into database
# Usage: clipboard_insert.sh <db_path> <hash> <mime_type> <is_image> <binary_path> <size>
# Content is read from stdin
#
# Attacker-controlled strings (MIME from wl-paste --list-types, hash/path) are
# written to temp files and loaded with sqlite readfile() — never spliced into
# the SQL text.

set -euo pipefail

DB_PATH="$1"
HASH="$2"
MIME_TYPE="$3"
IS_IMAGE="$4"
BINARY_PATH="$5"
SIZE="${6:-0}"

if [[ ! "$IS_IMAGE" =~ ^[01]$ ]]; then
	echo "clipboard_insert: is_image must be 0 or 1" >&2
	exit 1
fi
if [[ ! "$SIZE" =~ ^[0-9]+$ ]]; then
	echo "clipboard_insert: size must be an integer" >&2
	exit 1
fi

CONTENT_FILE=$(mktemp)
PREVIEW_FILE=$(mktemp)
HASH_FILE=$(mktemp)
MIME_FILE=$(mktemp)
BINPATH_FILE=$(mktemp)
trap 'rm -f "$CONTENT_FILE" "$PREVIEW_FILE" "$HASH_FILE" "$MIME_FILE" "$BINPATH_FILE"' EXIT

cat | tr -d '\r' >"$CONTENT_FILE"
printf '%s' "$HASH" >"$HASH_FILE"
printf '%s' "$MIME_TYPE" >"$MIME_FILE"
printf '%s' "$BINARY_PATH" >"$BINPATH_FILE"

# Don't insert empty content for text items
if [ "$IS_IMAGE" = "0" ] && [ ! -s "$CONTENT_FILE" ]; then
	exit 0
fi

if [ "$IS_IMAGE" = "1" ]; then
	printf '%s' "[Image]" >"$PREVIEW_FILE"
else
	head -c 97 "$CONTENT_FILE" >"$PREVIEW_FILE"
	BYTES=$(wc -c <"$CONTENT_FILE")
	if [ "$BYTES" -gt 100 ]; then
		printf '...' >>"$PREVIEW_FILE"
	fi
fi

TIMESTAMP=$(date +%s)000

# Paths come from mktemp (no attacker control). Integers are validated above.
sqlite3 "$DB_PATH" <<EOSQL
.timeout 5000
BEGIN TRANSACTION;
INSERT INTO clipboard_items 
(content_hash, mime_type, preview, full_content, is_image, binary_path, size, pinned, display_index, created_at, updated_at) 
VALUES (
    readfile('${HASH_FILE}'),
    readfile('${MIME_FILE}'),
    readfile('${PREVIEW_FILE}'),
    readfile('${CONTENT_FILE}'),
    ${IS_IMAGE},
    readfile('${BINPATH_FILE}'),
    ${SIZE},
    0,
    0,
    ${TIMESTAMP},
    ${TIMESTAMP}
)
ON CONFLICT(content_hash) DO UPDATE SET
updated_at = ${TIMESTAMP},
display_index = 0;
WITH reindexed AS (
  SELECT id, ROW_NUMBER() OVER (ORDER BY updated_at DESC, id DESC) - 1 AS new_idx
  FROM clipboard_items WHERE pinned = 0
)
UPDATE clipboard_items SET display_index = (SELECT new_idx FROM reindexed WHERE reindexed.id = clipboard_items.id) WHERE pinned = 0;
COMMIT;
EOSQL
