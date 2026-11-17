"""Windows FiveM launcher with a separate, time-limited local human permission.

Only connects to loopback FXServer. This permission never arms Full Control.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

DEFAULT_PORT = 30120
MAX_GRANT_SECONDS = 3600

def _grant_path():
    from .natives import _cache_dir
    return _cache_dir() / "client-launch-grant.json"

def _port(value):
    if not isinstance(value, int) or isinstance(value, bool) or not 1024 <= value <= 65535:
        raise ValueError("Local FXServer port must be 1024..65535")
    return value

def _client_path():
    if sys.platform != "win32":
        raise ValueError("FiveM client launch is available on Windows only")
    configured = os.environ.get("CFX_FIVEM_EXE")
    local = os.environ.get("LOCALAPPDATA")
    if not configured and not local:
        raise ValueError("Set CFX_FIVEM_EXE to the FiveM.exe file on this Windows machine")
    candidate = Path(configured).expanduser() if configured else Path(local) / "FiveM" / "FiveM.exe"
    if not candidate.is_file() or candidate.name.casefold() != "fivem.exe":
        raise ValueError("Set CFX_FIVEM_EXE to an existing FiveM.exe file")
    return candidate.resolve()

def permission():
    try:
        data=json.loads(_grant_path().read_text(encoding="utf-8"))
        expiry=int(data["expires_at"])
        port=_port(data["port"])
    except (OSError, ValueError, TypeError, KeyError):
        return {"approved":False, "expires_at":None, "port":None}
    return {"approved":expiry>int(time.time()),"expires_at":expiry,"port":port}

def arm(port=DEFAULT_PORT, minutes=15):
    """Human terminal only. No MCP tool can grant launch permission."""
    _port(port)
    if not isinstance(minutes,int) or isinstance(minutes,bool) or not 1<=minutes<=60:
        raise ValueError("Minutes must be 1..60")
    if not sys.stdin.isatty():
        raise ValueError("Launch authorization requires an interactive local terminal")
    _client_path()
    response=input(f"Allow FiveM to launch and join 127.0.0.1:{port} for {minutes} minutes? Type 'ALLOW FIVEM LAUNCH': ")
    if response!="ALLOW FIVEM LAUNCH":
        raise ValueError("Launch permission refused")
    dest=_grant_path()
    dest.parent.mkdir(parents=True,exist_ok=True)
    payload={"expires_at":int(time.time())+60*minutes,"port":port}
    fd,temp=tempfile.mkstemp(prefix=".client-launch-",dir=str(dest.parent))
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as stream:
            json.dump(payload,stream)
        os.replace(temp,dest)
    finally:
        if os.path.exists(temp):os.unlink(temp)
    return permission()

def disarm():
    _grant_path().unlink(missing_ok=True)
    return {"approved":False}

def preview(port=DEFAULT_PORT):
    _port(port)
    path=_client_path()
    grant=permission()
    return {"client_executable":str(path),"host":"127.0.0.1","port":port,
            "approved":bool(grant["approved"] and grant["port"]==port),
            "expires_at":grant["expires_at"],"will_launch":False,
            "note":"Launch-only permission. Does not enable Full Control or verify game join."}

def launch(port=DEFAULT_PORT):
    _port(port)
    path=_client_path()
    grant=permission()
    if not grant["approved"] or grant["port"]!=port:
        raise ValueError("Explicit authorization required: run cfx-devkit client-launch-arm in a local interactive terminal for this port")
    # Delegate to the desktop shell. ShellExecute from a console-attached MCP
    # can still give FiveM an unsuitable launch context and trigger its guard.
    explorer=Path(os.environ.get('WINDIR',r'C:\Windows'))/'explorer.exe'
    uri=f"fivem://connect/127.0.0.1:{port}"
    subprocess.Popen([str(explorer),uri],shell=False,stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                             creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    return {"launch_requested":True,"launched":False,"pid":None,"launch_method":"windows-explorer-fivem-uri",
            "host":"127.0.0.1","port":port,"connected":False,
            "join_verified":False,"note":"URL handler invoked; requires installed FiveM protocol association. Successful join unverified."}
