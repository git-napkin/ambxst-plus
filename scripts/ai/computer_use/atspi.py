"""AT-SPI snapshot, selectors, actions, and set_value. Degrades if the bus is empty."""

from __future__ import annotations

import time

MAX_NODES = 1000
HARD_MAX_NODES = 2000
MAX_DEPTH = 32
HARD_MAX_DEPTH = 64
SNAPSHOT_TIMEOUT = 10
MAX_TEXT = 4096
MAX_DISCOVERY_ROOTS = 256

CLICK_ACTIONS = ("click", "press", "toggle")

STATE_NAMES = (
    "invalid",
    "active",
    "armed",
    "busy",
    "checked",
    "collapsed",
    "defunct",
    "editable",
    "enabled",
    "expandable",
    "expanded",
    "focusable",
    "focused",
    "has_tooltip",
    "horizontal",
    "iconified",
    "modal",
    "multi_line",
    "multiselectable",
    "opaque",
    "pressed",
    "resizable",
    "selectable",
    "selected",
    "sensitive",
    "showing",
    "single_line",
    "stale",
    "transient",
    "vertical",
    "visible",
    "manages_descendants",
    "indeterminate",
    "required",
    "truncated",
    "animated",
    "invalid_entry",
    "supports_autocompletion",
    "selectable_text",
    "is_default",
    "visited",
    "checkable",
    "has_popup",
    "read_only",
)


def _states_from_flags(raw):
    flags = 0
    try:
        if hasattr(raw, "__iter__") and not isinstance(raw, (str, bytes)):
            parts = [int(x) for x in list(raw)[:4]]
            for i, part in enumerate(parts):
                flags |= (part & 0xFFFFFFFF) << (32 * i)
        else:
            flags = int(raw)
    except (TypeError, ValueError):
        return []
    names = []
    for i, name in enumerate(STATE_NAMES):
        if flags & (1 << i):
            names.append(name)
    return names


def _norm(value):
    return " ".join(str(value or "").lower().split())


def _clamp(value, default, hard):
    if value is None:
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(number, hard))


def _session_bus():
    import dbus

    return dbus.SessionBus()


def connect_a11y():
    import dbus

    session = _session_bus()
    try:
        bus_obj = session.get_object("org.a11y.Bus", "/org/a11y/bus")
        addr = str(bus_obj.GetAddress(dbus_interface="org.a11y.Bus"))
    except Exception as exc:
        raise RuntimeError("AT-SPI bus is unavailable: %s" % exc) from exc
    if not addr:
        raise RuntimeError("AT-SPI bus address is empty")
    return dbus.bus.BusConnection(addr)


def probe():
    try:
        bus = connect_a11y()
        bus.get_object("org.a11y.atspi.Registry", "/org/a11y/atspi/accessible/root")
        return True
    except Exception:
        return False


def _iface(obj, name):
    import dbus

    return dbus.Interface(obj, name)


def _node_from_proxy(bus, path, index, parent_index, depth):
    import dbus

    obj = bus.get_object("org.a11y.atspi.Registry", path)
    acc = _iface(obj, "org.a11y.atspi.Accessible")
    role = ""
    name = ""
    desc = ""
    child_count = 0
    states = []
    try:
        role = str(acc.GetRoleName())
    except Exception:
        pass
    try:
        name = str(acc.GetName())
    except Exception:
        pass
    try:
        desc = str(acc.GetDescription())
    except Exception:
        pass
    try:
        child_count = int(acc.GetChildCount())
    except Exception:
        child_count = 0
    try:
        state = acc.GetState()
        names = _states_from_flags(state)
        states = names if names else [str(item) for item in list(state)[:16]]
    except Exception:
        pass
    bounds = None
    try:
        comp = _iface(obj, "org.a11y.atspi.Component")
        extents = comp.GetExtents(0)
        x, y, w, h = [int(v) for v in extents]
        if w > 0 and h > 0 and x > -10**8 and y > -10**8:
            bounds = {"x": x, "y": y, "width": w, "height": h}
    except Exception:
        bounds = None
    actions = []
    try:
        act = _iface(obj, "org.a11y.atspi.Action")
        count = int(act.nActions) if hasattr(act, "nActions") else int(act.GetNActions())
        for i in range(min(count, 12)):
            try:
                actions.append(
                    {
                        "index": i,
                        "name": str(act.GetName(i)),
                        "description": str(act.GetDescription(i)),
                        "keybinding": str(act.GetKeyBinding(i)),
                    }
                )
            except Exception:
                continue
    except Exception:
        pass
    text = ""
    editable = False
    try:
        txt = _iface(obj, "org.a11y.atspi.Text")
        n = int(txt.GetCharacterCount())
        text = str(txt.GetText(0, min(n, MAX_TEXT)))
    except Exception:
        pass
    try:
        _iface(obj, "org.a11y.atspi.EditableText")
        editable = True
    except Exception:
        editable = False
    value = None
    try:
        val = _iface(obj, "org.a11y.atspi.Value")
        value = {
            "current": float(val.CurrentValue),
            "minimum": float(val.MinimumValue),
            "maximum": float(val.MaximumValue),
        }
    except Exception:
        value = None
    children = []
    try:
        kids = acc.GetChildren()
        for kid in list(kids)[:64]:
            if isinstance(kid, (list, tuple)) and len(kid) >= 1:
                children.append(str(kid[1] if len(kid) > 1 else kid[0]))
            else:
                children.append(str(kid))
    except Exception:
        children = []
    return {
        "index": index,
        "parent_index": parent_index,
        "depth": depth,
        "object_ref": str(path),
        "role": role,
        "name": name,
        "description": desc,
        "child_count": child_count,
        "bounds": bounds,
        "states": states,
        "actions": actions,
        "value": value,
        "text": text[:MAX_TEXT],
        "supports_editable_text": editable,
        "_children": children,
    }


def snapshot_tree(pid=None, app_name=None, max_nodes=None, max_depth=None):
    deadline = time.time() + SNAPSHOT_TIMEOUT
    cap_nodes = _clamp(max_nodes, MAX_NODES, HARD_MAX_NODES)
    cap_depth = _clamp(max_depth, MAX_DEPTH, HARD_MAX_DEPTH)
    bus = connect_a11y()
    root = bus.get_object("org.a11y.atspi.Registry", "/org/a11y/atspi/accessible/root")
    acc = _iface(root, "org.a11y.atspi.Accessible")
    apps = []
    try:
        apps = list(acc.GetChildren())[:MAX_DISCOVERY_ROOTS]
    except Exception as exc:
        raise RuntimeError("AT-SPI registry has no children: %s" % exc) from exc
    roots = []
    want_pid = None if pid in (None, "") else int(pid)
    want_name = _norm(app_name or "")
    for app in apps:
        path = str(app[1] if isinstance(app, (list, tuple)) and len(app) > 1 else app)
        try:
            node = _node_from_proxy(bus, path, 0, None, 0)
        except Exception:
            continue
        if want_pid is not None:
            # AT-SPI application nodes sometimes expose pid in name/description; skip strict pid if missing
            pass
        if want_name and want_name not in _norm(node.get("name") or "") and want_name not in _norm(node.get("role") or ""):
            continue
        roots.append(path)
        if want_name or want_pid is not None:
            break
    if not roots:
        roots = [
            str(app[1] if isinstance(app, (list, tuple)) and len(app) > 1 else app)
            for app in apps[:8]
        ]
    nodes = []
    queue = [(path, None, 0) for path in roots]
    seen = set()
    while queue and len(nodes) < cap_nodes and time.time() < deadline:
        path, parent, depth = queue.pop(0)
        if path in seen or depth > cap_depth:
            continue
        seen.add(path)
        try:
            node = _node_from_proxy(bus, path, len(nodes), parent, depth)
        except Exception:
            continue
        children = node.pop("_children", [])
        nodes.append(node)
        if depth < cap_depth:
            for child in children:
                if child and child not in seen:
                    queue.append((child, node["index"], depth + 1))
    return compact_tree(nodes)


def compact_tree(nodes):
    keepers = []
    for node in nodes:
        role = _norm(node.get("role") or "")
        keep = (
            node.get("depth", 0) <= 1
            or node.get("actions")
            or (node.get("name") or "").strip()
            or (node.get("text") or "").strip()
            or role in ("page tab", "menu", "list item", "tree item", "push button", "text", "entry")
        )
        if keep:
            keepers.append(node)
    index_map = {node["index"]: i for i, node in enumerate(keepers)}
    out = []
    for i, node in enumerate(keepers):
        parent = node.get("parent_index")
        item = dict(node)
        item["index"] = i
        item["parent_index"] = index_map.get(parent)
        out.append(item)
    return out


def node_matches_selector(node, selector):
    selector = selector or {}
    role = _norm(selector.get("role") or "")
    name = _norm(selector.get("name") or "")
    text = _norm(selector.get("text") or "")
    states = selector.get("states") or []
    if role and role not in _norm(node.get("role") or ""):
        return False
    if name and name not in _norm(node.get("name") or ""):
        return False
    blob = " ".join([node.get("text") or "", node.get("name") or "", node.get("description") or ""])
    if text and text not in _norm(blob):
        return False
    have = [_norm(s) for s in (node.get("states") or [])]
    for state in states:
        if _norm(state) not in have:
            return False
    return True


def resolve_node(nodes, args):
    nodes = list(nodes or [])
    if args.get("element_index") not in (None, ""):
        try:
            idx = int(args.get("element_index"))
        except (TypeError, ValueError):
            return None, "element_index is not an integer"
        if 0 <= idx < len(nodes):
            return nodes[idx], ""
        return None, "No cached accessibility node for element_index %s. Call snapshot first." % idx
    ident = str(args.get("element_identifier") or "").strip()
    if ident:
        for node in nodes:
            if node.get("object_ref") == ident:
                return node, ""
        return None, "No cached accessibility node for element_identifier"
    selector = {
        "role": args.get("role"),
        "name": args.get("name"),
        "text": args.get("text"),
        "states": args.get("states") or [],
    }
    if not any(selector.values()):
        return None, ""
    matches = [n for n in nodes if node_matches_selector(n, selector)]
    if len(matches) == 1:
        return matches[0], ""
    if not matches:
        return None, "No accessibility node matched the selector"
    names = ["%s:%s" % (m.get("index"), m.get("name") or m.get("role")) for m in matches[:8]]
    return None, "Ambiguous selector matched %s nodes (%s)" % (len(matches), ", ".join(names))


def click_equivalent(node):
    actions = node.get("actions") or []
    if not actions:
        return None
    name = _norm(actions[0].get("name") or "")
    if name in CLICK_ACTIONS:
        return 0
    return None


def perform_action(node, action=None):
    import dbus

    bus = connect_a11y()
    obj = bus.get_object("org.a11y.atspi.Registry", node["object_ref"])
    act = _iface(obj, "org.a11y.atspi.Action")
    index = 0
    if action in (None, ""):
        index = 0
    else:
        raw = str(action)
        if raw.isdigit():
            index = int(raw)
        else:
            want = _norm(raw)
            found = None
            for item in node.get("actions") or []:
                if want in _norm(item.get("name") or "") or want in _norm(item.get("description") or ""):
                    found = int(item.get("index") or 0)
                    break
            if found is None:
                raise RuntimeError("no such action: %s" % action)
            index = found
    return bool(act.DoAction(index))


def set_value(node, value):
    import dbus

    bus = connect_a11y()
    obj = bus.get_object("org.a11y.atspi.Registry", node["object_ref"])
    text = str(value)
    try:
        number = float(text)
        val = _iface(obj, "org.a11y.atspi.Value")
        val.SetCurrentValue(number)
        return True
    except (TypeError, ValueError, Exception):
        pass
    try:
        edit = _iface(obj, "org.a11y.atspi.EditableText")
        edit.SetTextContents(text)
        return True
    except Exception as exc:
        raise RuntimeError("could not set value: %s" % exc) from exc


def focused_element(max_nodes=400, max_depth=16):
    try:
        nodes = snapshot_tree(max_nodes=max_nodes, max_depth=max_depth)
    except Exception:
        return None
    for node in nodes:
        states = [_norm(s) for s in (node.get("states") or [])]
        if "focused" in states:
            return {
                "role": node.get("role"),
                "name": node.get("name"),
                "editable": bool(node.get("supports_editable_text") or "editable" in states),
            }
    return None
