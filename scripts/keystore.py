#!/usr/bin/env python3
import sqlite3
import json
import sys
import os
import base64
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


def encrypt(text, machine_key):
    from cryptography.fernet import Fernet

    salt = os.urandom(16)
    key = _derive_key(machine_key, salt)
    token = Fernet(key).encrypt(text.encode("utf-8"))
    return base64.b64encode(salt + token).decode("utf-8")


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
    try:
        return _try_decrypt(hex_str, machine_key)
    except Exception:
        # Compatibility: try legacy constant if current key fails
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


def get_provider_key(db_path, provider):
    """Read a decrypted API key from the sqlite db without putting it on argv."""
    path = Path(os.path.expanduser(str(db_path))).resolve()
    if not is_db_path_allowed(path):
        return ""
    if path.is_symlink() or path.parent.is_symlink():
        return ""
    if not path.exists():
        return ""
    conn = sqlite3.connect(str(path), timeout=5.0)
    try:
        row = conn.execute(
            "SELECT api_key FROM api_keys WHERE provider = ?",
            (provider,),
        ).fetchone()
        if not row:
            return ""
        return decrypt(row[0], get_machine_id())
    except Exception:
        return ""
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
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                provider TEXT PRIMARY KEY,
                api_key TEXT NOT NULL,
                endpoint TEXT DEFAULT '',
                custom_curl TEXT DEFAULT ''
            )
        """)
        conn.commit()

        machine_key = get_machine_id()

        if cmd == "set":
            if len(args) < 2:
                print(
                    json.dumps(
                        {
                            "error": "set requires <provider> <key> [endpoint] [custom_curl]"
                        }
                    ),
                    flush=True,
                )
                sys.exit(1)

            provider = args[0]
            api_key = encrypt(args[1], machine_key)
            endpoint = args[2] if len(args) > 2 else ""
            custom_curl = args[3] if len(args) > 3 else ""

            cursor.execute(
                "INSERT OR REPLACE INTO api_keys (provider, api_key, endpoint, custom_curl) VALUES (?, ?, ?, ?)",
                (provider, api_key, endpoint, custom_curl),
            )
            conn.commit()
            print(json.dumps({"status": "ok"}), flush=True)

        elif cmd == "get":
            if not args:
                print(json.dumps({"error": "get requires <provider>"}), flush=True)
                sys.exit(1)

            cursor.execute("SELECT provider, api_key, endpoint, custom_curl FROM api_keys WHERE provider = ?", (args[0],))
            row = cursor.fetchone()
            if row:
                res = {
                    "provider": row[0],
                    "api_key": decrypt(row[1], machine_key),
                    "endpoint": row[2],
                    "custom_curl": row[3],
                }
                print(json.dumps(res), flush=True)
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

        elif cmd == "list":
            cursor.execute("SELECT provider, api_key, endpoint, custom_curl FROM api_keys")
            rows = cursor.fetchall()
            results = []
            for row in rows:
                results.append(
                    {
                        "provider": row[0],
                        "api_key": decrypt(row[1], machine_key),
                        "endpoint": row[2],
                        "custom_curl": row[3],
                    }
                )
            print(json.dumps(results), flush=True)

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
