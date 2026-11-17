"""AI-runnable local installer. Preview first; --apply installs without terminal prompts.

Never approves host connector permissions or launches/restarts FXServer during installation.
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
    private_folders = {parent for path, _ in changes for parent in path.parents if parent.name == ".cfx-devkit"}
    for folder in private_folders:
        restrict_private_folder(folder)
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


def restrict_private_folder(folder):
    folder.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(folder, 0o700)
        return
    # chmod alone does not protect Windows secrets. Use an explicit protected DACL.
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    script = r'''
$ErrorActionPreference = 'Stop'
$acl = New-Object System.Security.AccessControl.DirectorySecurity
$acl.SetAccessRuleProtection($true, $false)
$owner = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$acl.SetOwner($owner)
foreach ($sid in @($owner, [System.Security.Principal.SecurityIdentifier]'S-1-5-18', [System.Security.Principal.SecurityIdentifier]'S-1-5-32-544')) {
    $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($sid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
    $acl.AddAccessRule($rule)
}
[System.IO.Directory]::SetAccessControl($env:CFX_SETUP_PRIVATE_DIR, $acl)
'''
    result = subprocess.run([str(powershell), "-NoProfile", "-NonInteractive", "-Command", script],
                            env={**os.environ, "CFX_SETUP_PRIVATE_DIR": str(folder)}, capture_output=True, text=True)
    if result.returncode:
        raise OSError("Cannot protect private connection directory")


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


def prepare(workspace, host, profile="both", server_cfg=None, home=None, unattended=False, port=30120, launch_target=None, diagnostics=False):
    if unattended and profile == "development":
        raise ValueError("Unattended control requires the integration profile")
    if diagnostics and profile == "development":
        raise ValueError("Diagnostics requires the integration profile")
    if launch_target is not None and not re.fullmatch(r"[a-f0-9]{64}", launch_target):
        raise ValueError("Server launch target must be the complete verified target_id")
    workspace = Path(workspace).resolve()
    if not workspace.is_dir():
        raise ValueError("Workspace must be an existing directory")
    if not isinstance(port, int) or isinstance(port, bool) or not 1024 <= port <= 65535:
        raise ValueError("Port must be 1024..65535")
    home = Path(home or Path.home()).resolve()
    config_path = checked(workspace / ".roo/mcp.json", workspace) if host == "roo" else host_path(host, home)
    python = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    references = checked(ROOT / ".cfx-devkit/reference-data", ROOT)
    env = {"CFX_WORKSPACE_ROOT": str(workspace), "CFX_ENABLE_WRITES": "0", "CFX_ENABLE_NETWORK": "0",
           "CFX_DEVKIT_DATA_DIR": str(references)}
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
        token = secrets.token_urlsafe(48) if unattended else old.get("env", {}).get("CFX_LIVE_TOKEN") or secrets.token_urlsafe(48)
        if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", token):
            raise ValueError("Invalid existing connection token")
        cache = checked(private / ("data-" + hashlib.sha256(token.encode()).hexdigest()[:16]), workspace)
        policy_file = checked(private / "delegation.json", workspace)
        permissions = ["full-control", "client-launch", "game-input"]
        if launch_target:
            permissions.append("server-launch")
        policy = {"version": 1, "grant_id": secrets.token_hex(16), "enabled": bool(unattended), "workspace": str(workspace),
                  "server_config": str(cfg.resolve()), "token_hash": hashlib.sha256(token.encode()).hexdigest(),
                  "port": port, "server_launch_target": launch_target, "permissions": permissions}
        live_env = {**env, "CFX_LIVE_ENABLE": "1", "CFX_LIVE_MODE": "full", "CFX_LIVE_TOKEN": token,
                    "CFX_DEVKIT_DATA_DIR": str(cache), "CFX_LIVE_POLICY_FILE": str(policy_file)}
        bridge_token = None
        if diagnostics:
            bridge_token = secrets.token_urlsafe(48)
            live_env.update(CFX_BRIDGE_ENABLE="1", CFX_BRIDGE_TOKEN=bridge_token)
        settings = json.dumps({"env": live_env}, indent=2) + "\n"
        private_cfg = checked(private / "connection.cfg", workspace)
        cfg_text = cfg.read_text(encoding="utf-8-sig")
        outside_block = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END), "", cfg_text, flags=re.S)
        if re.search(r"^\s*(?:setr?\s+devkit_live_|ensure\s+cfx-devkit-live\b)", outside_block, re.M):
            raise ValueError("Existing bridge configuration needs migration; no files changed")
        if diagnostics and re.search(r"^\s*(?:setr?\s+devkit_bridge_|ensure\s+cfx-devkit-reporter\b)", outside_block, re.M):
            raise ValueError("Existing diagnostics configuration needs migration; no files changed")
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
        diagnostic_cfg = ""
        diagnostic_ensure = ""
        if diagnostics:
            source = ROOT / "txadmin-integration/examples/cfx-devkit-reporter"
            if not source.is_dir():
                source = ROOT / "examples/cfx-devkit-reporter"
            for name in ("fxmanifest.lua", "server.lua"):
                content = (source / name).read_text(encoding="utf-8")
                if name == "fxmanifest.lua" and "lua54" not in content:
                    content += "\nlua54 'yes'\n"
                target = checked(resources / "cfx-devkit-reporter" / name, workspace)
                if target.exists() and target.read_text(encoding="utf-8") != content:
                    raise ValueError("Existing reporter differs; refusing to overwrite it")
                changes.append((target, content))
            diagnostic_cfg = 'set devkit_bridge_enable 1\nset devkit_bridge_token "' + bridge_token + '"\n'
            diagnostic_ensure = "\nensure cfx-devkit-reporter"
        changes.extend([(state, settings), (policy_file, json.dumps(policy, indent=2) + "\n"), (private_cfg,
            'set devkit_live_enable 1\nset devkit_live_mode "full"\n'
            + 'set devkit_live_token "' + token + '"\nsetr devkit_live_client_enabled 0\n' + diagnostic_cfg),
            (cfg, managed_block(cfg_text, 'exec .cfx-devkit/connection.cfg\nensure cfx-devkit-live' + diagnostic_ensure))])
        entries["cfx-txadmin"] = {"type": "stdio", "command": str(python),
            "args": ["-m", "cfx_devkit.connection", "--settings", str(state)], "env": env}
    changes.append((config_path, configure_host(config_path, host, entries)))
    return python, changes


def sync_references(python):
    env = {**os.environ, "CFX_ENABLE_NETWORK": "1", "CFX_DEVKIT_DATA_DIR": str(ROOT / ".cfx-devkit/reference-data")}
    for command in ("sync-natives", "sync-animations"):
        result = subprocess.run([str(python), "-m", "cfx_devkit.cli", command],
                                env=env, capture_output=True, text=True, timeout=240)
        if result.returncode:
            raise ValueError("Reference download failed; previous validated caches remain usable")
    statuses = {}
    for command in ("native-status", "animation-status"):
        result = subprocess.run([str(python), "-m", "cfx_devkit.cli", command],
                                env={**env, "CFX_ENABLE_NETWORK": "0"}, capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise ValueError("Reference status verification failed")
        statuses[command] = json.loads(result.stdout)
    datasets = statuses["native-status"].get("datasets", {})
    if (any(datasets.get(name, {}).get("origin") != "cached" or
            datasets.get(name, {}).get("count", 0) < 200 for name in ("gta5", "cfx"))
            or statuses["animation-status"].get("complete") is not True):
        raise ValueError("Reference sync did not produce validated full datasets")
    return statuses


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--host", required=True, choices=("freebuff", "cursor", "claude", "gemini", "roo", "copilot", "codex"))
    parser.add_argument("--profile", choices=("both", "development", "integration"), default="both")
    parser.add_argument("--server-cfg", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--allow-unattended-control", action="store_true",
                        help="Delegate console/Lua, FiveM launch and foreground input until revoked; server launch additionally requires --server-launch-target")
    parser.add_argument("--port", type=int, default=30120)
    parser.add_argument("--server-launch-target", help="Complete selected target_id from cfx_fxserver_status; omitted means no delegated server launch")
    parser.add_argument("--diagnostics", action="store_true", help="Install the read-only resource reporter and automatically run its loopback receiver")
    parser.add_argument("--sync-references", action="store_true", help="Download native/animation references to this user's local cache; no redistribution")
    args = parser.parse_args()
    if args.sync_references and args.profile == "integration":
        parser.error("Reference downloads require the development profile or both profiles")
    python, changes = prepare(args.workspace, args.host, args.profile, args.server_cfg,
                              unattended=args.allow_unattended_control, port=args.port, launch_target=args.server_launch_target,
                              diagnostics=args.diagnostics)
    if not args.apply:
        print(json.dumps({"preview": True, "files": [str(path) for path, _ in changes],
                          "unattended_control": args.allow_unattended_control,
                          "delegated_permissions": (["full-control", "client-launch", "game-input"] +
                                                    (["server-launch"] if args.server_launch_target else [])) if args.allow_unattended_control else [],
                          "delegation_duration": "until revoked" if args.allow_unattended_control else None,
                          "server_launch_target": args.server_launch_target,
                          "diagnostics": args.diagnostics, "download_references": args.sync_references,
                          "next": "Repeat with --apply after reviewing the selected paths and privileges"}))
        return
    if not python.exists():
        venv.EnvBuilder(with_pip=True).create(ROOT / ".venv")
    package = ROOT / ("txadmin-integration" if args.profile == "integration" else "skills-and-rules")
    if not (package / "pyproject.toml").exists():
        package = ROOT
    # Dependency installation finishes before modifying any server or host files.
    subprocess.run([str(python), "-m", "pip", "install", str(package)], check=True)
    references = sync_references(python) if args.sync_references else None
    apply_changes(changes)
    print(json.dumps({"installed": True, "host": args.host, "server_restarted": False,
        "delegation_enabled": args.allow_unattended_control, "client_execution_enabled": False,
        "diagnostics_configured": args.diagnostics, "references": references,
        "next": "Enable the connector in your AI app. Load cfx-devkit-live through an existing authorized connection or the next normal server start. Unattended delegation removes CFX terminal arming only; host approvals and the native txAdmin review gate remain."}))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError):
        # Never render config contents, tokens, pip environment or raw exceptions.
        print("Installation failed. Check selected paths, existing bridge/config conflicts, and Python installation.", file=sys.stderr)
        sys.exit(1)
