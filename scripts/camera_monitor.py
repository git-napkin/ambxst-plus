#!/usr/bin/env python3
"""Camera enumeration and in-use detection.

Lists /dev/video* (names from /sys/class/video4linux) and detects open cameras
by matching /proc/*/fd device numbers. Prints one JSON object per line.

With an interval argument (seconds), loops so the QML service can keep one
interpreter alive instead of paying startup on every poll.
"""

import json
import os
import sys
import time

VIDEO4LINUX = "/sys/class/video4linux"


def _camera_name(node):
    v4l_name = None
    try:
        if os.path.islink(node):
            real = os.path.realpath(node)
            if os.path.basename(real).startswith("video"):
                v4l_name = os.path.basename(real)
    except OSError:
        pass
    if v4l_name and os.path.isdir(os.path.join(VIDEO4LINUX, v4l_name)):
        name_file = os.path.join(VIDEO4LINUX, v4l_name, "name")
        try:
            with open(name_file, "r", errors="replace") as f:
                return f.read().strip()
        except OSError:
            return v4l_name
    return os.path.basename(node)


def _list_cameras():
    cameras = []
    try:
        with os.scandir("/dev") as it:
            entries = sorted(e.name for e in it if e.name.startswith("video"))
    except OSError:
        return cameras
    for entry in entries:
        node = os.path.join("/dev", entry)
        try:
            if not os.path.exists(node):
                continue
        except OSError:
            continue
        cameras.append({"name": _camera_name(node), "node": node})
    return cameras


def _camera_nodes(cameras):
    nodes = set()
    for cam in cameras:
        node = cam.get("node") or ""
        if node:
            nodes.add(node)
        try:
            nodes.add(os.path.realpath(node))
        except OSError:
            pass
    return nodes


def _open_camera_users(cameras):
    if not cameras:
        return []
    nodes = _camera_nodes(cameras)
    if not nodes:
        return []

    users = []
    try:
        proc_iter = os.scandir("/proc")
    except OSError:
        return users

    with proc_iter:
        for entry in proc_iter:
            if not entry.name.isdigit():
                continue
            fd_dir = os.path.join(entry.path, "fd")
            try:
                fds = os.scandir(fd_dir)
            except OSError:
                continue
            matched = False
            with fds:
                for fd in fds:
                    try:
                        target = os.readlink(fd.path)
                    except OSError:
                        continue
                    if target in nodes or target.startswith("/dev/video"):
                        users.append(entry.name)
                        matched = True
                        break
            if matched:
                continue
    return users


def _proc_name(pid):
    try:
        with open(os.path.join("/proc", pid, "comm"), "r") as f:
            return f.read().strip()
    except OSError:
        return "?"


def emit():
    cameras = _list_cameras()
    users = _open_camera_users(cameras)
    json.dump(
        {
            "cameras": cameras,
            "inUse": len(users) > 0,
            "users": [{"pid": pid, "name": _proc_name(pid)} for pid in users],
        },
        sys.stdout,
    )
    sys.stdout.write("\n")
    sys.stdout.flush()


def main():
    interval = None
    if len(sys.argv) > 1:
        try:
            interval = float(sys.argv[1])
        except ValueError:
            interval = None

    if interval and interval > 0:
        while True:
            emit()
            time.sleep(interval)
    else:
        emit()


if __name__ == "__main__":
    main()
