"""Explicit, revocable trusted-local-owner delegation; not an isolation boundary."""
import hashlib
import json
import os
from pathlib import Path
import re


def _identity():
    """Read protected grant identity even when its authorization is inactive."""
    try:
        path = Path(os.environ["CFX_LIVE_POLICY_FILE"])
        workspace = Path(os.environ["CFX_WORKSPACE_ROOT"]).resolve(strict=True)
        if not path.is_absolute() or not path.resolve().is_relative_to(workspace):
            return None
        for part in (path, *path.parents):
            if part.is_symlink() or getattr(part.lstat(), "st_file_attributes", 0) & 0x400:
                return None
            if part == workspace:
                break
        if path.stat().st_size > 4096:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] != 1
                or not isinstance(data.get("grant_id"), str)
                or not re.fullmatch(r"[a-f0-9]{32}", data["grant_id"])):
            return None
        cfg = Path(data["server_config"])
        if (data.get("workspace") != str(workspace)
                or not cfg.is_absolute()
                or cfg.parent / ".cfx-devkit" / "delegation.json" != path):
            return None
        return data
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        return None


def policy():
    """Fail closed on missing, malformed, linked or differently targeted policy files."""
    try:
        if os.environ.get("CFX_LIVE_ENABLE") != "1" or os.environ.get("CFX_LIVE_MODE") != "full":
            return None
        data = _identity()
        if data is None:
            return None
        token = os.environ["CFX_LIVE_TOKEN"]
        permissions = data.get("permissions")
        if not isinstance(permissions, list) or any(
                item not in {"full-control", "server-launch", "client-launch", "game-input"}
                for item in permissions):
            return None
        if "server-launch" in permissions and not re.fullmatch(r"[a-f0-9]{64}", str(data.get("server_launch_target", ""))):
            return None
        if (data.get("enabled") is not True
                or len(token) < 32
                or data.get("token_hash") != hashlib.sha256(token.encode()).hexdigest()):
            return None
        cfg = Path(data["server_config"])
        if not cfg.is_file() or not cfg.resolve().is_relative_to(Path(os.environ["CFX_WORKSPACE_ROOT"]).resolve()):
            return None
        port = data.get("port")
        if not isinstance(port, int) or isinstance(port, bool) or not 1024 <= port <= 65535:
            return None
        if revoked(data, "_all"):
            return None
        return data
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        return None


def allows(scope):
    data = policy()
    return data if data and scope in data.get("permissions", []) and not revoked(data, scope) else None


def marker(data, scope):
    return Path(os.environ["CFX_LIVE_POLICY_FILE"]).parent / "revocations" / data["grant_id"] / scope


def revoked(data, scope):
    # Markers only accumulate for this grant. Concurrent revokes never rewrite
    # or resurrect each other's permissions. Explicit reinstallation makes a new grant.
    path = marker(data, scope)
    try:
        for part in (path, path.parent, path.parent.parent):
            if part.is_symlink() or (part.exists() and getattr(part.lstat(), "st_file_attributes", 0) & 0x400):
                return True
        return path.exists()
    except OSError:
        return True


def revoke(scope=None):
    data = _identity()
    if data is None:
        return {"revoked": False, "reason": "no-valid-grant" if os.environ.get("CFX_LIVE_POLICY_FILE") else "not-configured"}
    if scope is not None and scope not in {"full-control", "server-launch", "client-launch", "game-input"}:
        raise ValueError("Invalid delegated scope")
    path = marker(data, scope or "_all")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
    except FileExistsError:
        pass
    return {"revoked": True, "scope": scope or "all", "grant_id": data["grant_id"]}
