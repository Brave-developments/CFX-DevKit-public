"""FiveM-only GTA V and CFX native reference.

Full data is fetched on explicit opt-in from official static.cfx.re endpoints and
saved in a local cache. The distributable contains a tiny verified seed for
offline first-run usability, not a pretend 12,000-native database.
"""
from __future__ import annotations
import json
import hashlib
from datetime import datetime, timezone
import os
import re
import tempfile
import urllib.request
from functools import lru_cache
from pathlib import Path

SOURCES = {
    "gta5": "https://static.cfx.re/natives/natives.json",
    "cfx": "https://static.cfx.re/natives/natives_cfx.json",
}
MAX_BYTES = 25_000_000
MAX_RESULTS = 30
BUNDLED = Path(__file__).with_name("data") / "native_seed.json"

def _cache_dir():
    value = os.environ.get("CFX_DEVKIT_DATA_DIR", "")
    return Path(value).expanduser().resolve() if value else Path.home() / ".cache" / "cfx-devkit"

def _entries(payload, game):
    """Accept official namespace/hash native JSON and normalized rows."""
    output=[]
    if isinstance(payload,list):
        for raw in payload:
            if isinstance(raw,dict):
                obj=_row(raw.get("namespace") or raw.get("ns") or raw.get("category") or "CFX",raw.get("hash") or "",raw,game)
                if obj: output.append(obj)
    elif isinstance(payload,dict):
        for namespace, group in payload.items():
            if isinstance(group,dict):
                for native_hash, raw in group.items():
                    if isinstance(raw,dict):
                        obj=_row(namespace,native_hash,raw,game)
                        if obj: output.append(obj)
            elif isinstance(group,list):
                for raw in group:
                    if isinstance(raw,dict):
                        obj=_row(namespace,raw.get("hash",""),raw,game)
                        if obj:output.append(obj)
    return output

def _row(namespace,native_hash,raw,game):
    name=raw.get("name") or raw.get("native") or raw.get("alias") or ""
    if not isinstance(name,str) or not name.strip():return None
    description=raw.get("description") or raw.get("desc") or ""
    if not isinstance(description,str): description=""
    # Some upstream documentation contains HTML or Markdown. Return concise text only.
    description=re.sub(r'<[^>]+>', ' ', description)
    description=re.sub(r'\s+',' ',description).strip()[:400]
    parameters=raw.get("params") or raw.get("parameters") or []
    if not isinstance(parameters,list): parameters=[]
    parameters=[{'name':str(p.get('name',''))[:70],'type':str(p.get('type',''))[:70]}
                for p in parameters[:30] if isinstance(p,dict)]
    api=raw.get("apiset") or raw.get("apiSet") or ""
    if api not in ('client','server','shared'):api='unknown'
    if game=='gta5':api='unverified'  # Original RAGE database does not reliably tag API side
    h=str(raw.get("hash") or native_hash or "")
    if not re.fullmatch(r'0[xX][0-9A-Fa-f]{8,16}',h):h=""
    return {'name':name.upper(),'namespace':str(namespace).upper()[:60],
            'hash':h.upper().replace('0X','0x'), 'apiset':api, 'returns':str(raw.get("results") or raw.get("return_type") or "")[:100],
            'params':parameters,'description':description, 'source':game,
            'url':f"https://docs.fivem.net/natives/?_{h}" if h else 'https://docs.fivem.net/natives/'}

@lru_cache(maxsize=2)
def _load_source(source):
    if source not in SOURCES: raise ValueError('Supported sources: gta5, cfx')
    path=_cache_dir() / f"natives_{source}.json"
    if path.exists():
        raw=json.loads(path.read_text(encoding='utf-8'))
        result=_entries(raw,source)
        if result:return result,'cached'
    raw=json.loads(BUNDLED.read_text(encoding='utf-8'))
    return _entries(raw[source],source),'bundled-seed'

def index_status():
    result={}
    for source in SOURCES:
        rows,origin=_load_source(source)
        metadata={}
        sidecar=_cache_dir()/f'natives_{source}.meta.json'
        if origin=='cached' and sidecar.is_file():
            try:metadata=json.loads(sidecar.read_text(encoding='utf-8'))
            except (OSError,ValueError):pass
        result[source]={'count':len(rows),'origin':origin,'upstream':SOURCES[source],'provenance':metadata}
    return {'datasets':result,'hint':'Run cfx_sync_natives with CFX_ENABLE_NETWORK=1 for complete official GTA V and CFX data. No RedM data.'}

def sync_natives():
    if os.environ.get('CFX_ENABLE_NETWORK')!='1':
        raise ValueError('Network disabled. Set CFX_ENABLE_NETWORK=1 to opt into fetching official FiveM native JSON.')
    dest=_cache_dir()
    dest.mkdir(parents=True,exist_ok=True)
    results={}
    for source,url in SOURCES.items():
        request=urllib.request.Request(url,headers={'User-Agent':'CFX-DevKit/0.2 (+https://github.com/Brave-developments/CFX-DevKit)','Accept':'application/json'})
        with urllib.request.urlopen(request,timeout=35) as response:
            data=response.read(MAX_BYTES+1)
        if len(data)>MAX_BYTES:raise ValueError(f'{source}: native data exceeds size limit')
        parsed=json.loads(data.decode('utf-8'))
        rows=_entries(parsed,source)
        if len(rows)<200:raise ValueError(f'{source}: unexpected native JSON schema or incomplete dataset ({len(rows)} records). Cache unchanged.')
        fd,tmp=tempfile.mkstemp(prefix='natives-',suffix='.json',dir=dest)
        try:
            with os.fdopen(fd,'wb') as f:f.write(data)
            os.replace(tmp,dest/f'natives_{source}.json')
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
        metadata={"source":url,"sha256":hashlib.sha256(data).hexdigest(),
                  "synced_at_utc":datetime.now(timezone.utc).isoformat(),"count":len(rows)}
        meta_path=dest/f'natives_{source}.meta.json'
        fd_meta,tmp_meta=tempfile.mkstemp(prefix='natives-meta-',suffix='.json',dir=dest)
        try:
            with os.fdopen(fd_meta,'w',encoding='utf-8') as f:json.dump(metadata,f,indent=2)
            os.replace(tmp_meta,meta_path)
        finally:
            if os.path.exists(tmp_meta):os.unlink(tmp_meta)
        _load_source.cache_clear()
        results[source]={'count':len(rows),'origin':'cached','provenance':metadata}
    return {'downloaded':results,'cache_directory':str(dest),'source_urls':SOURCES,
            'note':'Downloaded only official GTA V and CFX native references; no RDR3 data.'}

def _limit(value):
    if not isinstance(value,int) or isinstance(value,bool) or not 1<=value<=MAX_RESULTS:
        raise ValueError(f'limit must be an integer from 1 to {MAX_RESULTS}')
    return value

def find_natives(query='',source='all',namespace='',apiset='',limit=15):
    _limit(limit)
    if source not in ('all','gta5','cfx'): raise ValueError('source must be all, gta5, or cfx')
    if apiset not in ('','client','server','shared','unverified','unknown'):
        raise ValueError('Invalid apiset filter')
    if not isinstance(query,str) or len(query)>160:raise ValueError('query must be text <=160 chars')
    if not isinstance(namespace,str) or len(namespace)>60:raise ValueError('namespace must be text <=60 chars')
    q=query.strip().casefold()
    ns=namespace.strip().casefold()
    matches=[];coverage={}
    for s in (SOURCES if source=='all' else [source]):
        items,origin=_load_source(s)
        coverage[s]={'count':len(items),'origin':origin}
        for row in items:
            if ns and row['namespace'].casefold()!=ns:continue
            if apiset and row['apiset']!=apiset:continue
            name=row['name'].casefold()
            if q and not (q in name or q in row['hash'].casefold() or q in row['description'].casefold()):
                continue
            score=(0 if name==q or row['hash'].casefold()==q else
                   1 if name.startswith(q) else
                   2 if q in name else 3)
            matches.append((score,row['namespace'],row['name'],row))
    matches.sort(key=lambda x:(x[0],x[1],x[2]))
    return {'query':query,'total_matches':len(matches),
            'results':[v[3] for v in matches[:limit]],'coverage':coverage,
            'truncated':len(matches)>limit,
            'note':'GTA V native client/server side is unverified; do not infer server availability from name alone.'}

def native_detail(name_or_hash,source='all'):
    if not isinstance(name_or_hash,str) or not name_or_hash.strip():
        raise ValueError('name_or_hash required')
    matches=find_natives(name_or_hash,source=source,limit=MAX_RESULTS)
    key=name_or_hash.casefold().strip()
    exact=[r for r in matches['results'] if r['name'].casefold()==key or r['hash'].casefold()==key]
    return {'matches':exact,'coverage':matches['coverage'],
            'note':'No exact result may mean the full catalog has not been synced yet.'}

def native_namespaces(source='all'):
    if source not in ('all','gta5','cfx'):raise ValueError('Invalid native source')
    counts={}
    for s in (SOURCES if source=='all' else [source]):
        rows,_=_load_source(s)
        for r in rows:counts[r['namespace']]=counts.get(r['namespace'],0)+1
    return {'namespaces':dict(sorted(counts.items())),'total':sum(counts.values()),
            'note':'Counts are of locally available official data or bundled seed, never projected.'}
