"""Curated documented FiveM events. Framework-specific events are NOT invented."""
from __future__ import annotations
import json
from pathlib import Path

CATALOG=Path(__file__).with_name('data')/'events.json'

def _entries():
    return json.loads(CATALOG.read_text(encoding='utf-8'))['events']

def search_events(query='',group='',side='',limit=25):
    if not isinstance(query,str) or len(query)>160:raise ValueError('query length must be <=160')
    if group not in ('','core','chat','baseevents'):raise ValueError('Unknown group. Use core, chat, baseevents.')
    if side not in ('','client','server'):raise ValueError('side must be client or server')
    if not isinstance(limit,int) or isinstance(limit,bool) or not 1<=limit<=60:raise ValueError('limit must be 1..60')
    q=query.lower().strip()
    results=[r for r in _entries() if (not group or r['group']==group)
             and (not side or side in r['side'])
             and (not q or q in r['name'].lower() or q in r.get('description','').lower())]
    results.sort(key=lambda r:(0 if r['name'].lower()==q else 1 if r['name'].lower().startswith(q) else 2,r['name']))
    return {'total_matches':len(results),'results':results[:limit],'truncated':len(results)>limit,
            'catalog_total':len(_entries()),'scope':'Documented FiveM core, chat, and baseevents. No RedM; no fabricated framework events.'}

def event_detail(name):
    if not isinstance(name,str) or len(name)>180:raise ValueError('Invalid event name')
    results=[r for r in _entries() if r['name'].casefold()==name.casefold()]
    return {'matches':results,'note':'Same event may exist on both sides; check source URL and resource dependencies.'}

def event_groups():
    items=_entries()
    groups={}
    for row in items:
        group=row['group']
        groups[group]=groups.get(group,0)+1
    return {'counts':groups,'total':len(items),'sources':sorted(set(r['source_url'] for r in items)),
            'note':'Counts reflect verified documented entries, not claimed 101-event parity.'}
