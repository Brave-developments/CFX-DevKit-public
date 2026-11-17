"""GTA V animation dictionary and clip reference (FiveM only).

Source: DurtyFree/gta-v-data-dumps/animDictsCompact.json.
The upstream dump has no explicit license in its root; do not redistribute
the full dataset within this repository. Download it to the user's own local
cache after CFX_ENABLE_NETWORK=1, with source attribution and actual counts.

A dictionary/clip appearing in a game data dump does not guarantee that
TaskPlayAnim works on a particular ped, build or resource.
"""
from __future__ import annotations

from datetime import datetime, timezone
from difflib import get_close_matches
from functools import lru_cache
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import urllib.request

from .natives import _cache_dir

SOURCE_REPOSITORY = "https://github.com/DurtyFree/gta-v-data-dumps"
SOURCE_FILE = SOURCE_REPOSITORY + "/blob/master/animDictsCompact.json"
SOURCE_RAW = "https://raw.githubusercontent.com/DurtyFree/gta-v-data-dumps/master/animDictsCompact.json"
FILE_NAME = "animDictsCompact.json"
SEED = Path(__file__).with_name("data") / "animation_seed.json"
MAX_DOWNLOAD_BYTES = 30_000_000
MAX_RESULTS = 100
MIN_COMPLETE_DICTS = 15_000
MIN_COMPLETE_CLIPS = 190_000
MAX_NAME_LEN = 256

def _cache_path():
    return _cache_dir() / FILE_NAME

def _validate_text(value, field, allow_empty=False, length=MAX_NAME_LEN):
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ValueError(f"{field} must be a nonempty string")
    if len(value) > length or any(ord(ch) < 32 for ch in value):
        raise ValueError(f"{field} must be no longer than {length} characters, without control characters")
    return value

def _positive_int(value, field, maximum=MAX_RESULTS, minimum=1):
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise ValueError(f"{field} must be between {minimum} and {maximum}")
    return value

def _parse_records(data, complete=False):
    if not isinstance(data, list) or len(data) > 50_000 or not data:
        raise ValueError("Expected nonempty list of GTA V animation dictionaries")
    result={}
    total=0
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"Invalid dictionary row {index}")
        name=_validate_text(item.get("DictionaryName"), "DictionaryName")
        clips=item.get("Animations")
        if not isinstance(clips, list) or len(clips) > 12_000:
            raise ValueError(f"Invalid Animations list for {name}")
        if name in result:
            raise ValueError(f"Duplicate animation dictionary: {name}")
        parsed=[_validate_text(clip, "Animation clip") for clip in clips]
        result[name]=parsed
        total += len(parsed)
        if total > 1_000_000:
            raise ValueError("Animation dataset exceeds accepted size")
    if complete and (len(result)<MIN_COMPLETE_DICTS or total<MIN_COMPLETE_CLIPS):
        raise ValueError(f"Incomplete/unexpected upstream animation dump: {len(result)} dictionaries, {total} clips")
    return result, total

@lru_cache(maxsize=1)
def _load():
    path=_cache_path()
    if path.is_file():
        data=json.loads(path.read_text(encoding="utf-8"))
        records,clips=_parse_records(data, complete=True)
        return records,clips,"local-full-cache"
    data=json.loads(SEED.read_text(encoding="utf-8"))
    records,clips=_parse_records(data)
    return records,clips,"bundled-sample"

def status():
    rows,count,coverage=_load()
    meta_path=_cache_path().with_suffix(".meta.json")
    provenance={}
    if coverage=="local-full-cache" and meta_path.is_file():
        try: provenance=json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError,ValueError):pass
    return {"coverage":coverage,"complete":coverage=="local-full-cache",
        "dictionary_count":len(rows),"clip_count":count,
        "source_repository":SOURCE_REPOSITORY,"source_file":SOURCE_FILE,
        "provenance":provenance,
        "note":("Complete dump available from the imported upstream snapshot; actual game availability varies by build."
                if coverage=="local-full-cache" else
                "Only bundled example pairs available. Run cfx_sync_animations with CFX_ENABLE_NETWORK=1 for the entire upstream dump.")}

def sync_animations():
    if os.environ.get("CFX_ENABLE_NETWORK")!="1":
        raise ValueError("Network sync disabled. Set CFX_ENABLE_NETWORK=1 and explicitly request synchronization.")
    req=urllib.request.Request(SOURCE_RAW,headers={
        "User-Agent":"CFX-DevKit/0.3 (https://github.com/Brave-developments/CFX-DevKit)",
        "Accept":"application/json"})
    with urllib.request.urlopen(req, timeout=45) as response:
        raw=response.read(MAX_DOWNLOAD_BYTES+1)
    if len(raw)>MAX_DOWNLOAD_BYTES:
        raise ValueError("Upstream animation dump exceeds safe download size")
    decoded=json.loads(raw.decode("utf-8"))
    entries, count=_parse_records(decoded, complete=True)
    path=_cache_path()
    path.parent.mkdir(parents=True,exist_ok=True)
    info={"source":SOURCE_FILE, "sha256":sha256(raw).hexdigest(),
          "synced_at_utc":datetime.now(timezone.utc).isoformat(),
          "dictionary_count":len(entries),"clip_count":count}
    fd, temporary=tempfile.mkstemp(prefix="anim-dicts-",suffix=".json",dir=path.parent)
    try:
        with os.fdopen(fd,"wb") as file: file.write(raw)
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)
    # A failed metadata write must not invalidate the validated data cache.
    path.with_suffix(".meta.json").write_text(json.dumps(info,indent=2),encoding="utf-8")
    _load.cache_clear()
    return {"complete":True,"dictionary_count":len(entries),
            "clip_count":count,"cache_path":str(path),"source":SOURCE_FILE,
            "sha256":info["sha256"],"note":"Game data dump, not a live FiveM client runtime check."}

def _page(offset,limit):
    if not isinstance(offset,int) or isinstance(offset,bool) or not 0<=offset<=1_000_000:
        raise ValueError("offset must be an integer from 0 to 1000000")
    return offset,_positive_int(limit,"limit")

def _coverage(records,clip_count,kind):
    return {"coverage":kind,"complete":kind=="local-full-cache",
            "dictionary_count":len(records),"clip_count":clip_count,
            "source":SOURCE_FILE}

def search_dictionaries(query="",offset=0,limit=25):
    query=_validate_text(query,"query",allow_empty=True,length=160)
    offset,limit=_page(offset,limit)
    records,clip_count,kind=_load()
    q=query.casefold().strip()
    matches=[name for name in records if not q or q in name.casefold()]
    matches.sort(key=lambda name:(0 if name.casefold()==q else 1 if name.casefold().startswith(q) else 2,name.casefold()))
    results=[{"dictionary":name,"clip_count":len(records[name]),"clips_preview":records[name][:5]}
             for name in matches[offset:offset+limit]]
    return {**_coverage(records,clip_count,kind),"query":query,"offset":offset,
            "total_matches":len(matches),"next_offset":offset+limit if offset+limit<len(matches) else None,
            "results":results}

def search_clips(query, dictionary="",offset=0,limit=25):
    query=_validate_text(query,"query",length=160)
    dictionary=_validate_text(dictionary,"dictionary",allow_empty=True)
    offset,limit=_page(offset,limit)
    records,clip_count,kind=_load()
    if dictionary and dictionary not in records:
        return {**_coverage(records,clip_count,kind),"results":[],"total_matches":0,
                "error":"Dictionary not found; if coverage is bundled-sample, sync the full dataset."}
    q=query.casefold()
    names=[dictionary] if dictionary else records.keys()
    # Iterate without materializing up to 269k result dictionaries.
    total=0
    found=[]
    for name in names:
        for clip in records[name]:
            if q in clip.casefold():
                if offset<=total<offset+limit:
                    found.append({"dictionary":name,"clip":clip})
                total+=1
    return {**_coverage(records,clip_count,kind),"query":query,"dictionary_filter":dictionary,
            "offset":offset,"total_matches":total,
            "next_offset":offset+limit if offset+limit<total else None,
            "results":found,"note":"This searches clip names only. Use cfx_search_animation_dicts to search dictionary names."}

def dictionary_details(dictionary,offset=0,limit=50):
    dictionary=_validate_text(dictionary,"dictionary")
    offset,limit=_page(offset,limit)
    records,clip_count,kind=_load()
    if dictionary not in records:
        suggestions=get_close_matches(dictionary, list(records), n=5, cutoff=.5)
        return {**_coverage(records,clip_count,kind),"found":False,"dictionary":dictionary,
                "suggested_dictionaries":suggestions}
    clips=records[dictionary]
    return {**_coverage(records,clip_count,kind),"found":True,"dictionary":dictionary,
            "dictionary_clip_count":len(clips),"offset":offset,"clips":clips[offset:offset+limit],
            "next_offset":offset+limit if offset+limit<len(clips) else None}

def validate_pair(dictionary,clip):
    dictionary=_validate_text(dictionary,"dictionary")
    clip=_validate_text(clip,"clip")
    records,count,kind=_load()
    exists=dictionary in records
    valid=exists and clip in records[dictionary]
    output={**_coverage(records,count,kind),"dictionary":dictionary,"clip":clip,
            "dictionary_found":exists,"clip_found":bool(valid),
            "pair_in_dump":bool(valid),
            "runtime_verified":False,
            "note":"An exact pair in the dump is not proof it can play on a given ped or game build."}
    if not exists:
        output["suggested_dictionaries"]=get_close_matches(dictionary, list(records), n=5, cutoff=.5)
    elif not valid:
        output["suggested_clips"]=get_close_matches(clip,records[dictionary],n=7,cutoff=.35)
    return output

def _lua_quote(s):
    # All names are input-validated. JSON-escaped string literals are Lua 5.4 compatible for GTA ASCII names.
    if not s.isascii():
        raise ValueError("Non-ASCII animation identifiers require explicit manual review before generating Lua")
    return json.dumps(s,ensure_ascii=True)

def generate_lua(dictionary,clip,flag=49,duration=-1,timeout_ms=5000):
    result=validate_pair(dictionary,clip)
    if not result["pair_in_dump"]:
        raise ValueError("Dictionary/clip pair is not in the current dataset; sync the full list or correct the names.")
    if not isinstance(flag,int) or isinstance(flag,bool) or not 0<=flag<=1048575:
        raise ValueError("flag must be an integer between 0 and 1048575")
    if not isinstance(duration,int) or isinstance(duration,bool) or not -1<=duration<=3600000:
        raise ValueError("duration must be between -1 and 3600000 ms")
    _positive_int(timeout_ms,"timeout_ms",maximum=30000,minimum=100)
    code=f"""-- FiveM client-side only. Dictionary/clip exist in a game data dump.
-- Test on a local client; cutscene/object/vehicle clips may not play on a ped.
local dict = {_lua_quote(dictionary)}
local clip = {_lua_quote(clip)}
local ped = PlayerPedId()
if ped == 0 or not DoesEntityExist(ped) then return end

RequestAnimDict(dict)
local startTime = GetGameTimer()
while not HasAnimDictLoaded(dict) and GetGameTimer() - startTime < {timeout_ms} do
    Wait(0)
end

if not HasAnimDictLoaded(dict) then
    print(('Animation dictionary failed to load: %s'):format(dict))
    return
end

TaskPlayAnim(ped, dict, clip, 8.0, -8.0, {duration}, {flag}, 0.0, false, false, false)
RemoveAnimDict(dict)
"""
    return {"dictionary":dictionary,"clip":clip,"lua":code,"side":"client",
            "source":SOURCE_FILE,"runtime_verified":False,
            "note":"Only name-pair membership was checked. Test ped compatibility and your current GTA V game build."}

def prefix_counts(limit=50):
    _positive_int(limit,"limit")
    records,count,kind=_load()
    prefixes={}
    for name in records:
        prefix=name.split("@",1)[0].split("_",1)[0] or "(none)"
        prefixes[prefix]=prefixes.get(prefix,0)+1
    ranking=sorted(prefixes.items(),key=lambda item:(-item[1],item[0]))
    return {**_coverage(records,count,kind),"total_prefixes":len(prefixes),
            "prefixes":[{"prefix":name,"dictionaries":qty} for name,qty in ranking[:limit]],
            "note":"Prefixes are derived from names, not authoritative animation categories."}
