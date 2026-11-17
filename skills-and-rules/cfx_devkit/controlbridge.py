"""Development-only allowlisted FXServer resource control with *human CLI approval*.

Separate from the read-only devbridge. MCP may PROPOSE an operation but cannot
approve it. A local human must enter a confirmation in a real interactive
terminal; FXServer polls approved requests from an authenticated loopback HTTP
broker. No shell/Lua evaluation, arbitrary console commands, or player data.

Security model: Same trusted machine as FXServer, trusted OS account, private
convars ('set', never 'setr'), no port forwarding. The broker cannot protect
against a fully compromised local user or already-privileged server resources.
"""
from __future__ import annotations
from contextlib import contextmanager
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import sys
import time

HOST="127.0.0.1"
PORT=8766
TTL_SECONDS=600
ID=re.compile(r"^[a-f0-9]{24}$")
RESOURCE=re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
ACTIONS=frozenset({"ensure","restart","stop"})
STATES=frozenset({"started","stopped","starting","stopping","missing","unknown","uninitialized"})
RESERVED=frozenset({"cfx-devkit-controller","cfx-devkit-reporter","txadmin"})
MAX_POST=600

def database_path():
    from .natives import _cache_dir
    return _cache_dir()/"dev-control.sqlite3"

def _settings():
    if os.environ.get("CFX_CONTROL_ENABLE")!="1":
        raise ValueError("Control disabled; configure CFX_CONTROL_ENABLE=1 explicitly on a development host")
    token=os.environ.get("CFX_CONTROL_TOKEN","")
    if not (32<=len(token)<=256) or any(ord(c)<33 or ord(c)>126 for c in token):
        raise ValueError("CFX_CONTROL_TOKEN must be a private 32–256 printable nonspace ASCII token")
    resource_text=os.environ.get("CFX_CONTROL_RESOURCES","")
    allowed={v.strip() for v in resource_text.split(",") if v.strip()}
    if not allowed or any(not RESOURCE.fullmatch(v) or v.casefold() in RESERVED for v in allowed):
        raise ValueError("CFX_CONTROL_RESOURCES must list explicit, safe resource names (no wildcard)")
    action_text=os.environ.get("CFX_CONTROL_ACTIONS","restart")
    actions={v.strip() for v in action_text.split(",") if v.strip()}
    if not actions or not actions<=ACTIONS:
        raise ValueError("CFX_CONTROL_ACTIONS must be explicit subset of ensure,restart,stop")
    return token,allowed,actions

def _connect_raw():
    path=database_path()
    path.parent.mkdir(parents=True,exist_ok=True)
    conn=sqlite3.connect(str(path),timeout=5,isolation_level=None)
    conn.row_factory=sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS requests (
        id TEXT PRIMARY KEY, action TEXT NOT NULL, resource TEXT NOT NULL,
        reason TEXT NOT NULL, created_at INTEGER NOT NULL,
        expires_at INTEGER NOT NULL, status TEXT NOT NULL,
        observed_state TEXT, reported_at INTEGER
    )""")
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


def _id(value):
    if not isinstance(value,str) or not ID.fullmatch(value):
        raise ValueError("Invalid proposal ID")
    return value

def _public(row):
    if row is None:return None
    return {field:row[field] for field in
        ("id","action","resource","reason","created_at","expires_at","status","observed_state","reported_at")}

def _expired(conn):
    conn.execute("UPDATE requests SET status='expired' WHERE status IN ('proposed','approved') AND expires_at<=?",(int(time.time()),))

def status(request_id=None):
    # Status is read-only even while disabled and never discloses secrets.
    enabled=os.environ.get("CFX_CONTROL_ENABLE")=="1"
    base={"enabled":enabled,"server_command_access":"allowlisted resource lifecycle only",
          "mcp_can_approve":False,"requires_human_cli_confirmation":True,"bind":HOST,
          "port":PORT,"current_host_connected":"not_verified"}
    if request_id is not None:
        _id(request_id)
        with _connect() as conn:
            _expired(conn)
            base["request"]=_public(conn.execute("SELECT * FROM requests WHERE id=?",(request_id,)).fetchone())
    else:
        if enabled:
            try:
                _,allow,actions=_settings()
                base["resources"]=sorted(allow)
                base["actions"]=sorted(actions)
            except ValueError as exc:base["configuration_error"]=str(exc).split(";")[0]
        with _connect() as conn:
            _expired(conn)
            base["counts"]={row[0]:row[1] for row in conn.execute("SELECT status,COUNT(*) FROM requests GROUP BY status")}
    return base

def propose(action,resource,reason):
    _,allowed,actions=_settings()
    if not isinstance(action,str) or action not in actions:raise ValueError("Action not allowed by CFX_CONTROL_ACTIONS")
    if not isinstance(resource,str) or not RESOURCE.fullmatch(resource) or resource not in allowed:
        raise ValueError("Resource not explicitly permitted by CFX_CONTROL_RESOURCES")
    if not isinstance(reason,str) or not 4<=len(reason)<=160 or "\n" in reason or "\r" in reason or any(ord(c)<32 for c in reason):
        raise ValueError("Provide a short, single-line reason (4–160 characters)")
    now=int(time.time())
    ticket=secrets.token_hex(12)
    with _connect() as conn:
        _expired(conn)
        conn.execute("INSERT INTO requests VALUES (?,?,?,?,?,?,?,NULL,NULL)",
                     (ticket,action,resource,reason,now,now+TTL_SECONDS,"proposed"))
    return {"request_id":ticket,"action":action,"resource":resource,"reason":reason,
            "status":"proposed","expires_in_seconds":TTL_SECONDS,
            "human_action":f"Run cfx-devkit control-approve {ticket} in your own interactive terminal.",
            "executed":False,"note":"AI can propose but cannot approve. The broker must be running and FXServer opted-in."}

def review_cli(request_id,approve):
    """CLI-only function. Never register as an MCP tool or HTTP endpoint."""
    _settings()
    _id(request_id)
    if not sys.stdin.isatty():raise ValueError("Approval/rejection needs a real interactive terminal")
    with _connect() as conn:
        _expired(conn)
        row=conn.execute("SELECT * FROM requests WHERE id=?",(request_id,)).fetchone()
        if row is None or row["status"]!="proposed":raise ValueError("No pending unexpired proposal")
        _,allowed,actions=_settings()
        if row["resource"] not in allowed or row["action"] not in actions:
            raise ValueError("Current policy no longer permits this request")
        print(f"FiveM DEVELOPMENT server resource change\n  Action: {row['action']}\n  Resource: {row['resource']}\n  Reason: {row['reason']}\n  Expires: {row['expires_at']}")
        expected=f"{'APPROVE' if approve else 'REJECT'} {row['action']} {row['resource']}"
        response=input(f"Type exactly [{expected}]: ")
        if response!=expected:raise ValueError("Confirmation did not match; no change")
        new_state="approved" if approve else "rejected"
        updated=conn.execute("UPDATE requests SET status=? WHERE id=? AND status='proposed' AND expires_at>?",
                             (new_state,request_id,int(time.time())))
        if updated.rowcount!=1:raise ValueError("Proposal expired or changed before confirmation")
    return {"id":request_id,"status":new_state,"executed":False}

def claim():
    """Called solely by authenticated FXServer GET /next."""
    _,allowed,actions=_settings()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        _expired(conn)
        rows=conn.execute("SELECT * FROM requests WHERE status='approved' ORDER BY created_at,id LIMIT 20").fetchall()
        chosen=next((r for r in rows if r["resource"] in allowed and r["action"] in actions),None)
        if chosen is None:
            conn.commit()
            return None
        conn.execute("UPDATE requests SET status='dispatched' WHERE id=? AND status='approved'",(chosen["id"],))
        conn.commit()
        return {"id":chosen["id"],"action":chosen["action"],"resource":chosen["resource"]}
    # Dispatched operations are never auto-retried: no duplicate restarts.

def record_result(body):
    _settings()
    if not isinstance(body,dict) or set(body)!={"id","resource","action","observed_state"}:
        raise ValueError("Malformed resource observation")
    request_id=_id(body.get("id"))
    if body.get("observed_state") not in STATES:raise ValueError("Invalid resource state")
    with _connect() as conn:
        updated=conn.execute("""UPDATE requests
            SET status='reported', observed_state=?, reported_at=?
            WHERE id=? AND resource=? AND action=? AND status='dispatched'""",
            (body["observed_state"],int(time.time()),request_id,body["resource"],body["action"]))
        if updated.rowcount!=1:raise ValueError("Unknown, mismatched or already reported request")
    return {"accepted":True,"success_verified":False,
            "note":"FXServer reported an observed resource state after issuing an allowed command; not runtime correctness proof."}

def make_server(port=PORT):
    token,_,_=_settings()
    if not isinstance(port,int) or (port!=0 and not 1024<=port<=65535):
        raise ValueError("Port must be 1024–65535 (or 0 in tests)")

    class Handler(BaseHTTPRequestHandler):
        server_version="CFXDevKitControlled/1.0"
        def log_message(self,*args):pass
        def answer(self,status,payload):
            payload=json.dumps(payload,separators=(",",":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(payload)))
            self.send_header("Cache-Control","no-store")
            self.end_headers()
            self.wfile.write(payload)
        def authenticated(self):
            return hmac.compare_digest(self.headers.get("X-CFX-Control-Token",""),token)
        def do_GET(self):
            if not self.authenticated():return self.answer(401,{"error":"unauthorized"})
            if self.path=="/health":return self.answer(200,{"ready":True,"loopback":True,"mode":"approved-resource-control"})
            if self.path=="/next":
                try:entry=claim()
                except (ValueError,sqlite3.Error):return self.answer(503,{"error":"unavailable"})
                return self.answer(200,{"request":entry})
            return self.answer(404,{"error":"unknown endpoint"})
        def do_POST(self):
            if not self.authenticated():return self.answer(401,{"error":"unauthorized"})
            if self.path!="/result":return self.answer(404,{"error":"unknown endpoint"})
            rawlen=self.headers.get("Content-Length","")
            if not rawlen.isdecimal() or not 1<=int(rawlen)<=MAX_POST:
                return self.answer(413,{"error":"invalid body length"})
            try:
                body=json.loads(self.rfile.read(int(rawlen)).decode("utf-8"))
                result=record_result(body)
            except (ValueError,UnicodeError,sqlite3.Error):
                return self.answer(400,{"error":"invalid result"})
            return self.answer(200,result)
    return ThreadingHTTPServer((HOST,port),Handler)

def serve(port=PORT):
    server=make_server(port)
    try:
        print(f"CFX DEV-only control broker: http://{HOST}:{server.server_port}, human approval required")
        server.serve_forever(poll_interval=0.2)
    finally:server.server_close()

def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--port",type=int,default=PORT)
    args=parser.parse_args()
    serve(args.port)

if __name__=="__main__":main()
