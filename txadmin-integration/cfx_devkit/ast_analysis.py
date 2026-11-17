"""Opt-in grammar-based Lua analysis using tree-sitter-lua.

Unlike basic lexical scanning this walks actual parsed function-call nodes, so
comments, quoted snippets and unrelated code cannot impersonate a call.
Handler-guard rules are intentionally *heuristic*, NOT a proof of authority.
Install the optional extras: pip install -e '.[analysis]'
"""
from __future__ import annotations
from collections import defaultdict
from importlib.metadata import PackageNotFoundError, version
import re
from . import core

NETWORK_RECEIVERS={"RegisterNetEvent","RegisterServerEvent"}
CALL_KIND={
    "RegisterNetEvent":"register_network","RegisterServerEvent":"register_network",
    "AddEventHandler":"register_handler","TriggerServerEvent":"send_to_server",
    "TriggerClientEvent":"send_to_client","TriggerEvent":"emit_local",
    "RegisterNUICallback":"register_nui","RegisterCommand":"register_command",
    "MySQL.query.await":"sql_call","MySQL.update.await":"sql_call",
    "MySQL.insert.await":"sql_call","MySQL.scalar.await":"sql_call"
}
# Restrict paths and source size using core.workspace_root and core.files_under.
MAX_RESULTS=300
NAME= re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_.:]*)\s*\(")
STR_ARG=re.compile(r"^\s*[A-Za-z_][A-Za-z0-9_.:]*\s*\(\s*(['\"])([^'\"\r\n]{1,180})\1")

SUPPORTED_TREE_SITTER="0.25.2"

def _check_version():
    try: installed=version("tree-sitter")
    except PackageNotFoundError:raise ValueError("tree-sitter is not installed")
    if installed!=SUPPORTED_TREE_SITTER:
        raise ValueError("Incompatible tree-sitter version "+installed+"; install tree-sitter==0.25.2 before AST use")
    return installed

def _cfx_extensions(code):
    # Standard Lua 5.x grammar does not accept some CfxLua-only operators.
    # We cannot give a trustworthy syntax verdict if these are present.
    from .intelligence import _mask_literals
    masked=_mask_literals(code)
    return bool(re.search(r'(?:\+=|-=|\*=|/=|\?\.|\?\[|\?\?|&&|\|\||(?<![\w])![^=]|(?<!\w)\x60)',masked))

def available():
    try:
        installed=_check_version()
        from tree_sitter import Language, Parser
        import tree_sitter_lua
        parser=Parser(Language(tree_sitter_lua.language()))
        return {"available":True, "tree_sitter_version":installed, "backend":"tree-sitter-lua","grammar":"Lua 5.x/LuaJIT","note":"AST structure only, not control-flow/dataflow correctness"}
    except (ImportError,TypeError,ValueError) as exc:
        return {"available":False,"backend":"tree-sitter-lua","error":type(exc).__name__,
            "hint":"Install the optional parser: python -m pip install -e '.[analysis]'"}

def _parser():
    _check_version()
    try:
        from tree_sitter import Language, Parser
        import tree_sitter_lua
    except ImportError as exc:
        raise ValueError("Optional AST parser unavailable: pip install -e '.[analysis]'") from exc
    return Parser(Language(tree_sitter_lua.language()))

def parse_lua_source(code):
    if not isinstance(code,str):raise ValueError("Expected Lua source text")
    if len(code.encode("utf-8"))>core.MAX_BYTES:raise ValueError("Lua source exceeds analysis file limit")
    cfx_extension=_cfx_extensions(code)
    payload=code.encode("utf-8")
    tree=_parser().parse(payload)
    calls=[];errors=[];calls_total=0
    stack=[tree.root_node]
    while stack:
        node=stack.pop()
        if node.type=="ERROR" or node.is_missing:
            if len(errors)<30:errors.append({"line":node.start_point.row+1,"kind":node.type})
        if node.type=="function_call":
            snippet=payload[node.start_byte:node.end_byte].decode("utf-8",errors="replace")
            m=NAME.match(snippet)
            if m:
                function=m.group(1)
                if function in CALL_KIND:
                    calls_total+=1
                if function in CALL_KIND and len(calls)<MAX_RESULTS:
                    literal=STR_ARG.match(snippet)
                    calls.append({"function":function,"kind":CALL_KIND[function],
                                  "name":literal.group(2) if literal else None,
                                  "line":node.start_point.row+1,
                                  "byte_start":node.start_byte,
                                  "byte_end":node.end_byte})
        stack.extend(reversed(node.children))
    if cfx_extension:
        return {"calls":calls,'calls_total':calls_total,'calls_truncated':calls_total>len(calls),"syntax_errors":[],"has_syntax_errors":False,
                "syntax_validated":False,"unsupported_cfxlua_syntax":True,
                "analysis":"CfxLua-specific syntax detected; Lua 5.x grammar cannot give a reliable syntax verdict. Parsed call locations are best effort."}
    return {"calls":calls,'calls_total':calls_total,'calls_truncated':calls_total>len(calls),"syntax_errors":errors,"has_syntax_errors":tree.root_node.has_error,
            "syntax_validated":True,"unsupported_cfxlua_syntax":False,
            "analysis":"AST function-call and literal extraction; not dataflow analysis"}

@core.scan_report
def analyze_project(path="."):
    loc=core.safe_path(path)
    if not loc.is_dir():raise ValueError("Expected FiveM project directory")
    report=[];resources=set();warnings=[];scanned=0;warnings_total=0;calls_total=0;unsupported_count=0
    for file in core.files_under(loc):
        if file.suffix.lower()!=".lua":continue
        scanned+=1
        source=core.read(file)
        parsed=parse_lua_source(source)
        calls_total+=parsed['calls_total']
        rel=file.relative_to(core.workspace_root()).as_posix()
        if not parsed.get("syntax_validated",True):
            unsupported_count+=1
            warnings_total+=1
            if len(warnings)<100:warnings.append({"file":rel,"kind":"syntax-unverified-cfxlua",
                "note":"CfxLua extension unsupported by grammar; not a syntax error"})
        if parsed["has_syntax_errors"]:
            warnings_total+=1
            if len(warnings)<100:warnings.append({"file":rel,"kind":"lua-parse-errors",
                "examples":parsed["syntax_errors"][:8]})
        for call in parsed["calls"]:
            if len(report)<MAX_RESULTS:
                report.append({"file":rel,"line":call["line"],
                               "function":call["function"],"kind":call["kind"],
                               "literal":call["name"]})
    return {"backend":"tree-sitter-lua","files_scanned":scanned,
        "calls":report,"warnings":warnings,"warning_count":warnings_total,
        "syntax_unverified_files":unsupported_count,
        "calls_total":calls_total,"truncated":calls_total>len(report),
        "warnings_truncated":warnings_total>len(warnings),
        "note":"Structural AST locations only, not a security verdict. Dynamic arguments may have literal=null."}

@core.scan_report
def audit_network_handlers(path="."):
    result=analyze_project(path)
    findings=[]
    for call in result["calls"]:
        if (call["kind"]=="register_network" and
            ("server" in call["file"].casefold() or "/sv_" in call["file"].casefold())):
            findings.append({"file":call["file"],"line":call["line"],
                "event":call["literal"],"severity":"review",
                "message":"AST-confirmed server-side network event registration; check handler source, input types, server authority, authorization and rate controls."})
    return {"backend":"tree-sitter-lua","registrations":findings,
        "calls_truncated":result.get("result_truncated",False),
        "warnings_truncated":result.get("warnings_truncated",False),
        "syntax_unverified_files":result.get("syntax_unverified_files",0),
        "notes":"No automatic claim that an event is vulnerable or safe. AST classification alone does not trace data flow."}
