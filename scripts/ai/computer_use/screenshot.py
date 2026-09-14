"""Downscale a grim PNG for the vision loop. Capture itself is QML."""

from __future__ import annotations

import base64
import os
import shutil
import struct
import subprocess
import tempfile

DEFAULT_MAX_DIMENSION = 1280
ABSOLUTE_MAX_DIMENSION = 4096
DEFAULT_MAX_BYTES = 2 * 1024 * 1024
ABSOLUTE_MAX_BYTES = 4 * 1024 * 1024
MIN_MAX_BYTES = 1024
DEFAULT_JPEG_QUALITY = 70


def _clamp_dim(value, default):
    if value is None:
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(number, ABSOLUTE_MAX_DIMENSION))


def _clamp_bytes(value):
    if value is None:
        return DEFAULT_MAX_BYTES
    try:
        number = int(value)
    except (TypeError, ValueError):
        return DEFAULT_MAX_BYTES
    return max(MIN_MAX_BYTES, min(number, ABSOLUTE_MAX_BYTES))


def identify_size(path):
    try:
        with open(path, "rb") as fh:
            sig = fh.read(8)
            if sig == b"\x89PNG\r\n\x1a\n":
                fh.read(8)
                width, height = struct.unpack(">II", fh.read(8))
                return int(width), int(height)
            if sig[:2] == b"\xff\xd8":
                pass
            else:
                return None, None
    except (OSError, struct.error, ValueError):
        return None, None
    convert = shutil.which("identify") or shutil.which("magick")
    if not convert:
        return None, None
    cmd = [convert]
    if os.path.basename(convert) == "magick":
        cmd.append("identify")
    cmd.extend(["-format", "%w %h", path])
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=8)
    except (OSError, subprocess.SubprocessError):
        return None, None
    parts = out.decode("utf-8", "replace").strip().split()
    if len(parts) < 2:
        return None, None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None, None


def _run_convert(src, dest, extra):
    convert = shutil.which("convert") or shutil.which("magick")
    if not convert:
        raise RuntimeError("ImageMagick convert is not installed")
    cmd = [convert]
    if os.path.basename(convert) == "magick":
        cmd.append("convert")
    cmd.append(src)
    cmd.extend(extra)
    cmd.append(dest)
    subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)


def prepare_payload(
    path,
    max_width=None,
    max_height=None,
    max_bytes=None,
    scale=None,
    fmt="png",
    quality=None,
):
    if not path or not os.path.isfile(path):
        raise FileNotFoundError("screenshot file is missing")
    coord_w, coord_h = identify_size(path)
    if not coord_w or not coord_h:
        raise RuntimeError("could not read screenshot dimensions")
    max_w = _clamp_dim(max_width, DEFAULT_MAX_DIMENSION)
    max_h = _clamp_dim(max_height, DEFAULT_MAX_DIMENSION)
    cap_bytes = _clamp_bytes(max_bytes)
    req_scale = 1.0
    if scale is not None:
        try:
            req_scale = min(1.0, max(0.05, float(scale)))
        except (TypeError, ValueError):
            req_scale = 1.0
    fit = min(1.0, max_w / float(coord_w), max_h / float(coord_h), req_scale)
    fmt = "jpeg" if str(fmt).lower() in ("jpg", "jpeg") else "png"
    q = DEFAULT_JPEG_QUALITY if quality is None else max(1, min(95, int(quality)))
    original_bytes = os.path.getsize(path)
    if fit >= 0.999 and original_bytes <= cap_bytes and (
        (fmt == "png" and path.lower().endswith(".png"))
        or (fmt == "jpeg" and path.lower().endswith((".jpg", ".jpeg")))
    ):
        with open(path, "rb") as fh:
            data = fh.read()
        ext = "jpg" if fmt == "jpeg" else "png"
        durable = os.path.join(
            tempfile.gettempdir(),
            "ambxst+_cu_vision_%s.%s" % (os.path.basename(path).replace(".", "_"), ext),
        )
        with open(durable, "wb") as fh:
            fh.write(data)
        return {
            "path": durable,
            "width": coord_w,
            "height": coord_h,
            "coordinate_width": coord_w,
            "coordinate_height": coord_h,
            "scale": 1.0,
            "resized": False,
            "bytes": len(data),
            "original_bytes": original_bytes,
            "max_bytes": cap_bytes,
            "format": fmt,
            "quality": q if fmt == "jpeg" else None,
            "mime_type": "image/jpeg" if fmt == "jpeg" else "image/png",
            "image_base64": base64.b64encode(data).decode("ascii"),
        }
    work = path
    tmp_dir = tempfile.mkdtemp(prefix="ambxst+_cu_")
    try:
        if fit < 0.999:
            resized = os.path.join(tmp_dir, "resized.png")
            pct = max(1, int(round(fit * 100)))
            _run_convert(path, resized, ["-resize", "%s%%" % pct])
            work = resized
        out_path = os.path.join(tmp_dir, "out.jpg" if fmt == "jpeg" else "out.png")
        extra = ["-quality", str(q)] if fmt == "jpeg" else []
        _run_convert(work, out_path, extra)
        with open(out_path, "rb") as fh:
            data = fh.read()
        if len(data) > cap_bytes:
            ratio = max(0.2, (cap_bytes / float(len(data))) ** 0.5 * 0.9)
            shrink = os.path.join(tmp_dir, "shrink.png")
            _run_convert(work, shrink, ["-resize", "%s%%" % max(1, int(round(ratio * 100)))])
            _run_convert(shrink, out_path, extra)
            with open(out_path, "rb") as fh:
                data = fh.read()
            work = shrink
        width, height = identify_size(out_path)
        durable = os.path.join(
            tempfile.gettempdir(),
            "ambxst+_cu_vision_%s.%s" % (os.path.basename(path).replace(".", "_"), "jpg" if fmt == "jpeg" else "png"),
        )
        with open(durable, "wb") as fh:
            fh.write(data)
        image_scale = (width / float(coord_w)) if coord_w else 1.0
        return {
            "path": durable,
            "width": width,
            "height": height,
            "coordinate_width": coord_w,
            "coordinate_height": coord_h,
            "scale": image_scale,
            "resized": abs(image_scale - 1.0) > 0.001,
            "bytes": len(data),
            "original_bytes": os.path.getsize(path),
            "max_bytes": cap_bytes,
            "format": fmt,
            "quality": q if fmt == "jpeg" else None,
            "mime_type": "image/jpeg" if fmt == "jpeg" else "image/png",
            "image_base64": base64.b64encode(data).decode("ascii"),
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
