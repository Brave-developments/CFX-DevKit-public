"""Explicitly armed FULL FiveM/FXServer control for an OWNED LOCAL DEVELOPMENT server.

Not an OS shell, txAdmin session, RCON service or Internet-facing API.
Server and client game code can execute arbitrary FiveM Lua when FULL mode is
armed; that is intentionally privileged and unsafe for production. The owner
must arm it in an actual terminal. The existing read-only devbridge is separate.

Protocol: authenticated FXServer polls local GET /next and posts /result.
Queued requests are one-shot, bounded and audit-indexed. All HTTP endpoints
are bound to loopback and require a shared token.
"""
from __future__ import annotations
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import math
import os
from pathlib import Path
import re
import secrets
import sqlite3
import sys
import time

HOST="127.0.0.1"
PORT=8767
MAX_REQUEST=24576
MAX_RESULT=16384
SESSION_MAX=3600
REQUEST_TTL=90
KINDS=frozenset(("server_info","server_resources","server_players","server_command","server_lua","client_lua","client_action"))
ACTIONS=frozenset(("position","teleport","freeze","unfreeze","clear_tasks","heal","play_animation"))
HEX_ID=re.compile(r"^[a-f0-9]{32}$")
RESOURCE=re.compile(r"^[a-zA-Z0-9_-]{1,80}$")

def _now():return int(time.time())

def _db_path():
    from .natives import _cache_dir
    return _cache_dir()/"live-control.sqlite3"

def _connect_raw():
    db=_db_path()
    db.parent.mkdir(parents=True,exist_ok=True)
    if not db.exists():
        try:
            fd=os.open(db,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            os.close(fd)
        except FileExistsError:
            pass  # Competing broker/client created the DB first.
    conn=sqlite3.connect(str(db),timeout=6,isolation_level=None)
    conn.row_factory=sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS session
      (id INTEGER PRIMARY KEY CHECK (id=1), started_at INTEGER NOT NULL,
       expires_at INTEGER NOT NULL, reason TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS requests
      (id TEXT PRIMARY KEY, kind TEXT NOT NULL, target INTEGER NOT NULL,
       body TEXT NOT NULL, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
       status TEXT NOT NULL, result TEXT, finished_at INTEGER)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS runtime
      (id INTEGER PRIMARY KEY CHECK(id=1), last_poll_at INTEGER NOT NULL)""")
    return conn

@contextmanager
def _connect():
    """Commit/rollback and CLOSE SQLite handles (Windows otherwise locks DB files)."""
    conn=_connect_raw()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _config():
    if os.environ.get("CFX_LIVE_ENABLE")!="1" or os.environ.get("CFX_LIVE_MODE")!="full":
        raise ValueError("Full control is disabled: requires CFX_LIVE_ENABLE=1 and CFX_LIVE_MODE=full")
    token=os.environ.get("CFX_LIVE_TOKEN","")
    if not 32<=len(token)<=256 or any(not 33<=ord(x)<=126 for x in token):
        raise ValueError("Configure a unique private CFX_LIVE_TOKEN of 32–256 nonspace ASCII characters")
    return token

def _active(conn):
    row=conn.execute("SELECT started_at,expires_at,reason FROM session WHERE id=1").fetchone()
    return row if row and row["expires_at"]>_now() else None

def _expiry(conn):
    conn.execute("UPDATE requests SET status='expired',body='' WHERE status='queued' AND expires_at<=?",(_now(),))
    conn.execute("UPDATE requests SET status='timed_out',body='' WHERE status='sent' AND expires_at+45<=?",(_now(),))

def _identifier(request_id):
    if not isinstance(request_id,str) or not HEX_ID.fullmatch(request_id):
        raise ValueError("Expected a 32-character request ID")
    return request_id

def arm(minutes=15):
    """CLI only. Not exposed in MCP or HTTP."""
    _config()
    if not isinstance(minutes,int) or isinstance(minutes,bool) or not 1<=minutes<=60:
        raise ValueError("Minutes must be 1..60")
    if not sys.stdin.isatty():
        raise ValueError("Full access must be armed from a human interactive terminal")
    print("WARNING: FULL CONTROL permits arbitrary FiveM client/server Lua and FXServer console commands.")
    print("Use ONLY a disposable, locally hosted, trusted FiveM development server.")
    phrase="ARM FULL FIVEM CONTROL"
    answer=input(f"To enable {minutes} minutes, type exactly '{phrase}': ")
    if answer!=phrase:raise ValueError("Arming rejected; nothing enabled")
    now=_now()
    with _connect() as conn:
        conn.execute("INSERT OR REPLACE INTO session VALUES(1,?,?,?)",
                     (now,now+minutes*60,"interactive-human-arm"))
    return {"armed":True,"expires_at":now+minutes*60,"minutes":minutes,"note":"MCP may now submit privileged in-game actions to this local development server."}

def disarm():
    """Emergency stop: callable from CLI without an active session."""
    now=_now()
    with _connect() as conn:
        conn.execute("DELETE FROM session")
        conn.execute("UPDATE requests SET status='cancelled',body='' WHERE status='queued'")
    return {"armed":False,"stopped_at":now,
            "note":"Pending commands cancelled; already dispatched game commands cannot be undone."}

def status(request_id=None,limit=15):
    if not isinstance(limit,int) or isinstance(limit,bool) or not 1<=limit<=50:
        raise ValueError("Limit must be 1..50")
    if request_id is not None:_identifier(request_id)
    with _connect() as conn:
        _expiry(conn)
        session=_active(conn)
        tick=conn.execute("SELECT last_poll_at FROM runtime WHERE id=1").fetchone()
        last_poll=tick["last_poll_at"] if tick else None
        online=last_poll is not None and _now()-last_poll<12
        result={"enabled_in_environment":os.environ.get("CFX_LIVE_ENABLE")=="1" and os.environ.get("CFX_LIVE_MODE")=="full",
                "armed":session is not None,
                "arm_expires_at":session["expires_at"] if session else None,
                "server_poll_recent":online,"last_poll_at":last_poll,
                "mode":"full" if session else "locked","bound_host":HOST,"port":PORT}
        if request_id:
            row=conn.execute("SELECT * FROM requests WHERE id=?",(request_id,)).fetchone()
            result["request"]=_row(row) if row else None
        else:
            rows=conn.execute("SELECT * FROM requests ORDER BY created_at DESC,id DESC LIMIT ?",(limit,)).fetchall()
            result["recent"]=[_row(row) for row in rows]
    result["note"]="Status reflects local queue and latest FXServer poll, not proof of game/test success."
    return result

def _row(row):
    # Never expose submitted Lua code or original server commands through listing.
    return {"id":row["id"],"kind":row["kind"],"target":row["target"],"status":row["status"],
            "created_at":row["created_at"],"expires_at":row["expires_at"],
            "finished_at":row["finished_at"],
            "result":json.loads(row["result"]) if row["result"] else None}

def _payload(kind,body,target):
    if not isinstance(kind,str) or kind not in KINDS:raise ValueError("Unsupported game operation")
    if not isinstance(target,int) or isinstance(target,bool) or not 0<=target<=2048:
        raise ValueError("Invalid target server ID")
    if kind.startswith("client_") and target==0:
        raise ValueError("Client operations require a positive authorized player server ID")
    if not kind.startswith("client_") and target!=0:
        raise ValueError("Server operations do not accept a player target")
    if not isinstance(body,str) or len(body.encode("utf-8"))>MAX_REQUEST:
        raise ValueError("Payload JSON must not exceed 24 KiB")
    try:data=json.loads(body)
    except (ValueError,TypeError) as exc:raise ValueError("Invalid payload JSON") from exc
    if not isinstance(data,dict):raise ValueError("Payload must be JSON object")
    if kind in ("server_info","server_resources","server_players"):
        if data:raise ValueError("This operation expects {}")
    elif kind=="server_command":
        if set(data)!={"command"} or not isinstance(data["command"],str) or not 1<=len(data["command"])<=2000:
            raise ValueError("Expected one FXServer console command string of 1–2000 characters")
        if any(x in data["command"] for x in "\n\r\x00"):
            raise ValueError("Console commands must be a single line")
    elif kind in ("server_lua","client_lua"):
        if set(data)!={"code"} or not isinstance(data["code"],str) or not 1<=len(data["code"])<=16000:
            raise ValueError("Lua payload must contain 1–16000 characters of code")
    elif kind=="client_action":
        op=data.get("action")
        if op not in ACTIONS:raise ValueError("Unknown client action")
        expected={"action"}
        if op=="teleport":expected|={"x","y","z"}
        if op=="play_animation":expected|={"dictionary","clip"}
        if set(data)!=expected:raise ValueError("Client action has missing/extra fields")
        if op=="teleport":
            for p in ("x","y","z"):
                value=data[p]
                if not isinstance(value,(float,int)) or isinstance(value,bool) or not math.isfinite(value) or abs(value)>100000:
                    raise ValueError("Invalid teleport coordinate")
        if op=="play_animation":
            for p in ("dictionary","clip"):
                val=data[p]
                if not isinstance(val,str) or not 1<=len(val)<=150 or any(ord(c)<32 for c in val):
                    raise ValueError("Invalid animation identifier")
    return data

def submit(kind,payload_json="{}",target=0):
    _config()
    data=_payload(kind,payload_json,target)
    encoded=json.dumps(data,separators=(",",":"),ensure_ascii=False)
    with _connect() as conn:
        _expiry(conn)
        session=_active(conn)
        if session is None:raise ValueError("Full control not armed. Owner must run 'cfx-devkit live-arm' in an interactive terminal")
        deadline=min(session["expires_at"],_now()+REQUEST_TTL)
        request_id=secrets.token_hex(16)
        conn.execute("INSERT INTO requests VALUES(?,?,?,?,?,?,?,NULL,NULL)",
                     (request_id,kind,target,encoded,_now(),deadline,"queued"))
    return {"id":request_id,"kind":kind,"target":target,"status":"queued","executed":False,
            "expires_at":deadline,"instructions":"Check cfx_live_result for observed outcome. Game server polling must be active."}

def poll():
    _config()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        now=_now()
        conn.execute("INSERT INTO runtime VALUES (1,?) ON CONFLICT(id) DO UPDATE SET last_poll_at=excluded.last_poll_at",(now,))
        _expiry(conn)
        if not _active(conn):
            conn.commit()
            return None
        row=conn.execute("SELECT * FROM requests WHERE status='queued' ORDER BY created_at,id LIMIT 1").fetchone()
        if row is None:
            conn.commit()
            return None
        conn.execute("UPDATE requests SET status='sent',body='' WHERE id=? AND status='queued'",(row["id"],))
        conn.commit()
        return {"id":row["id"],"kind":row["kind"],"target":row["target"],
                "data":json.loads(row["body"])}

def accept_result(payload):
    _config()
    if not isinstance(payload,dict) or set(payload)!={"id","result"}:
        raise ValueError("Malformed result")
    request_id=_identifier(payload["id"])
    value=payload["result"]
    if not isinstance(value,dict) or set(value)-{"ok","value","error","note"}:
        raise ValueError("Unexpected result shape")
    if not isinstance(value.get("ok"),bool):raise ValueError("Result must contain boolean ok")
    raw=json.dumps(value,ensure_ascii=False,default=str)
    if len(raw.encode("utf-8"))>MAX_RESULT:raise ValueError("Result exceeds 16 KiB limit")
    with _connect() as conn:
        row=conn.execute("SELECT status FROM requests WHERE id=?",(request_id,)).fetchone()
        if row is None or row["status"]!="sent":raise ValueError("Unknown or already finalized request")
        changes=conn.execute("UPDATE requests SET status='done',result=?,finished_at=? WHERE id=? AND status='sent'",
                            (raw,_now(),request_id))
        if changes.rowcount!=1:raise ValueError("Result race; request was already completed")
    return {"accepted":True}

def tail_log(channel="server",lines=60,contains=""):
    """Read a bounded tail of a specifically configured LOCAL dev log, without files tool access."""
    _config()
    if channel not in ("server","client"):raise ValueError("Log channel must be server or client")
    if not isinstance(lines,int) or isinstance(lines,bool) or not 1<=lines<=200:
        raise ValueError("Lines must be 1–200")
    if not isinstance(contains,str) or len(contains)>120:
        raise ValueError("Invalid search pattern")
    with _connect() as conn:
        if not _active(conn):raise ValueError("Arm full control before accessing the game log")
    env="CFX_LIVE_SERVER_LOG" if channel=="server" else "CFX_LIVE_CLIENT_LOG"
    target=os.environ.get(env,"")
    if not target:raise ValueError("Set "+env+" to the exact local development log file")
    path=Path(target).expanduser().resolve()
    if not path.is_file() or path.suffix.casefold() not in (".log",".txt"):
        raise ValueError("Expected a local .log or .txt file")
    with path.open("rb") as stream:
        size=path.stat().st_size
        stream.seek(max(0,size-32000))
        content=stream.read(32000).decode("utf-8",errors="replace")
    found=[x for x in content.splitlines() if contains.casefold() in x.casefold()]
    rendered="\n".join(found[-lines:])[-12000:]
    token=os.environ.get("CFX_LIVE_TOKEN","")
    if token:rendered=rendered.replace(token,"[REDACTED_TOKEN]")
    return {"channel":channel,"matched_lines":len(found),"lines":rendered,
            "truncated_bytes":size>32000,"note":"Only the configured development log tail. Client identifiers or other private log content may be present."}

def make_server(port=PORT):
    token=_config()
    if not isinstance(port,int) or isinstance(port,bool) or (port!=0 and not 1024<=port<=65535):
        raise ValueError("Invalid broker port")
    class Handler(BaseHTTPRequestHandler):
        server_version="CFXDevKitLive/1.0"
        def log_message(self,*args):pass
        def response(self,code,data):
            binary=json.dumps(data,separators=(",",":"),ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(binary)))
            self.send_header("Cache-Control","no-store")
            self.end_headers()
            self.wfile.write(binary)
        def auth(self):
            return hmac.compare_digest(self.headers.get("X-CFX-Live-Token",""),token)
        def do_GET(self):
            if not self.auth():return self.response(401,{"error":"unauthorized"})
            if self.path=="/next":
                try:item=poll()
                except (ValueError,sqlite3.Error):return self.response(503,{"error":"not ready"})
                return self.response(200,{"request":item})
            if self.path=="/health":
                return self.response(200,{"ok":True,"armed":status()["armed"]})
            return self.response(404,{"error":"not found"})
        def do_POST(self):
            if not self.auth():return self.response(401,{"error":"unauthorized"})
            if self.path!="/result":return self.response(404,{"error":"not found"})
            length=self.headers.get("Content-Length","")
            if not length.isdecimal() or not 1<=int(length)<=MAX_RESULT+800:
                return self.response(413,{"error":"invalid request size"})
            try:answer=accept_result(json.loads(self.rfile.read(int(length)).decode("utf-8")))
            except (ValueError,UnicodeError,sqlite3.Error):return self.response(400,{"error":"invalid result"})
            return self.response(200,answer)
    return ThreadingHTTPServer((HOST,port),Handler)

def serve(port=PORT):
    broker=make_server(port)
    try:
        print(f"CFX DevKit Full Control broker bound ONLY to {HOST}:{broker.server_port}")
        broker.serve_forever(poll_interval=0.2)
    finally:broker.server_close()

def main():
    import argparse
    parser=argparse.ArgumentParser(description="Full-control FiveM dev-only loopback broker")
    parser.add_argument("--port",type=int,default=PORT)
    args=parser.parse_args()
    serve(args.port)

if __name__=="__main__":main()
