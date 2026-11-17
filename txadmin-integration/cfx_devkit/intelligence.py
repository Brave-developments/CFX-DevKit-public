"""Project-wide FiveM resource intelligence with bounded, source-aware checks.

This is a lexical/static analyzer, NOT a complete Lua AST parser, security
proof, or FiveM runtime debugger. It masks comments and preserves strings,
can recognize basic literal event references and manifest dependencies.
"""
from __future__ import annotations
import re
import fnmatch
from pathlib import Path
from . import core

def _code_without_comments(source):
    """Remove Lua single/long comments, without matching inside string literals."""
    out=[];i=0;n=len(source);quote=None;long_eq=None
    while i<n:
        c=source[i]
        if quote:
            if c=="\\" and i+1<n:out.extend((c,source[i+1]));i+=2;continue
            out.append(c);i+=1
            if c==quote:quote=None
            continue
        if long_eq is not None:
            close="]"+("="*long_eq)+"]"
            if source.startswith(close,i):out.append(close);i+=len(close);long_eq=None
            else:out.append(c);i+=1
            continue
        if c in "'\"":quote=c;out.append(c);i+=1;continue
        start=re.match(r'\[(=*)\[',source[i:]) if c=='[' else None
        if start:
            long_eq=len(start.group(1));out.append(start.group(0));i+=len(start.group(0));continue
        if source.startswith("--",i):
            lm=re.match(r'--\[(=*)\[',source[i:])
            if lm:
                end="]"+("="*len(lm.group(1)))+"]"
                begin=i+len(lm.group(0));at=source.find(end,begin)
                stop=n if at<0 else at+len(end)
            else:
                at=source.find("\n",i)
                stop=n if at<0 else at
            out.append("".join("\n" if ch=="\n" else " " for ch in source[i:stop]))
            i=stop
            continue
        out.append(c);i+=1
    return "".join(out)

def _mask_literals(source):
    """Prevent detecting fake APIs inside strings; retain line positions."""
    uncommented=_code_without_comments(source)
    out=[];quote=None;escape=False;i=0;n=len(uncommented)
    while i<n:
        c=uncommented[i]
        if quote:
            out.append("\n" if c=="\n" else " ")
            if escape:escape=False
            elif c=="\\":escape=True
            elif c==quote:quote=None
            i+=1;continue
        if c in "'\"":quote=c;out.append(" ");i+=1;continue
        lm=re.match(r'\[(=*)\[',uncommented[i:]) if c=='[' else None
        if lm:
            closing="]"+lm.group(1)+"]"
            start=i+len(lm.group(0));end=uncommented.find(closing,start)
            stop=n if end<0 else end+len(closing)
            out.append("".join("\n" if x=="\n" else " " for x in uncommented[i:stop]))
            i=stop;continue
        out.append(c);i+=1
    return "".join(out)

CALLS={
    "RegisterNetEvent":"receive-network",
    "RegisterServerEvent":"receive-network",
    "AddEventHandler":"receive-local",
    "TriggerServerEvent":"send-server",
    "TriggerClientEvent":"send-client",
    "TriggerEvent":"send-local",
    "RegisterCommand":"command",
    "RegisterNUICallback":"nui-callback",
    "exports":"export",
}
CALL_PATTERN=re.compile(r'\b('+'|'.join(CALLS)+r')\s*\(\s*([\'"])((?:\\.|(?!\2).)*?)\2',re.S)
# Exports and commands can exist inside comments; the call matcher runs on uncommented source.

def _line(source,offset):
    return source.count("\n",0,offset)+1

def _safe_events_in_source(source):
    uncommented=_code_without_comments(source)
    masked=_mask_literals(source)
    # The leading name must be in executable code, not in string literals.
    entries=[]
    for match in CALL_PATTERN.finditer(uncommented):
        start=match.start(1);name=match.group(3)
        if name is None or len(name)>150 or masked[start:start+len(match.group(1))]!=match.group(1):
            continue
        entries.append({"kind":CALLS[match.group(1)],"name":name,"line":_line(source,start)})
    return entries

@core.scan_report
def workspace_index(path="."):
    root=core.safe_path(path)
    if not root.is_dir():raise ValueError("Expected workspace folder")
    grouped={}
    files=0
    for p in core.files_under(root):
        if p.suffix.lower() not in (".lua",".js",".ts",".tsx"):continue
        files+=1
        if p.suffix.lower()!=".lua":continue
        src=core.read(p)
        calls=_safe_events_in_source(src)
        if calls:
            rel=p.relative_to(core.workspace_root()).as_posix()
            for item in calls:
                current=grouped.setdefault(item["name"],{"registered":[],"triggered":[],"commands":[]})
                record={"kind":item["kind"],"file":rel,"line":item["line"]}
                target=("registered" if item["kind"].startswith("receive") else
                        "triggered" if item["kind"].startswith("send") else "commands")
                current[target].append(record)
    if len(grouped)>2000:
        return {"error":"too many event identifiers","max":2000}
    return {"events":dict(sorted(grouped.items())),"event_names":len(grouped),
            "files_scanned":files,
            "note":"Static Lua event index; JS/TS event parsing and dynamic event names are not supported yet."}

@core.scan_report
def event_flow(name,path="."):
    if not isinstance(name,str) or not name or len(name)>160:raise ValueError("Invalid event name")
    index=workspace_index(path)
    node=index.get("events",{}).get(name)
    if not node:return {"name":name,"found":False,"locations":[],"note":"May be declared by another resource or dynamically."}
    return {"name":name,"found":True,**node,
            "note":"Static name matches alone cannot establish cross-resource behavior or valid authorization."}

@core.scan_report
def authority_review(path="."):
    root=core.safe_path(path)
    if not root.is_dir():raise ValueError("Expected workspace folder")
    findings=[]
    for p in core.files_under(root):
        if p.suffix.lower()!=".lua":continue
        rel=p.relative_to(core.workspace_root()).as_posix()
        if core.script_side(p)!="server":
            continue
        src=core.read(p)
        uncommented=_code_without_comments(src)
        masked=_mask_literals(src)
        for match in re.finditer(r'\b(?:RegisterNetEvent|RegisterServerEvent)\s*\(',masked):
            line=_line(src,match.start())
            segment=uncommented[match.start():match.start()+1500]
            check=re.search(r'\b(?:IsPlayerAceAllowed|GetPlayerFromId|GetPlayer\(|Player\(|source|lib\.callback|type\()\b',segment)
            if not check:
                findings.append({"file":rel,"line":line,"severity":"review",
                   "rule":"net-event-no-obvious-validation",
                   "message":"No obvious source or authority check in nearby code; inspect handler and enforce server trust boundaries."})
        # This is intentionally NOT a proof of SQL injection, only a lead.
        for pattern,kind,msg in [
            (r'\b(?:MySQL|oxmysql)\b[\s\S]{0,300}\.\.\s*[a-zA-Z_]',"sql-concatenation","Potential dynamic SQL assembled using concatenation"),
            (r'\bPerformHttpRequest\s*\(', "outbound-http","Server HTTP request found; review URLs, tokens and input handling")]:
            for m in re.finditer(pattern,uncommented):
                if len(findings)>=100:break
                findings.append({"file":rel,"line":_line(src,m.start()),"severity":"review","rule":kind,"message":msg})
        if len(findings)>=100:break
    return {"findings":findings[:100],"truncated":len(findings)>=100,
            "note":"Lexer-assisted static hints, NOT AST/dataflow analysis. Human security review is required."}

@core.scan_report
def manifest_asset_report(path="."):
    root=core.safe_path(path)
    if not root.is_dir():raise ValueError("Expected resource folder")
    result=[];limit=5000
    for p in core.files_under(root):
        if p.name!="fxmanifest.lua":continue
        source=_code_without_comments(core.read(p))
        declared=[]
        for block in re.findall(r'\bfiles\s*\{([^}]+)\}',source,re.S):
            declared.extend(re.findall(r"""['"]([^'"]+)['"]""",block))
        declared.extend(re.findall(r"""(?<!\w)files\s*['"]([^'"]+)['"]""",source))
        declared.extend(re.findall(r"""(?<!\w)data_file\s*['"][^'"]+['"]\s*['"]([^'"]+)['"]""",source))
        declared=list(dict.fromkeys(x.replace("\\","/") for x in declared))
        folder=p.parent
        walk=core.files_under(folder,all_files=True,file_limit=limit)
        actual=[candidate.relative_to(folder).as_posix() for candidate in walk]
        coverage=walk.report();truncated=walk.capped
        stream_files=sorted(x for x in actual if x.lower().endswith((".ytyp",".ymap",".ydr",".ydd",".ytd",".yft",".ybn",".meta")))
        def listed(name):
            return any(not entry.startswith(("@","$")) and fnmatch.fnmatch(name,entry) for entry in declared)
        missing=[]
        for ref in declared:
            if ref.startswith(("@","$")):continue
            if any(c in ref for c in "*?["):
                if not any(fnmatch.fnmatch(filename,ref) for filename in actual):missing.append(ref)
            elif ref not in actual:missing.append(ref)
        unreferenced=[item for item in stream_files if not listed(item)]
        result.append({"resource":folder.relative_to(core.workspace_root()).as_posix(),
                       "stream_files":stream_files[:150],"declared":declared[:150],
                       "missing":missing[:100],
                       "unreferenced_by_files_directive":unreferenced[:100],
                       "unreferenced_total":len(unreferenced),
                       "inventory_coverage":coverage,"missing_is_conclusive":coverage['complete'],
                       "truncated":truncated or len(stream_files)>150 or len(declared)>150 or len(missing)>100 or len(unreferenced)>100})
    return {"resources":result,"note":"Lists streaming assets not mentioned in files/data_file. Stream folder assets can load implicitly; an unreferenced result is not inherently a defect."}
