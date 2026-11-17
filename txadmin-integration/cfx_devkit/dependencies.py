"""Literal manifest dependencies and client visibility; never executes Lua."""
import re
from collections import defaultdict,deque
from . import core
from .intelligence import _code_without_comments,_mask_literals

_STRING=re.compile(r'''(['"])((?:\\.|(?!\1)[\s\S])*)\1''')
_DIRECTIVE=re.compile(r'(?<![\w.:])(?:dependency|dependencies|provide|provides|server_only|client_only)\b')
MAX_FINDINGS=150


def _values(source,masked,end):
    at=end
    while at<len(source) and source[at].isspace():at+=1
    if at<len(source) and source[at]=='(':
        at+=1
        while at<len(source) and source[at].isspace():at+=1
    if at<len(source) and source[at]=='{':
        depth=1;stop=at+1
        while stop<len(masked) and depth:
            if masked[stop]=='{':depth+=1
            elif masked[stop]=='}':depth-=1
            stop+=1
        if depth:return None
        body=source[at+1:stop-1]
        matches=list(_STRING.finditer(body))
        if re.sub(_STRING,'',body).strip(' \t\r\n,;') or any('\\' in m[2] for m in matches):return None
        return [m[2] for m in matches]
    match=_STRING.match(source,at)
    if not match or '\\' in match[2]:return None
    if re.match(r'\s*\)?\s*(?:\.\.|[+*/%^-])',source[match.end():]):return None
    return [match[2]]


def metadata(source):
    clean=_code_without_comments(source);masked=_mask_literals(clean)
    deps=[];provides=[];unknown=[];server_only=False
    conditional=bool(re.search(r'\b(?:if|function|for|while|repeat)\b',masked))
    for match in _DIRECTIVE.finditer(masked):
        name=match[0];values=_values(clean,masked,match.end())
        if name=='client_only':
            # This is not a documented Cfx side directive. Do not invent its
            # runtime semantics or use it as proof of a client-only resource.
            unknown.append(name);continue
        if name=='server_only':
            # Cfx treats the presence of a metadata value as the flag, even
            # server_only 'no'. Dynamic/conditional expressions stay unknown.
            if values and not conditional:server_only=True
            else:server_only=None;unknown.append(name)
        elif values is None or conditional:
            unknown.append(name)
        elif name in ('dependency','dependencies'):deps.extend(values)
        else:provides.extend(values)
    return {'dependencies':sorted(set(deps)),'provides':sorted(set(provides)),
            'server_only':server_only,'client_visible':None if server_only is None else not server_only,
            'unknown_metadata':sorted(set(unknown))}


@core.scan_report
def analyze(path='.'):
    base=core.safe_path(path)
    if not base.is_dir():raise ValueError('Project directory does not exist')
    found=defaultdict(list)
    for p in core.files_under(base):
        if p.name=='fxmanifest.lua':
            found[p.parent.name].append({'path':p.parent.relative_to(core.workspace_root()).as_posix(),
                                        **metadata(core.read(p))})
    resources={name:rows[0] for name,rows in found.items() if len(rows)==1}
    duplicate={name:[r['path'] for r in rows] for name,rows in found.items() if len(rows)>1}
    names=defaultdict(set)
    for name,row in resources.items():
        names[name].add(name)
        for alias in row['provides']:names[alias].add(name)
    missing=[];ambiguous=[];findings=[];count=0;reverse=defaultdict(set);queue=deque()
    def add(item):
        nonlocal count
        count+=1
        if len(findings)<MAX_FINDINGS:findings.append(item)
    for name,row in resources.items():
        if row['unknown_metadata']:
            add({'severity':'review','rule':'dynamic-manifest-metadata','resource':name,'path':row['path'],
                 'message':'Side/dependency metadata is dynamic or unsupported; runtime compatibility is unverified.'})
        for dep in row['dependencies']:
            if dep.startswith('/'):continue
            choices=names.get(dep,set())
            if dep in duplicate or len(choices)>1:
                ambiguous.append({'resource':name,'dependency':dep});continue
            if not choices:
                missing.append({'resource':name,'dependency':dep});continue
            target=next(iter(choices));reverse[target].add(name)
            if row['client_visible'] is True and resources[target]['server_only'] is True:
                item={'severity':'error','rule':'client-depends-on-server-only','resource':name,
                      'path':row['path'],'dependency':dep,'resolved_resource':target,
                      'dependency_path':[name,target],
                      'message':'Client-visible resource depends on a server_only resource that is not downloaded by clients.'}
                add(item);queue.append(item)
    # Propagate a bounded set of known failures through dependent resources.
    reported={r['resource'] for r in findings if r['severity']=='error'}
    while queue and len(findings)<MAX_FINDINGS:
        child=queue.popleft()
        for parent in sorted(reverse[child['resource']]):
            if parent in reported or resources[parent]['client_visible'] is not True:continue
            reported.add(parent)
            item={**child,'resource':parent,'path':resources[parent]['path'],
                  'rule':'transitive-client-dependency-failure',
                  'dependency_path':[parent]+child['dependency_path'][:15],
                  'message':'A required client-visible dependency has a server_only dependency failure.'}
            add(item);queue.append(item)
    ambiguous+= [{'resource':name,'dependency':None} for name in duplicate]
    unknown=any(r['unknown_metadata'] for r in resources.values())
    return {'resources':resources,'unresolved_in_scanned_tree':missing,
            'ambiguous_resources':duplicate,'ambiguous_dependencies':ambiguous,
            'findings':findings,'findings_total':None if queue else count,'findings_observed':count,
            'truncated':count>len(findings) or bool(queue),
            'analysis_complete':not unknown and not ambiguous and not missing and not queue,
            'note':'Literal static metadata only; Lua is not executed. Unresolved dependencies may be outside the workspace. '
                   'Unknown/dynamic metadata and ambiguous providers require review; this is not a runtime health verdict.'}
