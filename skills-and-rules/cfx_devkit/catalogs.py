"""Opt-in cached GTA V / FiveM asset reference catalogs.

No upstream dataset is redistributed. Sources are retrieved only on explicit
sync and retained in user-local cache. No RedM content.
"""
from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.request import Request, urlopen
from .natives import _cache_dir

ROOT = "https://raw.githubusercontent.com/DurtyFree/gta-v-data-dumps/master/"
UPSTREAM = "https://github.com/DurtyFree/gta-v-data-dumps"
MAX_BYTES = 32_000_000

@dataclass(frozen=True)
class Catalog:
    filename: str
    min_entries: int
    kind: str

CATALOGS = {
    "movement": Catalog("movementClipsetsCompact.json", 400, "named-clips"),
    "walking": Catalog("movementClipsetsWalkingCompact.json", 150, "named-clips"),
    "particles": Catalog("particleEffectsCompact.json", 250, "particle-clips"),
    "scenarios": Catalog("scenariosCompact.json", 150, "names"),
    "ipls": Catalog("ipls.json", 600, "objects"),
    "interiors": Catalog("mloInteriors.json", 200, "objects"),
    "vehicles": Catalog("vehicles.json", 600, "objects"),
    "peds": Catalog("peds.json", 400, "objects"),
    "props": Catalog("ObjectList.ini", 5000, "names"),
}
# Game build changes can alter counts. Lower bounds catch truncation without
# promising a static total. No RedM content or undocumented APIs.
def _path(name):
    if name not in CATALOGS:raise ValueError("Unknown catalog: "+str(name))
    return _cache_dir() / ("assets_" + CATALOGS[name].filename)

def _records(name,data):
    descriptor=CATALOGS[name]
    if not isinstance(data,list) or len(data)<descriptor.min_entries or len(data)>120_000:
        raise ValueError(f"Unexpected/incomplete {name} schema: not enough list entries")
    if descriptor.kind in ("named-clips","particle-clips"):
        groupkey="DictionaryName" if descriptor.kind=="particle-clips" else "Name"
        clipkey="EffectNames" if descriptor.kind=="particle-clips" else "Clips"
        if not all(isinstance(row,dict) and isinstance(row.get(groupkey),str) and
                   isinstance(row.get(clipkey),list) for row in data):
            raise ValueError(f"Unexpected {name} dictionary/clip format")
    elif descriptor.kind=="names":
        if not all(isinstance(row,str) for row in data):
            raise ValueError("Expected scenario name strings")
    else:
        if not all(isinstance(row,dict) and isinstance(row.get("Name"),str) for row in data):
            raise ValueError(f"Unexpected {name} object format")
    return data

@lru_cache(maxsize=10)
def _load(name):
    path=_path(name)
    if not path.is_file():return None
    return _records(name,json.loads(path.read_text(encoding="utf-8")))

def status():
    entries={}
    for name,desc in CATALOGS.items():
        try:rows=_load(name)
        except (OSError,ValueError):rows=None
        item={"downloaded":rows is not None,"entry_count":len(rows) if rows else 0,
              "upstream":UPSTREAM + "/blob/master/" + desc.filename}
        if rows and desc.kind in ("named-clips","particle-clips"):
            field="Clips" if desc.kind=="named-clips" else "EffectNames"
            item["clip_count"]=sum(len(x[field]) for x in rows)
        entries[name]=item
    return {"catalogs":entries,"complete":all(v["downloaded"] for v in entries.values()),
            "note":"Counts from locally downloaded source. Every import is opt-in and GTA V only."}

def sync(name):
    if os.environ.get("CFX_ENABLE_NETWORK")!="1":
        raise ValueError("Network download disabled; set CFX_ENABLE_NETWORK=1 with user approval")
    if name not in CATALOGS:raise ValueError("Unknown catalog")
    url=ROOT+CATALOGS[name].filename
    req=Request(url,headers={"User-Agent":"CFX-DevKit/0.4","Accept":"application/json"})
    with urlopen(req,timeout=45) as response:payload=response.read(MAX_BYTES+1)
    if len(payload)>MAX_BYTES:raise ValueError("Dataset exceeds 32MB limit")
    if name=="props":
        # Source is a plain newline-separated list of object model names.
        raw_names=[line.strip() for line in payload.decode("utf-8").splitlines() if line.strip() and not line.startswith(("[","#",";"))]
        rows=_records(name,raw_names)
        stored=json.dumps(rows,ensure_ascii=False).encode("utf-8")
    else:
        rows=_records(name,json.loads(payload.decode("utf-8")))
        stored=payload
    path=_path(name)
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix="cfx-asset-",suffix=".tmp",dir=path.parent)
    try:
        with os.fdopen(fd,"wb") as f:f.write(stored)
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)
    meta={"sha256":hashlib.sha256(payload).hexdigest(),"source":url,"entries":len(rows)}
    _load.cache_clear()
    return {"catalog":name,"count":len(rows),"bytes":len(payload),"sha256":meta["sha256"],
            "source":url,"cache_path":str(path),"note":"Source names only; runtime build/model compatibility not verified."}

def search(name,query="",offset=0,limit=25,search_clips=False):
    if name not in CATALOGS:raise ValueError("Unknown catalog")
    if not isinstance(query,str) or len(query)>150:raise ValueError("Invalid query")
    if not isinstance(offset,int) or isinstance(offset,bool) or not 0<=offset<=1_000_000:
        raise ValueError("Invalid offset")
    if not isinstance(limit,int) or isinstance(limit,bool) or not 1<=limit<=50:
        raise ValueError("Limit must be 1–50")
    rows=_load(name)
    if rows is None:return {"catalog":name,"downloaded":False,"results":[],
                            "message":"Run cfx_sync_asset_catalog (CFX_ENABLE_NETWORK=1) to fetch this GTA V reference."}
    k=CATALOGS[name].kind
    field="DictionaryName" if k=="particle-clips" else "Name"
    child_field="EffectNames" if k=="particle-clips" else "Clips"
    q=query.casefold()
    output=[];total=0
    for row in rows:
        if k=="names":
            key=row
            obj={"name":row}
        else:
            key=row[field]
            obj={"name":key}
            if k in ("named-clips","particle-clips"):
                obj["clip_count"]=len(row[child_field])
                obj["clips_preview"]=row[child_field][:5]
            elif name=="ipls":
                obj["position"]=row.get("Position")
                obj["dlc"]=row.get("DlcName")
            elif name=="interiors":
                obj["dlc"]=row.get("DlcName")
                obj["entities_count"]=row.get("TotalEntitiesCount")
            elif name in ("vehicles","peds"):
                obj["model"]=row.get("Name")
                obj["hash"]=row.get("Hash") or row.get("HashKey")
        if search_clips and k in ("named-clips","particle-clips"):
            for clip in row[child_field]:
                if not isinstance(clip,str):continue
                if q in clip.casefold():
                    if offset<=total<offset+limit:
                        output.append({"dictionary":key,"clip":clip})
                    total+=1
        elif not q or q in key.casefold():
            if offset<=total<offset+limit:output.append(obj)
            total+=1
    return {"catalog":name,"downloaded":True,"source":UPSTREAM+"/blob/master/"+CATALOGS[name].filename,
            "query":query,"total_matches":total,"offset":offset,
            "next_offset":offset+limit if offset+limit<total else None,
            "results":output,"note":"Names extracted from GTA V game assets; runtime compatibility not guaranteed."}

def validate_pair(name,dictionary,clip):
    if name not in ("movement","walking","particles"):raise ValueError("Pair lookup supports movement, walking and particles")
    if not all(isinstance(v,str) and 0<len(v)<=200 for v in (dictionary,clip)):
        raise ValueError("Invalid dictionary or clip")
    rows=_load(name)
    if rows is None:return {"catalog":name,"available":False,"pair_exists":False}
    kind=CATALOGS[name].kind
    field="DictionaryName" if kind=="particle-clips" else "Name"
    clips="EffectNames" if kind=="particle-clips" else "Clips"
    found=next((r for r in rows if r[field]==dictionary),None)
    return {"catalog":name,"available":True,"dictionary_exists":found is not None,
            "pair_exists":found is not None and clip in found[clips],
            "runtime_verified":False}

def lua_example(name,dictionary,clip):
    if name not in ("movement","walking","particles"):raise ValueError("No Lua example for this catalog")
    result=validate_pair(name,dictionary,clip)
    if not result.get("pair_exists"):raise ValueError("Exact asset pair not in local index; sync reference and check spelling")
    if not dictionary.isascii() or not clip.isascii() or any(ord(c)<32 for c in dictionary+clip):
        raise ValueError("Unsafe animation/particle identifier")
    d=json.dumps(dictionary);c=json.dumps(clip)
    if name=="particles":
        script=f"""-- FiveM client only: test on a development server.
local dictionary = {d}
local effect = {c}
RequestNamedPtfxAsset(dictionary)
local untilTime = GetGameTimer() + 5000
while not HasNamedPtfxAssetLoaded(dictionary) and GetGameTimer() < untilTime do Wait(0) end
if not HasNamedPtfxAssetLoaded(dictionary) then return end
UseParticleFxAssetNextCall(dictionary)
local ped = PlayerPedId()
if ped ~= 0 then
  local coords = GetEntityCoords(ped)
  StartParticleFxNonLoopedAtCoord(effect, coords.x, coords.y, coords.z, 0.0, 0.0, 0.0, 1.0, false, false, false)
end
RemoveNamedPtfxAsset(dictionary)
"""
    else:
        script=f"""-- FiveM client only: clipset must be applicable to this ped and game build.
local clipset = {d}
RequestAnimSet(clipset)
local untilTime = GetGameTimer() + 5000
while not HasAnimSetLoaded(clipset) and GetGameTimer() < untilTime do Wait(0) end
if not HasAnimSetLoaded(clipset) then return end
local ped = PlayerPedId()
if ped == 0 then return end
SetPedMovementClipset(ped, clipset, 0.25)
-- ResetPedMovementClipset(ped, 0.25) when movement style should end.
-- Available clip entry: {clip}
-- Clip names in this dump do not imply all clips can be played with TaskPlayAnim.
"""
    return {"catalog":name,"lua":script,"source":UPSTREAM,
            "runtime_verified":False,"note":"Review this development-only snippet and verify natives on target client."}
