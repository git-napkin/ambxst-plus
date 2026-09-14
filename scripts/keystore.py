#!/usr/bin/env python3
import sqlite3
import json
import sys
import os
import base64
import shutil
import subprocess
from pathlib import Path


def get_machine_id():
    try:
        with open("/etc/machine-id", "r") as f:
            mid = f.read().strip()
            if mid:
                return mid.encode("utf-8")
            raise ValueError("empty machine-id")
    except Exception:
        # Use persistent per-user fallback instead of constant
        fallback_path = Path.home() / ".config" / "ambxst+" / ".keystore_salt"
        try:
            if fallback_path.exists():
                fallback_path.chmod(0o600)
                return fallback_path.read_bytes().strip()
            fallback_path.parent.mkdir(parents=True, exist_ok=True)
            salt = os.urandom(32)
            # Atomic write with 0o600
            fd = os.open(str(fallback_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                encoded = base64.b64encode(salt)
                os.write(fd, encoded)
            finally:
                os.close(fd)
            # Return exactly what was persisted so later runs derive the same key
            return encoded
        except Exception:
            return base64.b64encode(os.urandom(32))


def _has_cryptography():
    try:
        import cryptography  # noqa: F401

        return True
    except ImportError:
        return False


def _derive_key(machine_key, salt):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=600000,
    )
    return base64.urlsafe_b64encode(kdf.derive(machine_key))


def _fernet_encrypt(text, machine_key):
    from cryptography.fernet import Fernet

    salt = os.urandom(16)
    key = _derive_key(machine_key, salt)
    token = Fernet(key).encrypt(text.encode("utf-8"))
    return base64.b64encode(salt + token).decode("utf-8")


_OPENSSL_PREFIX = "o1:"
_OPENSSL_PASS_ENV = "AMBXST_KS_PASS"


def _openssl_bin():
    return shutil.which("openssl") or "openssl"


def _openssl_env(machine_key):
    env = os.environ.copy()
    env[_OPENSSL_PASS_ENV] = base64.b64encode(machine_key).decode("ascii")
    return env


def _openssl_encrypt(text, machine_key):
    proc = subprocess.run(
        [
            _openssl_bin(),
            "enc",
            "-aes-256-cbc",
            "-pbkdf2",
            "-iter",
            "600000",
            "-salt",
            "-pass",
            "env:" + _OPENSSL_PASS_ENV,
            "-base64",
            "-A",
        ],
        input=text.encode("utf-8"),
        capture_output=True,
        env=_openssl_env(machine_key),
        check=False,
    )
    if proc.returncode != 0:
        err = (proc.stderr or b"").decode("utf-8", "replace").strip()
        raise RuntimeError(err or "openssl encrypt failed")
    return _OPENSSL_PREFIX + proc.stdout.decode("ascii").strip()


def _openssl_decrypt(blob, machine_key):
    payload = blob[len(_OPENSSL_PREFIX) :] if blob.startswith(_OPENSSL_PREFIX) else blob
    proc = subprocess.run(
        [
            _openssl_bin(),
            "enc",
            "-d",
            "-aes-256-cbc",
            "-pbkdf2",
            "-iter",
            "600000",
            "-pass",
            "env:" + _OPENSSL_PASS_ENV,
            "-base64",
            "-A",
        ],
        input=payload.encode("ascii"),
        capture_output=True,
        env=_openssl_env(machine_key),
        check=False,
    )
    if proc.returncode != 0:
        raise ValueError("openssl decrypt failed")
    return proc.stdout.decode("utf-8")


def encrypt(text, machine_key):
    if _has_cryptography():
        return _fernet_encrypt(text, machine_key)
    return _openssl_encrypt(text, machine_key)


_LEGACY_FALLBACK_KEY = b"ambxst+-fallback-salt-82741"


def _try_decrypt(hex_str, machine_key):
    from cryptography.fernet import Fernet

    raw = base64.b64decode(hex_str)
    if len(raw) < 17:
        raise ValueError("too short")
    salt = raw[:16]
    payload = raw[16:]
    key = _derive_key(machine_key, salt)
    return Fernet(key).decrypt(payload).decode("utf-8")


def decrypt(hex_str, machine_key):
    if not hex_str:
        return ""
    if str(hex_str).startswith(_OPENSSL_PREFIX):
        try:
            return _openssl_decrypt(hex_str, machine_key)
        except Exception:
            return ""
    try:
        return _try_decrypt(hex_str, machine_key)
    except ImportError:
        return ""
    except Exception:
        try:
            if machine_key != _LEGACY_FALLBACK_KEY:
                return _try_decrypt(hex_str, _LEGACY_FALLBACK_KEY)
        except Exception:
            pass
        return ""


def allowed_db_roots():
    roots = []
    try:
        roots.append((Path.home() / ".config" / "ambxst+").resolve())
    except Exception:
        pass
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        try:
            roots.append(Path(xdg_config).expanduser().resolve() / "ambxst+")
        except Exception:
            pass
    try:
        roots.append((Path.home() / ".local" / "share" / "ambxst+").resolve())
    except Exception:
        pass
    xdg_data = os.environ.get("XDG_DATA_HOME")
    if xdg_data:
        try:
            roots.append(Path(xdg_data).expanduser().resolve() / "ambxst+")
        except Exception:
            pass
    return roots


def is_db_path_allowed(db_path):
    resolved = Path(os.path.expanduser(str(db_path))).resolve()
    for root in allowed_db_roots():
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
        except Exception:
            continue
    return False


def ensure_schema(conn, create=True):
    cursor = conn.cursor()
    exists = cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='api_keys'"
    ).fetchone()
    if not exists:
        if not create:
            return False
        cursor.execute(
            """
            CREATE TABLE api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                label TEXT DEFAULT '',
                api_key TEXT NOT NULL,
                endpoint TEXT DEFAULT '',
                custom_curl TEXT DEFAULT ''
            )
            """
        )
        return True
    cols = {row[1] for row in cursor.execute("PRAGMA table_info(api_keys)")}
    if "id" in cols:
        if "label" not in cols:
            cursor.execute("ALTER TABLE api_keys ADD COLUMN label TEXT DEFAULT ''")
        return True
    cursor.execute("ALTER TABLE api_keys RENAME TO api_keys_legacy")
    cursor.execute(
        """
        CREATE TABLE api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            label TEXT DEFAULT '',
            api_key TEXT NOT NULL,
            endpoint TEXT DEFAULT '',
            custom_curl TEXT DEFAULT ''
        )
        """
    )
    legacy = {row[1] for row in cursor.execute("PRAGMA table_info(api_keys_legacy)")}
    if "endpoint" in legacy and "custom_curl" in legacy:
        cursor.execute(
            "INSERT INTO api_keys (provider, label, api_key, endpoint, custom_curl) "
            "SELECT provider, '', api_key, endpoint, custom_curl FROM api_keys_legacy"
        )
    else:
        cursor.execute(
            "INSERT INTO api_keys (provider, label, api_key, endpoint, custom_curl) "
            "SELECT provider, '', api_key, '', '' FROM api_keys_legacy"
        )
    cursor.execute("DROP TABLE api_keys_legacy")
    return True


def _open_keystore(db_path, create=False):
    path = Path(os.path.expanduser(str(db_path))).resolve()
    if not is_db_path_allowed(path):
        return None
    if path.is_symlink() or path.parent.is_symlink():
        return None
    if not path.exists():
        return None
    conn = sqlite3.connect(str(path), timeout=5.0)
    try:
        if not ensure_schema(conn, create=create):
            conn.close()
            return None
        conn.commit()
        return conn
    except Exception:
        conn.close()
        return None


def _split_key_ref(provider):
    text = str(provider or "")
    if "#" not in text:
        return text, None
    prefix, rest = text.rsplit("#", 1)
    if rest.isdigit():
        return prefix, int(rest)
    return text, None


def _entry_from_row(row, machine_key):
    return {
        "id": row[0],
        "provider": row[1],
        "label": row[2] or "",
        "api_key": decrypt(row[3], machine_key),
        "endpoint": row[4] or "",
        "custom_curl": row[5] or "",
    }


def get_provider_key(db_path, provider):
    """Read a decrypted API key from the sqlite db without putting it on argv."""
    conn = _open_keystore(db_path)
    if conn is None:
        return ""
    try:
        prefix, key_id = _split_key_ref(provider)
        if key_id is not None:
            row = conn.execute(
                "SELECT api_key FROM api_keys WHERE id = ?",
                (key_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT api_key FROM api_keys WHERE provider = ? ORDER BY id LIMIT 1",
                (prefix,),
            ).fetchone()
        if not row:
            return ""
        return decrypt(row[0], get_machine_id())
    except Exception:
        return ""
    finally:
        conn.close()


def list_provider_keys(db_path, provider):
    conn = _open_keystore(db_path)
    if conn is None:
        return []
    try:
        rows = conn.execute(
            "SELECT id, provider, label, api_key, endpoint, custom_curl "
            "FROM api_keys WHERE provider = ? ORDER BY id",
            (provider,),
        ).fetchall()
        machine_key = get_machine_id()
        return [_entry_from_row(row, machine_key) for row in rows]
    except Exception:
        return []
    finally:
        conn.close()


def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: <db_path> <cmd> [args...]"}), flush=True)
        sys.exit(1)

    db_path = Path(os.path.expanduser(sys.argv[1])).resolve()
    cmd = sys.argv[2]
    args = sys.argv[3:]

    if not is_db_path_allowed(db_path):
        print(json.dumps({"error": "db_path outside allowed directory"}), flush=True)
        sys.exit(1)

    # Reject symlink parent to prevent symlink attack
    if db_path.is_symlink():
        print(json.dumps({"error": "db_path must not be a symlink"}), flush=True)
        sys.exit(1)
    if db_path.parent.is_symlink():
        print(json.dumps({"error": "db_path parent must not be a symlink"}), flush=True)
        sys.exit(1)

    # Ensure parent directory exists with safe perms
    try:
        old_umask = os.umask(0o077)
        db_path.parent.mkdir(parents=True, exist_ok=True)
    finally:
        try:
            os.umask(old_umask)
        except Exception:
            pass

    conn = None
    try:
        # Create file with 0o600 if it doesn't exist to avoid TOCTOU chmod race
        if not db_path.exists():
            fd = os.open(str(db_path), os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
        else:
            # Ensure perms, don't follow symlink (already checked)
            try:
                os.chmod(str(db_path), 0o600, follow_symlinks=False)
            except TypeError:
                os.chmod(str(db_path), 0o600)

        conn = sqlite3.connect(str(db_path), timeout=5.0, isolation_level=None)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except Exception:
            pass

        cursor = conn.cursor()
        ensure_schema(conn, create=True)
        conn.commit()

        machine_key = get_machine_id()
        select_cols = (
            "SELECT id, provider, label, api_key, endpoint, custom_curl FROM api_keys"
        )

        if cmd in ("set", "add"):
            if len(args) < 2:
                print(
                    json.dumps(
                        {
                            "error": f"{cmd} requires <provider> <key> [label] [endpoint] [custom_curl]"
                        }
                    ),
                    flush=True,
                )
                sys.exit(1)

            provider = args[0]
            api_key = encrypt(args[1], machine_key)
            label = args[2] if len(args) > 2 else ""
            endpoint = args[3] if len(args) > 3 else ""
            custom_curl = args[4] if len(args) > 4 else ""
            if cmd == "set" and len(args) <= 4 and len(args) >= 3:
                # Legacy: set <provider> <key> [endpoint] [custom_curl]
                looks_like_url = args[2].startswith("http://") or args[2].startswith(
                    "https://"
                )
                if looks_like_url or (len(args) > 3 and not args[2]):
                    label = ""
                    endpoint = args[2]
                    custom_curl = args[3] if len(args) > 3 else ""

            cursor.execute(
                "INSERT INTO api_keys (provider, label, api_key, endpoint, custom_curl) "
                "VALUES (?, ?, ?, ?, ?)",
                (provider, label, api_key, endpoint, custom_curl),
            )
            conn.commit()
            print(json.dumps({"status": "ok", "id": cursor.lastrowid}), flush=True)

        elif cmd == "get":
            if not args:
                print(json.dumps({"error": "get requires <provider>"}), flush=True)
                sys.exit(1)

            prefix, key_id = _split_key_ref(args[0])
            if key_id is not None:
                cursor.execute(select_cols + " WHERE id = ?", (key_id,))
            else:
                cursor.execute(
                    select_cols + " WHERE provider = ? ORDER BY id LIMIT 1",
                    (prefix,),
                )
            row = cursor.fetchone()
            if row:
                print(json.dumps(_entry_from_row(row, machine_key)), flush=True)
            else:
                print(
                    json.dumps({"error": f"Provider '{args[0]}' not found"}), flush=True
                )
                sys.exit(1)

        elif cmd == "delete":
            if not args:
                print(json.dumps({"error": "delete requires <provider>"}), flush=True)
                sys.exit(1)
            cursor.execute("DELETE FROM api_keys WHERE provider = ?", (args[0],))
            conn.commit()
            print(json.dumps({"status": "ok"}), flush=True)

        elif cmd == "delete-id":
            if not args:
                print(json.dumps({"error": "delete-id requires <id>"}), flush=True)
                sys.exit(1)
            try:
                key_id = int(args[0])
            except ValueError:
                print(json.dumps({"error": "delete-id requires a numeric id"}), flush=True)
                sys.exit(1)
            cursor.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
            conn.commit()
            print(json.dumps({"status": "ok"}), flush=True)

        elif cmd == "list":
            cursor.execute(select_cols + " ORDER BY id")
            rows = cursor.fetchall()
            print(
                json.dumps([_entry_from_row(row, machine_key) for row in rows]),
                flush=True,
            )

        elif cmd == "has":
            if not args:
                print(json.dumps({"error": "has requires <provider>"}), flush=True)
                sys.exit(1)
            cursor.execute("SELECT 1 FROM api_keys WHERE provider = ?", (args[0],))
            print(json.dumps(cursor.fetchone() is not None), flush=True)

        else:
            print(json.dumps({"error": f"Unknown command: {cmd}"}), flush=True)
            sys.exit(1)

    except Exception as e:
        # Sanitize error for UI; log details to stderr
        print(json.dumps({"error": "internal error"}), flush=True)
        print(f"keystore error: {e}", file=sys.stderr, flush=True)
        sys.exit(1)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
