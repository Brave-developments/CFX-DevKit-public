"""AI-runnable local installer. Preview first; --apply installs without terminal prompts.

Does not approve tools, arm Full Control, launch/restart FXServer or enable txAdmin mutation.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import venv

ROOT = Path(__file__).resolve().parent
BEGIN = "# BEGIN CFX DEVKIT CONNECTION"
END = "# END CFX DEVKIT CONNECTION"
SKIP = {".git", ".venv", ".local", ".cfx-devkit", "node_modules", "cache", "build"}


def linked(path):
    try:
        return path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400)
    except FileNotFoundError:
        return False


def checked(path, root):
    path = Path(path).absolute()
    root = Path(root).resolve()
    if not path.resolve().is_relative_to(root):
        raise ValueError("Target must remain inside the selected folder")
    for item in (path, *path.parents):
        if linked(item):
            raise ValueError("Linked installation targets are not supported")
        if item == root:
            break
    return path


def find_cfg(workspace, explicit=None):
    if explicit:
        candidate = checked(Path(explicit), workspace)
        if not candidate.is_file():
            raise ValueError("Selected server config does not exist")
        return candidate
    candidates = []
    for directory, folders, files in os.walk(workspace, followlinks=False):
        folders[:] = [name for name in folders if name not in SKIP
                      and not linked(Path(directory) / name)]
        if "server.cfg" in files:
            candidates.append(checked(Path(directory) / "server.cfg", workspace))
    if len(candidates) != 1:
        raise ValueError("Choose --server-cfg: expected exactly one server.cfg in the workspace")
    return candidates[0]


def managed_block(text, body):
    if text.count(BEGIN) != text.count(END) or text.count(BEGIN) > 1:
        raise ValueError("Conflicting installer markers; no files changed")
    block = BEGIN + "\n" + body.rstrip() + "\n" + END
    if BEGIN in text:
        start = text.index(BEGIN)
        end = text.index(END) + len(END)
        if end < start:
            raise ValueError("Invalid installer markers")
        return text[:start] + block + text[end:]
    return text.rstrip() + "\n\n" + block + "\n"


def write_private(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Keep backups private and outside the publicly served resource directory.
    if path.exists():
        backup = path.with_name(path.name + ".cfx-backup")
        if not backup.exists():
            shutil.copy2(path, backup)
            os.chmod(backup, 0o600)
    fd, temporary = tempfile.mkstemp(prefix=".cfx-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def apply_changes(changes):
    originals = {path: (path.read_bytes(), path.stat().st_mode) if path.exists() else None
                 for path, _ in changes}
    attempted = []
    try:
        for path, content in changes:
            attempted.append(path)
            write_private(path, content)
    except OSError:
        for path in reversed(attempted):
            original = originals[path]
            if original is None:
                path.unlink(missing_ok=True)
            else:
                if path.exists() and path.read_bytes() == original[0]:
                    continue
                path.write_bytes(original[0])
                os.chmod(path, original[1])
        raise


def host_path(host, home):
    mapping = {
        "freebuff": home / ".agents/mcp.json",
        "cursor": home / ".cursor/mcp.json",
        "claude": home / ".claude.json",
        "gemini": home / ".gemini/settings.json",
        "roo": home / ".roo/mcp.json",
        "copilot": home / ".copilot/mcp-config.json",
        "codex": home / ".codex/config.toml",
    }
    return checked(mapping[host], home)


def configure_host(path, host, entries):
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if host == "codex":
        existing = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END), "", text, flags=re.S)
        if re.search(r"^\s*\[mcp_servers\.cfx_(development|txadmin)(?:\.|\])", existing, re.M):
            raise ValueError("Existing Codex CFX entries need migration before installation")
        blocks = []
        for name, entry in entries.items():
            blocks.append("[mcp_servers." + name.replace("-", "_") + "]\n"
                          + "command = " + json.dumps(entry["command"]) + "\n"
                          + "args = " + json.dumps(entry["args"]) + "\n"
                          + "env = { " + ", ".join(key + " = " + json.dumps(value) for key, value in entry["env"].items()) + " }")
        return managed_block(text, "\n\n".join(blocks))
    data = json.loads(text) if text.strip() else {}
    servers = data.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError("Expected an mcpServers object")
    servers.update(entries)
    return json.dumps(data, indent=2) + "\n"


def prepare(workspace, host, profile="both", server_cfg=None, home=None):
    workspace = Path(workspace).resolve()
    if not workspace.is_dir():
        raise ValueError("Workspace must be an existing directory")
    home = Path(home or Path.home()).resolve()
    config_path = checked(workspace / ".roo/mcp.json", workspace) if host == "roo" else host_path(host, home)
    python = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    env = {"CFX_WORKSPACE_ROOT": str(workspace), "CFX_ENABLE_WRITES": "0", "CFX_ENABLE_NETWORK": "0"}
    entries = {}
    changes = []
    if profile in {"both", "development"}:
        entries["cfx-development"] = {"type": "stdio", "command": str(python),
            "args": ["-m", "cfx_devkit.profiles", "development"], "env": env}
    if profile in {"both", "integration"}:
        cfg = find_cfg(workspace, server_cfg)
        resources = checked(cfg.parent / "resources", workspace)
        if not resources.is_dir():
            raise ValueError("Selected server must have an existing resources folder")
        private = checked(cfg.parent / ".cfx-devkit", workspace)
        state = checked(private / "connection.json", workspace)
        old = json.loads(state.read_text(encoding="utf-8")) if state.exists() else {}
        token = old.get("env", {}).get("CFX_LIVE_TOKEN") or secrets.token_urlsafe(48)
        if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", token):
            raise ValueError("Invalid existing connection token")
        cache = checked(private / ("data-" + hashlib.sha256(token.encode()).hexdigest()[:16]), workspace)
        live_env = {**env, "CFX_LIVE_ENABLE": "1", "CFX_LIVE_MODE": "full", "CFX_LIVE_TOKEN": token,
                    "CFX_DEVKIT_DATA_DIR": str(cache)}
        settings = json.dumps({"env": live_env}, indent=2) + "\n"
        private_cfg = checked(private / "connection.cfg", workspace)
        cfg_text = cfg.read_text(encoding="utf-8-sig")
        outside_block = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END), "", cfg_text, flags=re.S)
        if re.search(r"^\s*(?:setr?\s+devkit_live_|ensure\s+cfx-devkit-live\b)", outside_block, re.M):
            raise ValueError("Existing bridge configuration needs migration; no files changed")
        resource = checked(resources / "cfx-devkit-live", workspace)
        source = ROOT / "txadmin-integration/examples/cfx-devkit-live"
        if not source.is_dir():
            source = ROOT / "examples/cfx-devkit-live"
        for name in ("fxmanifest.lua", "server.lua", "client.lua"):
            original = source / name
            content = original.read_text(encoding="utf-8")
            if name == "fxmanifest.lua" and "lua54" not in content:
                content += "\nlua54 'yes'\n"
            target = checked(resource / name, workspace)
            if target.exists() and target.read_text(encoding="utf-8") != content:
                raise ValueError("Existing connection resource differs; refusing to overwrite it")
            changes.append((target, content))
        changes.extend([(state, settings), (private_cfg,
            'set devkit_live_enable 1\nset devkit_live_mode "full"\n'
            + 'set devkit_live_token "' + token + '"\nsetr devkit_live_client_enabled 0\n'),
            (cfg, managed_block(cfg_text, 'exec .cfx-devkit/connection.cfg\nensure cfx-devkit-live'))])
        entries["cfx-txadmin"] = {"type": "stdio", "command": str(python),
            "args": ["-m", "cfx_devkit.connection", "--settings", str(state)], "env": env}
    changes.append((config_path, configure_host(config_path, host, entries)))
    return python, changes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--host", required=True, choices=("freebuff", "cursor", "claude", "gemini", "roo", "copilot", "codex"))
    parser.add_argument("--profile", choices=("both", "development", "integration"), default="both")
    parser.add_argument("--server-cfg", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    python, changes = prepare(args.workspace, args.host, args.profile, args.server_cfg)
    if not args.apply:
        print(json.dumps({"preview": True, "files": [str(path) for path, _ in changes],
                          "next": "Repeat with --apply after reviewing the selected paths"}))
        return
    if not python.exists():
        venv.EnvBuilder(with_pip=True).create(ROOT / ".venv")
    package = ROOT / ("txadmin-integration" if args.profile == "integration" else "skills-and-rules")
    if not (package / "pyproject.toml").exists():
        package = ROOT
    # Dependency installation finishes before modifying any server or host files.
    subprocess.run([str(python), "-m", "pip", "install", str(package)], check=True)
    apply_changes(changes)
    print(json.dumps({"installed": True, "host": args.host, "server_restarted": False,
        "control_armed": False, "client_execution_enabled": False,
        "next": "Enable the connector in your AI app. Start only cfx-devkit-live through an existing authorized connection; otherwise the resource loads on the next normal server start. Full Control still requires the owner's local approval."}))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError):
        # Never render config contents, tokens, pip environment or raw exceptions.
        print("Installation failed. Check selected paths, existing bridge/config conflicts, and Python installation.", file=sys.stderr)
        sys.exit(1)
