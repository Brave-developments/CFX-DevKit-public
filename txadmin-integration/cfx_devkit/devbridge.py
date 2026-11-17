"""Opt-in, read-only, loopback diagnostic ingest for an owned FiveM dev server.

Separate from MCP. Never sends commands to FXServer. Never binds externally.
Never stores player names, IDs, IPs, stack traces or arbitrary user payloads.
Requires a 32+ character random token (CFX_BRIDGE_TOKEN) and explicit opt-in
(CFX_BRIDGE_ENABLE=1). Localhost/host-level credentials remain the user's responsibility.
"""
from __future__ import annotations
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import os
from pathlib import Path
import re
import threading
import time

HOST="127.0.0.1"
PORT=8765
ALLOWED=frozenset(("resource_started","resource_stopped","heartbeat","resource_error"))
RESOURCE=re.compile(r"^[A-Za-z0-9_.-]{1,96}$")
MAX_BODY=1024
MAX_LOG_BYTES=2_000_000
GUARD=threading.Lock()

def storage_path():
    from .natives import _cache_dir
    return _cache_dir()/"dev-bridge.jsonl"

def _token():
    key=os.environ.get("CFX_BRIDGE_TOKEN","")
    if len(key)<32 or len(key)>256 or any(ord(x)<33 or ord(x)>126 for x in key):
        raise ValueError("CFX_BRIDGE_TOKEN must be 32–256 printable ASCII nonspace characters")
    return key

def _enabled():
    if os.environ.get("CFX_BRIDGE_ENABLE")!="1":
        raise ValueError("Development bridge disabled; explicitly set CFX_BRIDGE_ENABLE=1")
    _token()

def _sanitize(packet):
    if not isinstance(packet,dict):
        raise ValueError("Expected JSON object")
    if set(packet)-{"event","resource","detail"}:
        raise ValueError("Unsupported diagnostic keys: no player data, identifiers or arbitrary payloads allowed")
    event=packet.get("event");resource=packet.get("resource")
    if event not in ALLOWED or not isinstance(resource,str) or not RESOURCE.fullmatch(resource):
        raise ValueError("Only resource lifecycle/heartbeat/error reports with safe resource names are allowed")
    detail=packet.get("detail")
    # No raw traceback or arbitrary text is persisted. Error categories only.
    if detail is not None and detail not in ("runtime","load","dependency","unknown"):
        raise ValueError("Detail must be a fixed category, never an error string or player data")
    return {"time_unix":int(time.time()),"event":event,
            "resource":resource,"detail":detail or ""}

def append_record(record,path=None):
    path=path or storage_path()
    path.parent.mkdir(parents=True,exist_ok=True)
    data=json.dumps(record,separators=(",",":"))+"\n"
    with GUARD:
        if path.exists() and path.stat().st_size>MAX_LOG_BYTES:
            rotated=path.with_suffix(".old")
            # Old file also contains sanitized records; only one older batch retained.
            os.replace(path,rotated)
        with path.open("a",encoding="utf-8") as out:out.write(data)

def read_events(limit=50,resource=""):
    if not isinstance(limit,int) or isinstance(limit,bool) or not 1<=limit<=200:
        raise ValueError("limit must be between 1 and 200")
    if resource and (not isinstance(resource,str) or not RESOURCE.fullmatch(resource)):
        raise ValueError("Invalid resource name filter")
    path=storage_path()
    if not path.is_file():return {"connected":False,"events":[],"note":"No local bridge messages recorded"}
    if path.stat().st_size>MAX_LOG_BYTES+MAX_BODY+10000:
        raise ValueError("Bridge log exceeds safe read size")
    result=[];counts=Counter()
    for line in path.read_text(encoding="utf-8").splitlines():
        try:item=json.loads(line)
        except ValueError:continue
        if item.get("event") not in ALLOWED or not isinstance(item.get("resource"),str):continue
        counts[item["event"]]+=1
        if not resource or item["resource"]==resource:result.append(item)
    return {"connected":True,"events":result[-limit:],
            "record_count":sum(counts.values()),"counts":dict(counts),
            "note":"Local validated resource-only records. No live client screenshots, player identities or remote commands."}

def setup_status():
    """Report configuration separately from receiver health and recorded history."""
    configured = False
    reachable = False
    try:
        _enabled()
        configured = True
        from urllib.request import Request, build_opener, ProxyHandler
        from .performance import NoRedirect
        request = Request("http://127.0.0.1:8765/health", headers={"X-CFX-DevKit-Token": _token()})
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=1) as response:
            data = json.loads(response.read(MAX_BODY + 1))
        reachable = data.get("ok") is True and data.get("read_only") is True
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    history = read_events(limit=1)
    return {"enabled_by_default": False, "configured": configured,
            "receiver_reachable": reachable, "records_present": bool(history.get("events")),
            "bind": HOST, "port": PORT,
            "requirements": ["CFX_BRIDGE_ENABLE=1", "CFX_BRIDGE_TOKEN: 32+ printable ASCII characters",
                "set devkit_bridge_enable 1", "set devkit_bridge_token <private token>", "ensure cfx-devkit-reporter"],
            "capabilities": ["sanitized resource lifecycle and explicitly reported error categories"],
            "raw_console_capture": False, "remote_commands": False,
            "documentation": "docs/DEV_BRIDGE.md",
            "note": "Recorded events do not prove current server liveness; arbitrary Lua errors require console logs or explicit reporting."}


def make_server(port=PORT):
    _enabled()
    if not isinstance(port,int) or not (port==0 or 1024<=port<=65535):raise ValueError("Port must be 1024..65535 (or 0 for isolated tests)")
    secret=_token()

    class Handler(BaseHTTPRequestHandler):
        server_version="CFXDevKitBridge/1.0"
        def log_message(self,*args):
            # Do not echo request headers/tokens or arbitrary log payloads
            return
        def reply(self,status,payload):
            body=json.dumps(payload,separators=(",",":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(body)))
            self.send_header("Cache-Control","no-store")
            self.end_headers()
            self.wfile.write(body)
        def auth(self):
            supplied=self.headers.get("X-CFX-DevKit-Token","")
            return hmac.compare_digest(supplied,secret)
        def do_GET(self):
            if not self.auth():return self.reply(401,{"error":"unauthorized"})
            if self.path!="/health":return self.reply(404,{"error":"not found"})
            return self.reply(200,{"ok":True,"mode":"development","read_only":True})
        def do_POST(self):
            if not self.auth():return self.reject_post(401,"unauthorized")
            if self.path!="/event":return self.reject_post(404,"not found")
            raw_len=self.headers.get("Content-Length","")
            if not raw_len.isdecimal():return self.reply(411,{"error":"Content-Length required"})
            length=int(raw_len)
            if not 1<=length<=MAX_BODY:return self.reply(413,{"error":"body too large"})
            try:
                raw=self.rfile.read(length)
                value=json.loads(raw.decode("utf-8"))
                entry=_sanitize(value)
                append_record(entry)
            except (ValueError,UnicodeDecodeError,OSError):
                return self.reply(400,{"error":"invalid diagnostic"})
            return self.reply(202,{"accepted":True})
        def reject_post(self,status,message):
            # Closing with a small unread POST body can reset the socket on
            # Windows before the client receives our rejection. Discard only
            # a valid bounded body; never parse/store it or wait indefinitely.
            value=self.headers.get('Content-Length','')
            if (len(value)<=9 and value.isdecimal() and
                0<int(value)<=MAX_BODY and not self.headers.get('Transfer-Encoding')):
                self.connection.settimeout(1)
                try:self.rfile.read(int(value))
                except OSError:pass
            return self.reply(status,{'error':message})
    return ThreadingHTTPServer((HOST,port),Handler)

def serve(port=PORT):
    http=make_server(port)
    try:
        print(f"CFX development bridge listening on http://{HOST}:{http.server_port} (events only)")
        http.serve_forever(poll_interval=0.1)
    finally:http.server_close()

def main():
    import argparse
    parser=argparse.ArgumentParser(description="Local FiveM development bridge; opt-in, read-only, loopback only")
    parser.add_argument("--port",type=int,default=PORT)
    args=parser.parse_args()
    try:serve(args.port)
    except ValueError as exc:parser.exit(2,f"Error: {exc}\n")

if __name__=="__main__":main()
