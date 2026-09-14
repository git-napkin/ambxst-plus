"""Map screenshot-preview pixels onto compositor logical coordinates."""

from __future__ import annotations


def preview_to_logical(x, y, meta):
    """Convert a click in the image the model saw into compositor logical pixels.

    ``meta`` comes from a silent grim capture:
    - ``scale``: payload_width / coordinate_width (downscale factor)
    - ``origin_x`` / ``origin_y``: monitor logical origin
    - ``monitor_scale``: that output's scale (not max-across-monitors)
    - ``crop_x`` / ``crop_y``: physical crop origin inside the monitor PNG
    """
    meta = meta or {}
    image_scale = float(meta.get("scale") or 1) or 1.0
    monitor_scale = float(meta.get("monitor_scale") or 1) or 1.0
    origin_x = float(meta.get("origin_x") or 0)
    origin_y = float(meta.get("origin_y") or 0)
    crop_x = float(meta.get("crop_x") or 0)
    crop_y = float(meta.get("crop_y") or 0)
    cap_x = (float(x) / image_scale) + crop_x
    cap_y = (float(y) / image_scale) + crop_y
    logical_x = origin_x + cap_x / monitor_scale
    logical_y = origin_y + cap_y / monitor_scale
    return int(round(logical_x)), int(round(logical_y))


def relative_preview_to_logical(x, y, meta):
    """``relative: true`` coords are from the cropped window origin in preview space."""
    return preview_to_logical(x, y, meta)


def clamp_note(requested, emitted):
    if requested == emitted:
        return ""
    return "Requested coordinate %s was clamped to %s" % (requested, emitted)
