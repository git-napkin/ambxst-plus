"""Jaro-Winkler fuzzy matching and LLM-friendly apply errors."""

from __future__ import annotations

import re

LINE_NUM_PREFIX = re.compile(r"^(\s*)(\d+)\|(.*)$")
FUZZY_THRESHOLD = 0.85


def jaro_similarity(s1, s2):
    if s1 == s2:
        return 1.0
    len1, len2 = len(s1), len(s2)
    if len1 == 0 or len2 == 0:
        return 0.0
    match_distance = max(0, max(len1, len2) // 2 - 1)
    s1_matches = [False] * len1
    s2_matches = [False] * len2
    matches = 0
    for i in range(len1):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, len2)
        for j in range(start, end):
            if s2_matches[j] or s1[i] != s2[j]:
                continue
            s1_matches[i] = True
            s2_matches[j] = True
            matches += 1
            break
    if matches == 0:
        return 0.0
    transpositions = 0
    k = 0
    for i in range(len1):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1
    return (
        matches / len1 + matches / len2 + (matches - transpositions / 2) / matches
    ) / 3.0


def jaro_winkler(s1, s2, p=0.1):
    jaro = jaro_similarity(s1, s2)
    prefix = 0
    for a, b in zip(s1, s2):
        if a != b or prefix == 4:
            break
        prefix += 1
    if jaro > 0.7:
        return jaro + prefix * p * (1.0 - jaro)
    return jaro


def remove_extra_line_num_prefix(text):
    first_num = None
    out = []
    parts = text.splitlines(True)
    if not parts and text:
        parts = [text]
    for line in parts:
        ended = line.endswith("\n")
        body = line[:-1] if ended else line
        match = LINE_NUM_PREFIX.match(body)
        if match:
            if first_num is None:
                first_num = int(match.group(2))
            rebuilt = match.group(3)
            out.append(rebuilt + ("\n" if ended else ""))
        else:
            out.append(line)
    return "".join(out), first_num


def append_unmatched_line_suffix(search, replace, file_window):
    search_lines = search.splitlines()
    replace_lines = replace.splitlines()
    file_lines = file_window.splitlines()
    if not search_lines or not file_lines or not replace_lines:
        return replace
    s_last = search_lines[-1].strip()
    f_last = file_lines[-1]
    f_stripped = f_last.strip()
    if not s_last or not f_stripped.startswith(s_last) or f_stripped == s_last:
        return replace
    idx = f_last.find(s_last)
    suffix = f_last[idx + len(s_last):] if idx >= 0 else f_stripped[len(s_last):]
    replace_lines[-1] = replace_lines[-1] + suffix
    joiner = "\n"
    if search.endswith("\n") and not replace.endswith("\n"):
        return joiner.join(replace_lines) + "\n"
    return joiner.join(replace_lines)


def _split_keep(text):
    lines = text.splitlines(True)
    if not lines and text:
        return [text]
    return lines


def exact_matches(content, search):
    if not search:
        return []
    needle = search
    found = []
    start = 0
    while True:
        idx = content.find(needle, start)
        if idx < 0:
            break
        found.append((idx, idx + len(needle)))
        start = idx + max(1, len(needle))
    if found:
        return found
    stripped = search.strip("\n")
    if stripped and stripped != search:
        return exact_matches(content, stripped)
    return []


def exact_match(content, search, expected_line=None):
    hits = exact_matches(content, search)
    if not hits:
        return None
    if expected_line is None:
        return hits[0]
    return _nearest_span(content, hits, expected_line)


def _line_at(content, idx):
    return content.count("\n", 0, idx) + 1


def _nearest_span(content, spans, expected_line):
    return min(spans, key=lambda span: abs(_line_at(content, span[0]) - expected_line))


def indent_agnostic_matches(content, search):
    file_lines = _split_keep(content)
    search_lines = [ln.rstrip("\n") for ln in _split_keep(search)]
    if not search_lines:
        return []
    stripped_search = [ln.strip() for ln in search_lines]
    n = len(stripped_search)
    bodies = [ln.rstrip("\n") for ln in file_lines]
    hits = []
    for i in range(0, max(0, len(bodies) - n + 1)):
        window = [ln.strip() for ln in bodies[i : i + n]]
        if window == stripped_search:
            start = sum(len(file_lines[j]) for j in range(i))
            end = start + sum(len(file_lines[j]) for j in range(i, i + n))
            hits.append((start, end, "".join(file_lines[i : i + n])))
    return hits


def indent_agnostic_match(content, search, expected_line=None):
    hits = indent_agnostic_matches(content, search)
    if not hits:
        return None
    if expected_line is None:
        return hits[0]
    start, end, window = min(hits, key=lambda h: abs(_line_at(content, h[0]) - expected_line))
    return start, end, window


def fuzzy_window_match(content, search, expected_line=None, threshold=FUZZY_THRESHOLD):
    file_lines = [ln.rstrip("\n") for ln in _split_keep(content)]
    search_lines = [ln.rstrip("\n") for ln in _split_keep(search)]
    n = len(search_lines)
    if n == 0 or n > len(file_lines):
        return None
    search_blob = "\n".join(search_lines)
    raw_lines = _split_keep(content)
    candidates = []
    for i in range(0, len(file_lines) - n + 1):
        window = "\n".join(file_lines[i : i + n])
        score = jaro_winkler(search_blob, window)
        if score >= threshold:
            start = sum(len(raw_lines[j]) for j in range(i))
            end = start + sum(len(raw_lines[j]) for j in range(i, i + n))
            candidates.append((score, i + 1, start, end, "".join(raw_lines[i : i + n])))
    if not candidates:
        return None
    if expected_line is None:
        best = max(candidates, key=lambda c: c[0])
    else:
        top = max(c[0] for c in candidates)
        near = [c for c in candidates if c[0] >= top - 0.05]
        best = min(near, key=lambda c: abs(c[1] - expected_line))
    return best[2], best[3], best[4], best[0]


def find_search_span(content, search):
    cleaned, expected_line = remove_extra_line_num_prefix(search)
    if not cleaned:
        return None, "empty search", expected_line, cleaned
    exact = exact_match(content, cleaned, expected_line=expected_line)
    if exact:
        start, end = exact
        return (start, end, content[start:end]), None, expected_line, cleaned
    indent = indent_agnostic_match(content, cleaned, expected_line=expected_line)
    if indent:
        start, end, window = indent
        return (start, end, window), None, expected_line, cleaned
    fuzzy = fuzzy_window_match(content, cleaned, expected_line=expected_line)
    if fuzzy:
        start, end, window, _score = fuzzy
        return (start, end, window), None, expected_line, cleaned
    return None, "did not match", expected_line, cleaned


def is_noop(search, replace, window=None):
    cleaned_search, _ = remove_extra_line_num_prefix(search)
    cleaned_replace, _ = remove_extra_line_num_prefix(replace)
    if cleaned_search == cleaned_replace:
        return True
    if window is not None and cleaned_replace == window:
        return True
    return False


def deduplicate_overlapping_deltas(deltas):
    ordered = sorted(deltas, key=lambda d: (d["start"], -(d["end"] - d["start"])))
    kept = []
    for delta in ordered:
        overlaps = False
        for prev in kept:
            if delta["start"] < prev["end"] and delta["end"] > prev["start"]:
                overlaps = True
                break
        if not overlaps:
            kept.append(delta)
    return sorted(kept, key=lambda d: d["start"])


def apply_deltas(content, deltas):
    pieces = []
    cursor = 0
    for delta in sorted(deltas, key=lambda d: d["start"], reverse=True):
        pass
    for delta in sorted(deltas, key=lambda d: d["start"]):
        if delta["start"] < cursor:
            continue
        pieces.append(content[cursor : delta["start"]])
        pieces.append(delta["replacement"])
        cursor = delta["end"]
    pieces.append(content[cursor:])
    return "".join(pieces)


def error_search_mismatch(path, block_index):
    return "Could not apply all diffs to %s. Search block %s did not match." % (
        path,
        block_index,
    )


def error_missing_file(path):
    return "%s does not exist. Is the path correct?" % path


def error_already_made(path):
    return "The changes to %s were already made." % path
