"""Safe, bounded, read-only FiveM project inspection tools."""
from __future__ import annotations
import re
from pathlib import Path
from . import core
from .intelligence import _code_without_comments, _mask_literals

MAX_MATCHES=100

def _sources(path='.'):
    base=core.safe_path(path)
    if not base.is_dir():raise ValueError('Project directory does not exist')
    return [(p,p.relative_to(core.workspace_root()).as_posix()) for p in core.files_under(base)
            if p.suffix.lower() in {'.lua','.js','.ts','.jsx','.tsx','.cfg'}]

def _hits(path, patterns):
    findings=[];total=0
    for p,relative in _sources(path):
        if p.suffix.lower()=='.cfg' and p.name!='server.cfg':continue
        source=core.read(p)
        if p.suffix.lower()=='.lua':
            source=_code_without_comments(source)
            masked=_mask_literals(source)
        else:
            masked=source
        raw_lines=source.splitlines()
        masked_lines=masked.splitlines()
        for i,line in enumerate(raw_lines,1):
            if line.lstrip().startswith(('--','//','#')):continue
            mask=masked_lines[i-1] if i<=len(masked_lines) else ''
            for kind,pattern in patterns:
                if kind=='js-export' and p.suffix.lower() not in ('.js','.jsx','.ts','.tsx'):
                    continue
                for match in re.finditer(pattern,line):
                    # Ensure the matched API name is executable, not a quote/long-string.
                    first=re.match(r'[A-Za-z_][A-Za-z_0-9]*',match.group(0))
                    if first and mask[match.start():match.start()+len(first.group())]!=first.group():
                        continue
                    name=match.group(1) if match.lastindex else match.group(0)
                    total+=1
                    if len(findings)<MAX_MATCHES:
                        findings.append({'kind':kind,'name':name[:180],'path':relative,'line':i})
    return {'findings':findings,'total_matches':total,'truncated':total>len(findings),
            'note':'Source-aware lexical index. Dynamic events, non-literal names and some JavaScript constructs may be missed.'}

@core.scan_report
def project_events(path='.'):
    patterns=[
        ('register-net-event',r'\bRegisterNetEvent\s*\(\s*[\x27"]([^\x27"]+)'),
        ('register-local-event',r'\bAddEventHandler\s*\(\s*[\x27"]([^\x27"]+)'),
        ('client-to-server',r'\bTriggerServerEvent\s*\(\s*[\x27"]([^\x27"]+)'),
        ('server-to-client',r'\bTriggerClientEvent\s*\(\s*[\x27"]([^\x27"]+)'),
        ('local-trigger',r'\bTriggerEvent\s*\(\s*[\x27"]([^\x27"]+)'),
        ('js-event',r'\b(?:onNet|emitNet|on|emit)\s*\(\s*[\x27"]([^\x27"]+)'),
    ]
    result=_hits(path,patterns)
    inbound={r['name'] for r in result['findings'] if r['kind'] in {'register-net-event','register-local-event','js-event'}}
    outbound={r['name'] for r in result['findings'] if r['kind'] in {'client-to-server','server-to-client','local-trigger'}}
    result['unmatched_static_triggers']=sorted(outbound-inbound)[:40]
    result['note']+=' Unmatched triggers can be registered in other resources or at runtime, and are not necessarily bugs.'
    return result

@core.scan_report
def find_exports(path='.'):
    return _hits(path,[('lua-export',r'\bexports\s*\(\s*[\x27"]([\w:-]+)'),
                       ('manifest-export',r'\b(?:server_export|export)\s*[\x27"]([\w:-]+)'),
                       # JS export declarations assign a value; calling exports["resource"] is NOT declaring an export.
                       ('js-export',r'\bexports\s*\[\s*[\x27"]([\w:-]+)[\x27"]\s*\]\s*=')])

@core.scan_report
def find_commands(path='.'):
    return _hits(path,[('command',r'\bRegisterCommand\s*\(\s*[\x27"]([\w:-]+)'),
                       ('key-mapping',r'\bRegisterKeyMapping\s*\(\s*[\x27"]([\w:+-]+)')])

@core.scan_report
def dependency_graph(path='.'):
    from . import dependencies
    return dependencies.analyze(path)

def check_server_cfg(path='server.cfg'):
    p=core.safe_path(path)
    if p.is_dir():p=p/'server.cfg'
    p=core.safe_path(p.relative_to(core.workspace_root()).as_posix())
    if not p.is_file() or p.name!='server.cfg':raise ValueError('Provide an existing server.cfg path')
    warnings=[];ensured=[];bound=set()
    for n,line in enumerate(core.read(p).splitlines(),1):
        stripped=line.strip()
        if not stripped or stripped.startswith('#'):continue
        parts=stripped.split(None,1)
        command=parts[0].lower()
        argument=parts[1].strip() if len(parts)>1 else ''
        if command in ('ensure','start'):
            name=argument.split('#')[0].strip()
            if name:ensured.append(name)
            if name in bound:warnings.append({'line':n,'severity':'info','message':'Resource started more than once: '+name})
            bound.add(name)
        if command in ('endpoint_add_tcp','endpoint_add_udp') and '0.0.0.0' in argument:
            warnings.append({'line':n,'severity':'info','message':'Server binds to all IPv4 interfaces; verify firewall exposure.'})
        if command in ('set','setr','sets','seta') and argument:
            first=argument.split(None,1)[0].lower()
        elif command in ('sv_licensekey','rcon_password','steam_webapikey','sv_tebexsecret'):
            first=command
        else:
            first=None
        if first and (first in ('rcon_password','sv_licensekey','steam_webapikey','sv_tebexsecret') or any(t in first for t in ('password','token','secret','api_key','webhook','mysql_connection_string','licensekey'))):
                warnings.append({'line':n,'severity':'review','message':'Sensitive setting present: '+first+' (value intentionally redacted).'})
    return {'path':p.relative_to(core.workspace_root()).as_posix(),'ensured_resources':ensured[:150],
            'warnings':warnings[:100],'note':'Config values are never returned. Check config file access and secrets outside version control.'}

@core.scan_report
def audit_performance(path='.'):
    findings=[]
    for p,rel in _sources(path):
        if p.suffix.lower()!='.lua':continue
        lines=_mask_literals(core.read(p)).splitlines()
        for n,line in enumerate(lines):
            if line.lstrip().startswith('--'):continue
            neighbors='\n'.join(lines[n:n+14])
            def note(rule,msg):
                if len(findings)<MAX_MATCHES:findings.append({'path':rel,'line':n+1,'rule':rule,'severity':'review','message':msg})
            if re.search(r'\bwhile\s+true\s+do\b',line) and re.search(r'\bWait\s*\(\s*0\s*\)',neighbors):
                note('per-frame-loop','Continuous Wait(0) loop; gate work on active state and profile actual cost.')
            if re.search(r'\bGetHashKey\s*\(\s*[\x27"]',line) and 'while' in '\n'.join(lines[max(0,n-8):n]):
                note('runtime-hash-in-loop','Compile-time backtick hash may be more appropriate in frequently called Lua paths.')
            if re.search(r'\bWait\s*\(\s*0\s*\)',line) and 'server' in rel.lower():
                note('server-frame-wait','Server-side zero-wait loop; check CPU cost and consider a longer interval.')
    return {'findings':findings,'truncated':len(findings)>=MAX_MATCHES,
            'note':'Static heuristics. Measure with the FiveM profiler before claiming performance improvement.'}

@core.scan_report
def audit_sql(path='.'):
    findings=[]
    sqlcalls=re.compile(r'\b(?:MySQL\.(?:query|update|insert|scalar|single|prepare|transaction)(?:\.await)?|exports\.oxmysql)\b')
    for p,rel in _sources(path):
        if p.suffix.lower() not in {'.lua','.js','.ts'}:continue
        source=core.read(p)
        lines=(_code_without_comments(source) if p.suffix.lower()=='.lua' else source).splitlines()
        executable=(_mask_literals(source) if p.suffix.lower()=='.lua' else source).splitlines()
        for n,line in enumerate(lines):
            if line.lstrip().startswith(('--','//')):continue
            active=executable[n] if n<len(executable) else ''
            if sqlcalls.search(active):
                fragment='\n'.join(lines[n:n+4])
                if re.search(r'\.\.\s*\w+|\$\{|["\x27]\s*\+\s*\w+',fragment):
                    if len(findings)<MAX_MATCHES:findings.append({'path':rel,'line':n+1,'severity':'high',
                            'rule':'sql-dynamic-concatenation','message':'Possible dynamic SQL. Check parameter binding.'})
    return {'findings':findings,'truncated':len(findings)>=MAX_MATCHES,
            'note':'Heuristic review, not a SQL injection verdict. Parameterize every dynamic value.'}

def _asset_base(kind):
    if kind not in ('snippets','templates'):raise ValueError('unknown asset kind')
    source=Path(__file__).resolve().parents[1]/kind
    return (source if source.is_dir() else Path(__file__).resolve().parent/'_assets'/kind).resolve()

def _assets(kind):
    if kind not in ('snippets','templates'):raise ValueError('unknown asset kind')
    base=_asset_base(kind)
    if not base.is_dir():return []
    paths=[p for p in base.rglob('*') if p.is_file() and not p.is_symlink()]
    return sorted(paths)

def list_assets(kind,query='',limit=100):
    if not isinstance(query,str) or len(query)>100:raise ValueError('Invalid query')
    if not isinstance(limit,int) or isinstance(limit,bool) or not 1<=limit<=150:raise ValueError('Invalid limit')
    paths=_assets(kind)
    base=_asset_base(kind)
    names=[p.relative_to(base).as_posix() for p in paths if query.casefold() in str(p).casefold()]
    return {'kind':kind,'files':names[:limit],'files_total':len(paths),
            'matching':len(names),'truncated':len(names)>limit,
            'note':'Files are starter reference material; validate scripts in a FiveM development server.'}

def preview_asset(kind,name):
    if not isinstance(name,str) or len(name)>180:raise ValueError('Invalid asset name')
    base=_asset_base(kind)
    p=(base/name).resolve()
    if not p.is_relative_to(base) or not p.is_file() or p.is_symlink():raise ValueError('Requested asset is unavailable')
    if p.stat().st_size>60_000:raise ValueError('Asset too large to preview')
    return {'kind':kind,'name':p.relative_to(base).as_posix(),'content':p.read_text(encoding='utf-8')}
