"""Independent, offline-first CFX project analysis helpers (standard library only)."""
from __future__ import annotations
import fnmatch
import os
import re
import stat
from pathlib import Path
from contextvars import ContextVar
from functools import wraps

IGNORE_DIRS = {'.git', '.cfx-devkit', 'node_modules', '.next', 'dist', 'build', 'coverage', '.venv', '__pycache__', 'vendor'}
SCAN_EXT = {'.lua', '.js', '.jsx', '.ts', '.tsx', '.html', '.json', '.cfg'}
MAX_FILES = 25000
MAX_BYTES = 600_000
_SCANS = ContextVar('cfx_file_scans', default=None)


def scan_report(function):
    """Attach coverage from every walker used by a public analysis, including nested calls."""
    @wraps(function)
    def measured(*args, **kwargs):
        parent = _SCANS.get()
        scans = []
        token = _SCANS.set(scans)
        try:
            result = function(*args, **kwargs)
        finally:
            _SCANS.reset(token)
            if parent is not None:
                parent.extend(scans)
        if isinstance(result, dict):
            reports = [scan.report() for scan in scans]
            capped = any(r['file_cap_reached'] for r in reports)
            incomplete = any(not r['complete'] for r in reports)
            limited = bool(result.get('result_truncated', result.get('truncated', False)) or
                           result.get('resources_truncated') or result.get('warnings_truncated') or
                           result.get('calls_truncated') or any(
                               row.get('truncated') for value in result.values() if isinstance(value, list)
                               for row in value if isinstance(row, dict)))
            result.update(scan_truncated=capped, scan_complete=not incomplete,
                          scan_incomplete=incomplete, result_truncated=limited,
                          truncated=incomplete or limited,
                          scan_coverage={'walks': reports, 'eligible_total_known': all(r['eligible_files_total'] is not None for r in reports)})
            if incomplete:
                result['coverage_warning'] = 'Incomplete source coverage; missing findings do not establish absence of defects.'
        return result
    return measured


class FileScan:
    """Single-use iterator with observable coverage; a cap is detected by lookahead."""
    def __init__(self, location, *, all_files=False, file_limit=None):
        self.root = workspace_root()
        self.location = Path(location).resolve()
        if not self.location.is_relative_to(self.root) or not self.location.is_dir():
            raise ValueError('Project directory must be inside the configured workspace')
        try:
            self.limit = int(os.environ.get('CFX_MAX_SCAN_FILES', MAX_FILES))
        except (ValueError, TypeError):
            raise ValueError('CFX_MAX_SCAN_FILES must be an integer from 1 to 250000') from None
        if not 1 <= self.limit <= 250000:
            raise ValueError('CFX_MAX_SCAN_FILES must be 1..250000')
        if file_limit is not None:
            self.limit=min(self.limit,file_limit)
        self.all_files=all_files
        self.links=0
        self.yielded = self.seen = self.oversize = self.unreadable = 0
        self.capped = self.finished = False
        self._iterator = self._walk()
        if _SCANS.get() is not None:
            _SCANS.get().append(self)

    def __iter__(self):
        return self

    def __next__(self):
        return next(self._iterator)

    def _walk(self):
        def denied(error):
            self.unreadable += 1
        for base, dirs, files in os.walk(self.location, followlinks=False, onerror=denied):
            kept=[]
            for d in sorted(dirs):
                if d in IGNORE_DIRS:continue
                child=Path(base)/d
                try:
                    if linked_path(child) or not child.resolve().is_relative_to(self.location):
                        self.links+=1;continue
                    kept.append(d)
                except OSError:self.unreadable+=1
            dirs[:]=kept
            for filename in sorted(files):
                p = Path(base)/filename
                if not self.all_files and p.suffix.lower() not in SCAN_EXT:
                    continue
                try:
                    if linked_path(p) or not p.resolve().is_relative_to(self.location):
                        self.links+=1;continue
                    info=p.stat()
                    if not stat.S_ISREG(info.st_mode):
                        self.unreadable+=1;continue
                    if not self.all_files and info.st_size > MAX_BYTES:
                        self.oversize += 1
                        continue
                except OSError:
                    self.unreadable += 1
                    continue
                self.seen += 1
                if self.yielded >= self.limit:
                    self.capped = True
                    return
                self.yielded += 1
                yield p
        self.finished = True

    def report(self):
        complete = self.finished and not self.capped and not self.oversize and not self.unreadable and not self.links
        return {'path': self.location.relative_to(self.root).as_posix(), 'file_limit': self.limit,
                'files_yielded': self.yielded, 'eligible_files_seen': self.seen,
                'eligible_files_total': self.seen if self.finished and not self.unreadable else None,
                'file_cap_reached': self.capped, 'enumeration_finished': self.finished,
                'oversized_files_skipped': self.oversize, 'unreadable_locations': self.unreadable,
                'linked_paths_skipped':self.links,'inventory_only':self.all_files,
                'complete': complete}
FRAMEWORKS = {
    'qbox': ('qbx_core', 'QBX', 'qbox'),
    'qbcore': ('qb-core', 'QBCore', 'qbcore'),
    'esx': ('es_extended', 'ESX', 'esx:getSharedObject'),
    'ox_core': ('ox_core', 'Ox.GetPlayer', 'ox:playerLoaded'),
}
DOCS = [
    {'topic':'resource manifest', 'url':'https://docs.fivem.net/docs/scripting-reference/resource-manifest/resource-manifest/'},
    {'topic':'events and security', 'url':'https://docs.fivem.net/docs/scripting-manual/working-with-events/'},
    {'topic':'secure events', 'url':'https://docs.fivem.net/docs/developers/server-security/'},
    {'topic':'NUI callbacks', 'url':'https://docs.fivem.net/docs/scripting-manual/nui-development/nui-callbacks/'},
    {'topic':'NUI messages', 'url':'https://docs.fivem.net/docs/scripting-manual/nui-development/full-screen-nui/'},
    {'topic':'natives', 'url':'https://docs.fivem.net/natives/'},
    {'topic':'scripting runtime', 'url':'https://docs.fivem.net/docs/scripting-manual/runtimes/lua/'},
]

def workspace_root() -> Path:
    root = Path(os.environ.get('CFX_WORKSPACE_ROOT', os.getcwd())).expanduser().resolve()
    if not root.is_dir():
        raise ValueError('Configured CFX_WORKSPACE_ROOT is not a directory')
    return root

def safe_path(relative: str = '.') -> Path:
    root = workspace_root()
    if not isinstance(relative, str) or not relative:
        raise ValueError('path must be a nonempty string')
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError('Requested path is outside the configured workspace')
    return candidate

def linked_path(path):
    """Detect Windows reparse points too, including junctions on Python 3.10."""
    return path.is_symlink() or bool(getattr(path.lstat(),'st_file_attributes',0) &
                                    getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0x400))

def files_under(location: Path, *, all_files=False, file_limit=None):
    return FileScan(location,all_files=all_files,file_limit=file_limit)

def read(p: Path) -> str:
    p=p.resolve()
    if not p.is_relative_to(workspace_root()):
        raise ValueError('Source file is outside the configured workspace')
    if not p.is_file():raise ValueError('Expected a regular source file')
    with p.open('rb') as stream:raw=stream.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:raise ValueError('Source file exceeds the configured byte limit')
    return raw.decode('utf-8',errors='replace')

def script_side(p: Path) -> str:
    """Best-effort file side; unknown is NOT assumed to be server-side."""
    p=p.resolve()  # Windows temp paths may use short (8.3) aliases
    name=p.name.casefold()
    parts={part.casefold() for part in p.parts}
    if name in ('client.lua','client.js','client.ts') or name.startswith('cl_') or 'client' in parts or 'html' in parts or 'web' in parts:
        return 'client'
    if name in ('server.lua','server.js','server.ts') or name.startswith('sv_') or 'server' in parts:
        return 'server'
    if name.startswith('shared') or 'shared' in parts:
        return 'shared'
    # Look for an explicit fxmanifest in this resource or ancestors.
    root=workspace_root()
    for folder in (p.parent,*p.parent.parents):
        if not folder.is_relative_to(root):break
        manifest=folder/'fxmanifest.lua'
        if not manifest.is_file():continue
        source=strip_lua_comments(read(manifest))
        relative=p.relative_to(folder).as_posix()
        for side in ('client','server','shared'):
            pattern=r'\b'+side+r'_scripts?\s*(?:\{([^}]+)\}|[\\\'"]([^\\\'"]+)[\\\'"])'
            for match in re.finditer(pattern,source,re.S):
                raw=match.group(1) or match.group(2) or ''
                targets=re.findall(r'[\\\'"]([^\\\'"]+)[\\\'"]',raw) if match.group(1) is not None else [raw]
                if any(fnmatch.fnmatch(relative,item) for item in targets):
                    return side
        break
    return 'unknown'

@scan_report
def list_resources(path: str = '.') -> dict:
    loc = safe_path(path)
    if not loc.is_dir(): raise ValueError('Project directory does not exist')
    walk = files_under(loc)
    source = list(walk)
    manifests = [p for p in source if p.name == 'fxmanifest.lua']
    frameworks = detect_framework(path)
    resource_truncated=len(manifests)>100
    return {'workspace': str(workspace_root()), 'path': loc.relative_to(workspace_root()).as_posix(),
            'files_scanned':len(source), 'resource_count':len(manifests),
            'resources_truncated':resource_truncated, 'max_resource_results':100,
            'resources':[p.parent.relative_to(workspace_root()).as_posix() for p in manifests[:100]],
            'frameworks':frameworks['detected'],
            'framework_sampling':frameworks.get('sampling'),
            'warnings':(['Scan stopped at file cap of '+str(walk.limit)] if walk.capped else [])+
                (['Resource results limited to 100 of '+str(len(manifests))] if resource_truncated else [])}

@scan_report
def detect_framework(path: str = '.') -> dict:
    loc = safe_path(path)
    if not loc.is_dir(): raise ValueError('Project directory does not exist')
    samples = []
    matching = 0
    for p in files_under(loc):
        if p.name.lower() in {'fxmanifest.lua','server.cfg','config.lua','shared.lua'} or p.name.lower().startswith(('server.', 'main.')):
            matching += 1
            if len(samples)<60:
                samples.append(read(p)[:100_000].lower())
    joined = '\n'.join(samples)
    found = []
    for name, tokens in FRAMEWORKS.items():
        hits = [token for token in tokens if token.lower() in joined]
        if hits:
            found.append({'name':name,'signals':hits,'confidence':'possible' if len(hits)==1 else 'strong'})
    return {'detected':found or [{'name':'standalone-or-undetected','confidence':'unknown','signals':[]}],
            'sampling':{'files_read':len(samples),'matching_files_seen':matching,'sample_limit':60,'sample_limited':matching>60},
            'note':'Heuristic detection; mixed or dynamically loaded frameworks require manual verification.'}

def strip_lua_comments(s: str) -> str:
    from .intelligence import _code_without_comments
    return _code_without_comments(s)

def _manifest_paths(content: str) -> list[str]:
    clean = strip_lua_comments(content)
    names = r'(?:client_scripts?|server_scripts?|shared_scripts?|files|ui_page)'
    items = []
    for mat in re.finditer(r'\b'+names+r'\s*\{([^}]+)\}', clean, flags=re.S):
        items += re.findall(r'[\'\"]([^\'\"]+)[\'\"]', mat.group(1))
    for mat in re.finditer(r'\b'+names+r'\s*\(?\s*[\'\"]([^\'\"]+)[\'\"]', clean):
        items.append(mat.group(1))
    return list(dict.fromkeys(items))

@scan_report
def validate_manifest(path: str) -> dict:
    p = safe_path(path)
    if p.is_dir(): p = p / 'fxmanifest.lua'
    p=safe_path(p.relative_to(workspace_root()).as_posix())
    if p.name != 'fxmanifest.lua' or not p.is_file(): raise ValueError('Expected an existing fxmanifest.lua')
    s = strip_lua_comments(read(p))
    findings = []
    if not re.search(r'\bfx_version\s*[\'\"]cerulean[\'\"]',s):
        findings.append({'severity':'warning','message':'Missing current fx_version cerulean; verify target support.'})
    # Only game directives determine FiveM support; comments and descriptions do not.
    game_values = []
    for declaration in re.finditer(r'\bgames?\s*(?:\{([^}]*?)\}|([\x27\x22])([^\x27\x22]*)\2)', s, re.S):
        body = declaration.group(1) if declaration.group(1) is not None else declaration.group(3)
        game_values.extend(re.findall(r'[\x27\x22]([^\x27\x22]+)[\x27\x22]', body) if declaration.group(1) is not None else [body])
    allowed = {'gta5', 'common'}
    if not any(game.lower() in allowed for game in game_values):
        if any(game.lower() == 'rdr3' for game in game_values):
            findings.append({'severity':'error','message':'RedM/RDR3 game declaration is unsupported by this FiveM-only toolkit.'})
        else:
            findings.append({'severity':'error','message':'No FiveM-compatible game declaration (gta5/common).'})
    elif any(game.lower() == 'rdr3' for game in game_values):
        findings.append({'severity':'warning','message':'Mixed FiveM/RedM games declaration; FiveM is supported, but RedM is outside this toolkit.'})
    declared = _manifest_paths(s)
    manifest_files = None
    for rel in declared:
        if rel.startswith(('@','$','http:','https:')) or '$' in rel: continue
        if any(c in rel for c in '*?['):
            if manifest_files is None:
                manifest_files = list(files_under(p.parent,all_files=True))
            if not any(fnmatch.fnmatch(str(f.relative_to(p.parent)).replace('\\','/'),rel) for f in manifest_files):
                findings.append({'severity':'warning','message':f'File glob matches nothing: {rel}'})
        else:
            target=(p.parent/rel).resolve()
            if not target.is_relative_to(workspace_root()):
                findings.append({'severity':'error','message':'Referenced file escapes the configured workspace.'})
            elif not target.is_file():
                findings.append({'severity':'warning','message':f'Referenced file not found: {rel}'})
    from . import dependencies
    meta=dependencies.metadata(s)
    dependency_check=None
    if meta['dependencies'] or meta['unknown_metadata']:
        graph=dependencies.analyze('.')
        resource=p.parent.name
        dependency_check={'scope':'workspace','analysis_complete':graph['analysis_complete'] and graph['scan_complete'],
                          'result_truncated':graph['result_truncated'],
                          'unresolved':[r for r in graph['unresolved_in_scanned_tree'] if r['resource']==resource],
                          'ambiguous':[r for r in graph['ambiguous_dependencies'] if r['resource']==resource]}
        findings.extend(r for r in graph['findings'] if r['path']==p.parent.relative_to(workspace_root()).as_posix())
        if not dependency_check['analysis_complete'] or graph['result_truncated']:
            findings.append({'severity':'review','rule':'dependency-resolution-incomplete',
                             'message':'Dependency resolution is incomplete; review missing/ambiguous resources and workspace coverage.'})
    return {'manifest':p.relative_to(workspace_root()).as_posix(), 'declared_files':declared,
            'dependency_check':dependency_check,'metadata':meta,
            'result_truncated':bool(dependency_check and dependency_check['result_truncated']),
            'findings':findings, 'status':'review' if findings else 'no-obvious-issues',
            'note':'Static checks only; Lua manifest evaluation and dynamic directives are not executed.'}

@scan_report
def security_audit(path: str = '.') -> dict:
    loc = safe_path(path)
    if not loc.is_dir(): raise ValueError('Project directory does not exist')
    findings=[]; scanned=0
    for p in files_under(loc):
        if p.suffix.lower() not in {'.lua','.js','.ts','.jsx','.tsx','.html','.cfg'}: continue
        scanned+=1
        text=read(p)
        if p.suffix.lower()=='.lua':
            from .intelligence import _code_without_comments, _mask_literals
            text=_code_without_comments(text)
            executable=_mask_literals(text).splitlines()
        else:
            executable=text.splitlines()
        lines=text.splitlines()
        rel=str(p.relative_to(workspace_root()))
        low=rel.lower().replace('\\','/')
        side=script_side(p)
        is_client = side=='client'
        for n,line in enumerate(lines,1):
            active=executable[n-1] if n-1<len(executable) else ''
            stripped=line.strip()
            if stripped.startswith(('--','//','*')): continue
            def add(sev,code,detail):
                if len(findings)<150: findings.append({'severity':sev,'rule':code,'path':rel,'line':n,'message':detail})
            if re.search(r'discord(?:app)?\.com/api/webhooks/\d+/',line, re.I) and is_client:
                add('high','client-webhook','Potential Discord webhook URL in client-facing files. Move secrets to server configuration.')
            if re.search(r'\b(?:MySQL\.(?:query|scalar|update|insert|execute)|exports\.oxmysql)\b', active) and re.search(r'(\.\.|\+\s*[\w]+\s*\+)',line):
                add('high','sql-concatenation','Potential SQL string concatenation. Review for parameterized queries.')
            if re.search(r'\bRegisterNetEvent\s*\(',active) and side=='server':
                window='\n'.join(executable[n:n+17])
                guards=('type(', 'IsPlayerAceAllowed(', 'GetPlayer(', 'source', 'lib.callback', 'Validate', 'validate', 'if ')
                if not any(x in window for x in guards):
                    add('review','server-event-review','Server net event with no obvious argument or authority checks nearby; review trust boundaries.')
            if re.search(r'\bwhile\s+true\s+do\b',active) and any(re.search(r'\bWait\s*\(\s*0\s*\)',x) for x in executable[n:n+9]):
                add('info','tight-loop','Per-frame loop detected. Confirm it only runs when needed.')
    return {'files_scanned':scanned,'findings':findings,'truncated':len(findings)>=150,
            'note':'Heuristic findings are not proof of vulnerabilities. Inspect control flow and test on an isolated server.'}

@scan_report
def nui_audit(path: str = '.') -> dict:
    loc=safe_path(path)
    if not loc.is_dir(): raise ValueError('Project directory does not exist')
    signals=dict.fromkeys(('send_nui_message','register_nui_callback','set_nui_focus',
                          'window_message_listener','browser_fetch','nui_resource_name'),False)
    for p in files_under(loc):
        suffix=p.suffix.lower()
        if suffix not in {'.lua','.js','.ts','.tsx','.jsx','.html'}:continue
        source=read(p)
        if suffix=='.lua':
            signals['send_nui_message'] |= 'SendNUIMessage' in source
            signals['register_nui_callback'] |= 'RegisterNUICallback' in source
            signals['set_nui_focus'] |= 'SetNuiFocus' in source
        else:
            signals['window_message_listener'] |= bool(re.search(r'addEventListener\s*\(\s*[\'\"]message',source))
            signals['browser_fetch'] |= bool(re.search(r'\bfetch\s*\(',source))
            signals['nui_resource_name'] |= 'GetParentResourceName' in source
    notices=[]
    if signals['send_nui_message'] and not signals['window_message_listener']:
        notices.append('Lua sends NUI messages, but no browser window message listener was found in scanned source.')
    if signals['register_nui_callback'] and not signals['browser_fetch']:
        notices.append('Lua registers NUI callbacks, but browser fetch() was not found in scanned source.')
    if signals['browser_fetch'] and not signals['nui_resource_name']:
        notices.append('Browser fetch() exists; verify dynamic NUI resource name, callback endpoint, and response.')
    return {'signals':signals,'review_notes':notices,'note':'Scans eligible source files; inspect coverage for exclusions. Signals are lexical hints, not execution verification.'}

def _valid_resource_name(name: str):
    if not isinstance(name,str) or not re.fullmatch(r'[a-z][a-z0-9_-]{1,48}',name):
        raise ValueError('Resource name must start with a letter and contain 2–49 lowercase letters, numbers, _ or -')

def resource_preview(name: str, framework: str='standalone', with_nui: bool=False) -> dict:
    _valid_resource_name(name)
    deps={'standalone':None,'qbox':'qbx_core','qbcore':'qb-core','esx':'es_extended'}
    if framework not in deps: raise ValueError('Supported frameworks: standalone, qbox, qbcore, esx')
    if not isinstance(with_nui,bool): raise ValueError('with_nui must be boolean')
    manifest="fx_version 'cerulean'\ngame 'gta5'\n\nauthor 'CFX DevKit'\ndescription 'Secure starter resource'\nversion '0.1.0'\n"
    if deps[framework]: manifest+=f"\ndependency '{deps[framework]}'\n"
    manifest+="\nshared_script 'config.lua'\nclient_script 'client/main.lua'\nserver_script 'server/main.lua'\n"
    files={'fxmanifest.lua':manifest, 'config.lua':"Config = { Debug = false }\n",
    'client/main.lua':"-- Client-only presentation and controls. Never grant items or money here.\nRegisterCommand('cfxhello', function()\n    print('CFX DevKit client ready')\nend, false)\n",
    'server/main.lua':"-- Validate every client event on the server before changing game state.\nAddEventHandler('onResourceStart', function(resource)\n    if resource ~= GetCurrentResourceName() then return end\n    print(('[%s] started'):format(resource))\nend)\n"}
    if with_nui:
        manifest+="\nui_page 'html/index.html'\nfiles { 'html/index.html', 'html/app.js' }\n"
        files['fxmanifest.lua']=manifest
        files['html/index.html']='<!doctype html><html><head><meta charset="utf-8"></head><body><p>CFX DevKit NUI starter</p><script src="app.js"></script></body></html>\n'
        files['html/app.js']="window.addEventListener('message', (event) => { console.log('NUI message', event.data); });\n"
    return {'resource':name,'framework':framework,'files':files,'note':'Preview only. Inspect all generated code before installing.'}

def scaffold_resource(name: str, framework: str='standalone', with_nui: bool=False, destination: str='.') -> dict:
    if os.environ.get('CFX_ENABLE_WRITES')!='1':
        raise ValueError('Writes are disabled. Set CFX_ENABLE_WRITES=1 and obtain explicit user approval before use.')
    preview=resource_preview(name,framework,with_nui)
    parent=safe_path(destination)
    if not parent.is_dir(): raise ValueError('Destination directory does not exist')
    target=parent/name
    if target.exists() or target.is_symlink(): raise ValueError('Destination resource already exists; no files overwritten')
    target.mkdir()
    try:
        for rel, content in preview['files'].items():
            p=target/rel;p.parent.mkdir(parents=True,exist_ok=True)
            with p.open('x',encoding='utf-8') as out: out.write(content)
    except Exception:
        raise
    return {'created':str(target.relative_to(workspace_root())), 'files':list(preview['files']), 'note':'Review generated files before server use.'}

def reference_links(topic: str='') -> dict:
    q=topic.casefold().strip()
    return {'sources':[v for v in DOCS if not q or q in v['topic'].lower() or q in v['url'].lower()],
            'note':'Curated official documentation links; no live scraping or claims of current native availability.'}
