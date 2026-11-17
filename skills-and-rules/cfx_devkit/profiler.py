"""Offline review of Chrome Trace-format samples exported by profiling tools.

Accepts local trace JSON supplied by a developer. Does not connect to FXServer
or claim any sampling is performed by this module. Never executes trace data.
"""
from __future__ import annotations
import json
import math
from pathlib import Path
from . import core

MAX_TRACE_BYTES=40_000_000
MAX_EVENTS=300_000

def summarize_trace(path,limit=20):
    if not isinstance(limit,int) or isinstance(limit,bool) or not 1<=limit<=50:
        raise ValueError("Limit must be 1–50")
    target=core.safe_path(path)
    if not target.is_file() or target.suffix.lower() not in (".json",".trace"):
        raise ValueError("Provide an existing .json or .trace file inside the workspace")
    if target.stat().st_size>MAX_TRACE_BYTES:
        raise ValueError("Trace exceeds 40 MB analysis limit")
    raw=json.loads(target.read_text(encoding="utf-8"))
    events=raw.get("traceEvents",[]) if isinstance(raw,dict) else raw
    if not isinstance(events,list) or len(events)>MAX_EVENTS:
        raise ValueError("Expected Chrome Trace JSON list with at most 300000 events")
    names={}
    seen=0
    complete=0
    for item in events:
        if not isinstance(item,dict):continue
        seen+=1
        if item.get("ph")!="X":continue
        duration=item.get("dur")
        if not isinstance(duration,(int,float)) or isinstance(duration,bool) or not math.isfinite(duration) or duration<0:
            continue
        label=item.get("name")
        if not isinstance(label,str) or not label:continue
        label=label[:140]
        key=(label,str(item.get("cat",""))[:80])
        obj=names.setdefault(key,{"name":label,"category":key[1],"samples":0,"total_us":0.0,"max_us":0.0})
        obj["samples"]+=1
        obj["total_us"]+=duration
        obj["max_us"]=max(obj["max_us"],duration)
        complete+=1
    order=sorted(names.values(),key=lambda x:-x["total_us"])
    for item in order[:limit]:
        item["total_us"]=round(item["total_us"],2)
        item["max_us"]=round(item["max_us"],2)
    return {"trace":target.relative_to(core.workspace_root()).as_posix(),
            "events_read":seen,"duration_events":complete,"total_unique_labels":len(names),
            "top":order[:limit],
            "unit":"microseconds",
            "note":"Chrome Trace X-duration summaries. Overlapping threads/categories can double-count time; do not interpret sums as total CPU usage or benchmark evidence alone."}
