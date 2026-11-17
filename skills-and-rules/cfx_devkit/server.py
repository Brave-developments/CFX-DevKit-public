"""Minimal MCP stdio server (JSON-RPC 2.0, 2025-11-25). No third-party dependencies.

Stderr is for diagnostic messages only; stdout is exclusive to MCP frames.
"""
from __future__ import annotations
import json
import sys
from cfx_devkit import core, natives, events, inspection, animations, catalogs, intelligence, profiler, ast_analysis, devbridge, controlbridge, livecontrol, clientlaunch, gameinput, fxserverlaunch, performance, resourceprofile

VERSION='1.0.0rc1'
PROTOCOLS={'2025-11-25','2025-06-18','2025-03-26'}

def schema(properties,required=()):
    return {'type':'object','properties':properties,'required':list(required),'additionalProperties':False}

def string(description): return {'type':'string','description':description}

def tool(name,description,properties=None,required=(),read_only=True):
    return {'name':name,'description':description,'inputSchema':schema(properties or {},required),
            'annotations':{'readOnlyHint':read_only,'destructiveHint':False,'idempotentHint':read_only}}

PATH=string('Workspace-relative folder; confined to configured CFX_WORKSPACE_ROOT (default .).')
TOOLS=[
    tool('cfx_scan_project','Find FiveM resources and detect likely framework(s).',{'path':PATH}),
    tool('cfx_detect_framework','Heuristically identify ESX, QBCore, Qbox, ox_core from source context.',{'path':PATH}),
    tool('cfx_validate_manifest','Inspect fxmanifest.lua and referenced files without executing the manifest.',{'path':string('Workspace-relative fxmanifest.lua file or its resource folder.')},['path']),
    tool('cfx_audit_security','Check common FiveM security and performance red flags; findings need human review.',{'path':PATH}),
    tool('cfx_audit_nui','Check Lua↔browser NUI integration signals and likely missing links.',{'path':PATH}),
    tool('cfx_resource_preview','Preview new Lua resource files without writing to disk.',{'name':string('New lowercase resource name.'),'framework':{'type':'string','enum':['standalone','qbox','qbcore','esx']},'with_nui':{'type':'boolean'}},['name']),
    tool('cfx_scaffold_resource','Write a new resource only when CFX_ENABLE_WRITES=1; never overwrite an existing folder.',{'name':string('New lowercase resource name.'),'framework':{'type':'string','enum':['standalone','qbox','qbcore','esx']},'with_nui':{'type':'boolean'},'destination':PATH},['name'],False),
    tool('cfx_reference_links','Return curated official Cfx documentation URLs for follow-up research.',{'topic':string('Keyword such as NUI, manifest, events or natives.')}),
    tool('cfx_native_status','Return installed native dataset counts and provenance.',{},[]),
    tool('cfx_sync_natives','Opt-in network download of official GTA V and CFX natives to local cache (requires CFX_ENABLE_NETWORK=1).',{},[],False),
    tool('cfx_search_natives','Search native names/hashes/descriptions; filters for GTA V vs CFX, namespace and API side.',{'query':string('Search term or name.'),'source':{'type':'string','enum':['all','gta5','cfx']},'namespace':string('Search term or name.'),'apiset':{'type':'string','enum':['','client','server','shared','unverified','unknown']},'limit':{'type':'integer','minimum':1,'maximum':100}},[]),
    tool('cfx_native_detail','Lookup exact native name or hash, including arguments and official docs link.',{'name_or_hash':string('Search term or name.'),'source':{'type':'string','enum':['all','gta5','cfx']}},['name_or_hash']),
    tool('cfx_native_namespaces','Get local native namespace counts.',{'source':{'type':'string','enum':['all','gta5','cfx']}},[]),
    tool('cfx_search_events','Search sourced, verified FiveM core and stock-resource events.',{'query':string('Search term or name.'),'group':{'type':'string','enum':['','core','chat','baseevents']},'side':{'type':'string','enum':['','client','server']},'limit':{'type':'integer','minimum':1,'maximum':100}},[]),
    tool('cfx_event_detail','Look up an exact FiveM event with its side, group and source URL.',{'name':string('Search term or name.')},['name']),
    tool('cfx_event_groups','Show available documented event groups and catalog coverage.',{},[]),
    tool('cfx_project_events','Map statically registered and triggered events in this FiveM project.',{'path':PATH},[]),
    tool('cfx_find_exports','Find named Lua/JS resource exports and manifest export declarations.',{'path':PATH},[]),
    tool('cfx_find_commands','Find RegisterCommand and RegisterKeyMapping names and locations.',{'path':PATH},[]),
    tool('cfx_dependency_graph','List resource manifests and their declared dependencies.',{'path':PATH},[]),
    tool('cfx_check_server_cfg','Analyze server.cfg ensuring secrets are never returned.',{'path':string('Search term or name.')},[]),
    tool('cfx_audit_performance','Find possible FiveM Lua per-frame loop and runtime hash issues.',{'path':PATH},[]),
    tool('cfx_audit_sql','Find potentially unparameterized OxMySQL database queries.',{'path':PATH},[]),
    tool('cfx_list_snippets','List bundled FiveM snippets.',{'query':string('Search term or name.'),'limit':{'type':'integer','minimum':1,'maximum':100}},[]),
    tool('cfx_preview_snippet','Read a single bundled snippet file.',{'name':string('Search term or name.')},['name']),
    tool('cfx_list_templates','List bundled FiveM project templates and their files.',{'query':string('Search term or name.'),'limit':{'type':'integer','minimum':1,'maximum':100}},[]),
    tool('cfx_preview_template','Read a single file from a bundled project template.',{'name':string('Search term or name.')},['name']),
    tool('cfx_animation_status','Show the actual locally available GTA V animation dictionary and clip count and upstream source.'),
    tool('cfx_sync_animations','Download full upstream GTA V animation dictionary/clip dump to an opt-in local cache; CFX_ENABLE_NETWORK=1 required.',{},(),False),
    tool('cfx_search_animation_dicts','Find GTA V animation dictionaries by name with result pagination.',{'query':string('Substring of an animation dictionary name; may be empty.'),'offset':{'type':'integer','minimum':0},'limit':{'type':'integer','minimum':1,'maximum':100}}),
    tool('cfx_search_animation_clips','Find clip names across GTA V animation dictionaries, optionally filter by an exact dictionary.',{'query':string('Substring of clip name.'),'dictionary':string('Optional exact dictionary name.'),'offset':{'type':'integer','minimum':0},'limit':{'type':'integer','minimum':1,'maximum':100}},['query']),
    tool('cfx_animation_dict_detail','Get all clips in one dictionary using pagination.',{'dictionary':string('Exact, case-sensitive animation dictionary name.'),'offset':{'type':'integer','minimum':0},'limit':{'type':'integer','minimum':1,'maximum':100}},['dictionary']),
    tool('cfx_validate_animation_pair','Check exact dictionary and clip membership in the downloaded GTA V dump.',{'dictionary':string('Exact dictionary name.'),'clip':string('Exact animation clip name.')},['dictionary','clip']),
    tool('cfx_generate_animation_lua','Generate safe client-side RequestAnimDict/TaskPlayAnim Lua with timeout, only for verified dump pairs.',{'dictionary':string('Exact animation dictionary name.'),'clip':string('Exact clip name.'),'flag':{'type':'integer','minimum':0,'maximum':1048575},'duration':{'type':'integer','minimum':-1,'maximum':3600000},'timeout_ms':{'type':'integer','minimum':100,'maximum':30000}},['dictionary','clip']),
    tool('cfx_animation_prefixes','Explore animation dictionary name prefixes with counts, not authoritative categories.',{'limit':{'type':'integer','minimum':1,'maximum':100}}),
    tool('cfx_asset_catalog_status','Get real locally cached GTA V movement, particles, scenarios, IPL, interior, vehicle and ped record counts.'),
    tool('cfx_sync_asset_catalog','Explicitly download one GTA V asset catalog from the upstream data dump to a local cache.',{'catalog':{'type':'string','enum':['movement','walking','particles','scenarios','ipls','interiors','vehicles','peds','props']}},['catalog'],False),
    tool('cfx_search_asset_catalog','Search one GTA V asset catalog with bounded pagination; supports clip-name search for movement and particles.',{'catalog':{'type':'string','enum':['movement','walking','particles','scenarios','ipls','interiors','vehicles','peds','props']},'query':string('Name substring'),'offset':{'type':'integer','minimum':0},'limit':{'type':'integer','minimum':1,'maximum':50},'search_clips':{'type':'boolean'}},['catalog']),
    tool('cfx_validate_asset_pair','Check exact movement clipset or particle dictionary+clip membership in the downloaded GTA V dump.',{'catalog':{'type':'string','enum':['movement','walking','particles']},'dictionary':string('Exact dictionary or clipset name'),'clip':string('Exact clip name')},['catalog','dictionary','clip']),
    tool('cfx_asset_lua_example','Generate a minimal client-side FiveM particle or movement clipset example for a real downloaded pair.',{'catalog':{'type':'string','enum':['movement','walking','particles']},'dictionary':string('Exact dictionary or clipset name'),'clip':string('Exact clip name')},['catalog','dictionary','clip']),
    tool('cfx_workspace_index','Build a lexically parsed static Lua event/command index from a FiveM workspace.',{'path':PATH}),
    tool('cfx_trace_event','Locate static Lua registrations and sends for an exact event name.',{'name':string('Exact event name'),'path':PATH},['name']),
    tool('cfx_authority_review','Check server-side Lua network handlers and sensitive operations for review leads.',{'path':PATH}),
    tool('cfx_manifest_asset_report','Review GTA V streaming asset filenames and fxmanifest declarations without parsing binary assets.',{'path':PATH}),
    tool('cfx_analyze_profiler_trace','Summarize a developer-captured Chrome Trace JSON file: duration-heavy labels, frequencies and caveats.',{'path':string('Workspace-relative .json or .trace file'),'limit':{'type':'integer','minimum':1,'maximum':50}},['path']),
    tool('cfx_server_health','Read bounded loopback server HTTP health, response latency, client counts and advertised resource count without returning convars or identities.',{'port':{'type':'integer','minimum':1024,'maximum':65535}}),
    tool('cfx_server_process_metrics','Sample one FXServer PID CPU, resident memory, threads and uptime; optional psutil required. If multiple processes exist, return candidate PIDs instead of guessing.',{'pid':{'type':'integer','minimum':0,'maximum':2147483647},'interval_ms':{'type':'integer','minimum':100,'maximum':3000}}),
    tool('cfx_resource_timings','Measure per-resource tick mean/p95/max milliseconds from a captured FiveM Chrome Trace (X or B/E); not a live resmon reading.',{'path':string('Workspace-relative profiler .json or .trace file'),'side':{'type':'string','enum':['server','client']},'limit':{'type':'integer','minimum':1,'maximum':100}},['path']),
    tool('cfx_compare_resource_timings','Compare two captured resource profiles using frame-normalized timing where available; flag missing resources without treating them as improvements.',{'baseline_path':string('Workspace-relative baseline trace'),'candidate_path':string('Workspace-relative candidate trace'),'side':{'type':'string','enum':['server','client']},'limit':{'type':'integer','minimum':1,'maximum':100}},['baseline_path','candidate_path']),
    tool('cfx_server_stability_log','Summarize hitches, per-resource script error counts, missing dependencies and repeated starts from a bounded local log tail. Never returns raw logs or player identities.',{'path':string('Workspace-relative .log or .txt file'),'lines':{'type':'integer','minimum':1,'maximum':50000}},['path']),
    tool('cfx_performance_capture_plan','Generate fixed profiler capture instructions for a server or client. Does not execute console commands or grant permissions.',{'frames':{'type':'integer','minimum':100,'maximum':10000},'filename':string('Simple .json basename without paths'),'side':{'type':'string','enum':['server','client']}}),
    tool('cfx_lua_ast_status','Identify whether the optional tree-sitter-lua grammar is installed for AST-backed Lua analysis.'),
    tool('cfx_lua_ast_index','Parse FiveM project Lua source with a real tree-sitter AST, locating static calls and syntax errors.',{'path':PATH}),
    tool('cfx_lua_ast_network_review','Identify AST-confirmed server network event registrations needing human security review.',{'path':PATH}),
    tool('cfx_bridge_recent','Read sanitized resource-only messages previously received by the optional local development bridge.',{'limit':{'type':'integer','minimum':1,'maximum':200},'resource':string('Optional exact resource name')}),
    tool('cfx_bridge_setup','Read local-only bridge configuration requirements and security limitations.'),
    tool('cfx_control_status','Read development resource-control policy, approved proposals and observed results; no live admin commands.',{'request_id':string('Optional request ID; empty means summary.')}),
    tool('cfx_control_propose','PROPOSE a named-resource lifecycle action, not execute it. Human must approve from an interactive local terminal.',{'action':{'type':'string','enum':['ensure','restart','stop']},'resource':string('Exact allowlisted development resource name'),'reason':string('Short justification, single line')},['action','resource','reason'],False),
    tool('cfx_control_result','Read status of a specific dev-server action proposal; a reported resource state is not test success.',{'request_id':string('24-character proposal ID')},['request_id']),
    tool('cfx_game_type_text','Type bounded Unicode text only into focused FiveM; content never echoed.',{'text':string('1..120 printable characters, no control characters')},['text'],False),
    tool('cfx_game_screenshot','Capture foreground FiveM window rectangle as local PNG; Pillow is optional and required.',{},[],False),
    tool('cfx_game_input_status','Report launch-independent input approval and whether FiveM is foreground.'),
    tool('cfx_game_press_key','Press one allowlisted game key for a bounded duration while FiveM is foreground.',{'key':{'type':'string','enum':['w','a','s','d','space','shift','ctrl','e','f','escape','enter','tab','i','m','f1','f2','f8']},'duration_ms':{'type':'integer','minimum':20,'maximum':2000}},['key'],False),
    tool('cfx_game_click','Click the current mouse cursor in the foreground FiveM game window.',{'button':{'type':'string','enum':['left','right']}},[],False),
    tool('cfx_game_mouse_move','Move mouse relatively in the foreground FiveM game.',{'dx':{'type':'integer','minimum':-500,'maximum':500},'dy':{'type':'integer','minimum':-500,'maximum':500}},['dx','dy'],False),
    tool('cfx_game_scroll','Scroll inside foreground FiveM.',{'steps':{'type':'integer','minimum':-3,'maximum':3}},['steps'],False),
    tool('cfx_fxserver_status','Discover local FXServer/txAdmin targets, report readiness and approval. Optional verify_txadmin logs into the selected loopback panel once and checks its saved profile without starting or changing the game server.',{'port':{'type':'integer','minimum':1024,'maximum':65535},'verify_txadmin':{'type':'boolean'}}),
    tool('cfx_fxserver_start','Start the approved selected local server using its direct or native txAdmin plan. Managed mode verifies panel identity and never falls back to direct startup. Native managed mutation is disabled pending independent security review.',{'port':{'type':'integer','minimum':1024,'maximum':65535}},[],False),
    tool('cfx_dev_start_and_join','Use the selected direct or native txAdmin startup plan, verify readiness, then request the separately approved FiveM launch. Managed mode authenticates and verifies the selected profile even for an existing server; managed mutation is disabled pending independent security review.',{'port':{'type':'integer','minimum':1024,'maximum':65535}},[],False),
    tool('cfx_fivem_launch_preview','Preview a Windows FiveM launch targeting loopback FXServer only; does not start the game.',{'port':{'type':'integer','minimum':1024,'maximum':65535}}),
    tool('cfx_fivem_launch_local','Launch FiveM with +connect 127.0.0.1:port, only during a human-armed live session. Does not imply a successful join.',{'port':{'type':'integer','minimum':1024,'maximum':65535}},[],False),
    tool('cfx_live_status','Check whether explicit full-control session is armed and FXServer is polling, with recent request outcomes.',{'request_id':string('Optional request ID'),'limit':{'type':'integer','minimum':1,'maximum':50}}),
    tool('cfx_live_run','Perform high-privilege FiveM FULL-mode FXServer console/Lua or authorized test-client Lua and actions; requires human arming.',{'kind':{'type':'string','enum':['server_info','server_resources','server_players','server_command','server_lua','client_lua','client_action']},'payload_json':string('JSON object: command, code, action or {}'),'target':{'type':'integer','minimum':0,'maximum':2048}},['kind'],False),
    tool('cfx_live_result','Read execution outcome of a specific FiveM live request; response is not proof of correct game behavior.',{'id':string('32-char request ID')},['id']),
    tool('cfx_live_log','Read bounded local FiveM client/server log tail while Full Control is armed; log may include private operational data.',{'channel':{'type':'string','enum':['server','client']},'lines':{'type':'integer','minimum':1,'maximum':200},'contains':string('Optional substring filter')}),
]
CALLS={
    'cfx_scan_project':lambda a:core.list_resources(a.get('path','.')),
    'cfx_detect_framework':lambda a:core.detect_framework(a.get('path','.')),
    'cfx_validate_manifest':lambda a:core.validate_manifest(a['path']),
    'cfx_audit_security':lambda a:core.security_audit(a.get('path','.')),
    'cfx_audit_nui':lambda a:core.nui_audit(a.get('path','.')),
    'cfx_resource_preview':lambda a:core.resource_preview(a['name'],a.get('framework','standalone'),a.get('with_nui',False)),
    'cfx_scaffold_resource':lambda a:core.scaffold_resource(a['name'],a.get('framework','standalone'),a.get('with_nui',False),a.get('destination','.')),
    'cfx_reference_links':lambda a:core.reference_links(a.get('topic','')),
    'cfx_native_status':lambda a:natives.index_status(),
    'cfx_sync_natives':lambda a:natives.sync_natives(),
    'cfx_search_natives':lambda a:natives.find_natives(a.get('query',''),a.get('source','all'),a.get('namespace',''),a.get('apiset',''),a.get('limit',15)),
    'cfx_native_detail':lambda a:natives.native_detail(a['name_or_hash'],a.get('source','all')),
    'cfx_native_namespaces':lambda a:natives.native_namespaces(a.get('source','all')),
    'cfx_search_events':lambda a:events.search_events(a.get('query',''),a.get('group',''),a.get('side',''),a.get('limit',25)),
    'cfx_event_detail':lambda a:events.event_detail(a['name']),
    'cfx_event_groups':lambda a:events.event_groups(),
    'cfx_project_events':lambda a:inspection.project_events(a.get('path','.')),
    'cfx_find_exports':lambda a:inspection.find_exports(a.get('path','.')),
    'cfx_find_commands':lambda a:inspection.find_commands(a.get('path','.')),
    'cfx_dependency_graph':lambda a:inspection.dependency_graph(a.get('path','.')),
    'cfx_check_server_cfg':lambda a:inspection.check_server_cfg(a.get('path','server.cfg')),
    'cfx_audit_performance':lambda a:inspection.audit_performance(a.get('path','.')),
    'cfx_audit_sql':lambda a:inspection.audit_sql(a.get('path','.')),
    'cfx_list_snippets':lambda a:inspection.list_assets('snippets',a.get('query',''),a.get('limit',100)),
    'cfx_preview_snippet':lambda a:inspection.preview_asset('snippets',a['name']),
    'cfx_list_templates':lambda a:inspection.list_assets('templates',a.get('query',''),a.get('limit',100)),
    'cfx_preview_template':lambda a:inspection.preview_asset('templates',a['name']),
    'cfx_animation_status':lambda a:animations.status(),
    'cfx_sync_animations':lambda a:animations.sync_animations(),
    'cfx_search_animation_dicts':lambda a:animations.search_dictionaries(a.get('query',''),a.get('offset',0),a.get('limit',25)),
    'cfx_search_animation_clips':lambda a:animations.search_clips(a['query'],a.get('dictionary',''),a.get('offset',0),a.get('limit',25)),
    'cfx_animation_dict_detail':lambda a:animations.dictionary_details(a['dictionary'],a.get('offset',0),a.get('limit',50)),
    'cfx_validate_animation_pair':lambda a:animations.validate_pair(a['dictionary'],a['clip']),
    'cfx_generate_animation_lua':lambda a:animations.generate_lua(a['dictionary'],a['clip'],a.get('flag',49),a.get('duration',-1),a.get('timeout_ms',5000)),
    'cfx_animation_prefixes':lambda a:animations.prefix_counts(a.get('limit',50)),
    'cfx_asset_catalog_status':lambda a:catalogs.status(),
    'cfx_sync_asset_catalog':lambda a:catalogs.sync(a['catalog']),
    'cfx_search_asset_catalog':lambda a:catalogs.search(a['catalog'],a.get('query',''),a.get('offset',0),a.get('limit',25),a.get('search_clips',False)),
    'cfx_validate_asset_pair':lambda a:catalogs.validate_pair(a['catalog'],a['dictionary'],a['clip']),
    'cfx_asset_lua_example':lambda a:catalogs.lua_example(a['catalog'],a['dictionary'],a['clip']),
    'cfx_workspace_index':lambda a:intelligence.workspace_index(a.get('path','.')),
    'cfx_trace_event':lambda a:intelligence.event_flow(a['name'],a.get('path','.')),
    'cfx_authority_review':lambda a:intelligence.authority_review(a.get('path','.')),
    'cfx_manifest_asset_report':lambda a:intelligence.manifest_asset_report(a.get('path','.')),
    'cfx_analyze_profiler_trace':lambda a:profiler.summarize_trace(a['path'],a.get('limit',20)),
    'cfx_server_health':lambda a:performance.server_health(a.get('port',30120)),
    'cfx_server_process_metrics':lambda a:performance.process_metrics(a.get('pid',0),a.get('interval_ms',1000)),
    'cfx_resource_timings':lambda a:resourceprofile.resource_timings(a['path'],a.get('side','server'),a.get('limit',20)),
    'cfx_compare_resource_timings':lambda a:resourceprofile.compare_timings(a['baseline_path'],a['candidate_path'],a.get('side','server'),a.get('limit',20)),
    'cfx_server_stability_log':lambda a:performance.stability_log(a['path'],a.get('lines',10000)),
    'cfx_performance_capture_plan':lambda a:performance.capture_plan(a.get('frames',500),a.get('filename','performance-profile.json'),a.get('side','server')),
    'cfx_lua_ast_status':lambda a:ast_analysis.available(),
    'cfx_lua_ast_index':lambda a:ast_analysis.analyze_project(a.get('path','.')),
    'cfx_lua_ast_network_review':lambda a:ast_analysis.audit_network_handlers(a.get('path','.')),
    'cfx_bridge_recent':lambda a:devbridge.read_events(a.get('limit',50),a.get('resource','')),
    'cfx_bridge_setup':lambda a:devbridge.setup_status(),
    'cfx_control_status':lambda a:controlbridge.status(a.get('request_id') or None),
    'cfx_control_propose':lambda a:controlbridge.propose(a['action'],a['resource'],a['reason']),
    'cfx_control_result':lambda a:controlbridge.status(a['request_id']),
    'cfx_game_type_text':lambda a:gameinput.type_text(a['text']),
    'cfx_game_screenshot':lambda a:gameinput.screenshot(),
    'cfx_game_input_status':lambda a:gameinput.status(),
    'cfx_game_press_key':lambda a:gameinput.press(a['key'],a.get('duration_ms',80)),
    'cfx_game_click':lambda a:gameinput.click(a.get('button','left')),
    'cfx_game_mouse_move':lambda a:gameinput.move(a['dx'],a['dy']),
    'cfx_game_scroll':lambda a:gameinput.scroll(a['steps']),
    'cfx_fxserver_status':lambda a:fxserverlaunch.status(a.get('port',30120),a.get('verify_txadmin',False)),
    'cfx_fxserver_start':lambda a:fxserverlaunch.start(a.get('port',30120)),
    'cfx_dev_start_and_join':lambda a:fxserverlaunch.start_and_connect(a.get('port',30120)),
    'cfx_fivem_launch_preview':lambda a:clientlaunch.preview(a.get('port',30120)),
    'cfx_fivem_launch_local':lambda a:clientlaunch.launch(a.get('port',30120)),
    'cfx_live_log':lambda a:livecontrol.tail_log(a.get('channel','server'),a.get('lines',60),a.get('contains','')),
    'cfx_live_status':lambda a:livecontrol.status(a.get('request_id') or None,a.get('limit',15)),
    'cfx_live_run':lambda a:livecontrol.submit(a['kind'],a.get('payload_json','{}'),a.get('target',0)),
    'cfx_live_result':lambda a:livecontrol.status(a['id']),
}

# High-risk action annotation for explicit full-control mode.
for _entry in TOOLS:
    if _entry['name']=='cfx_live_run':
        _entry['annotations']['destructiveHint']=True
        _entry['annotations']['idempotentHint']=False

def validate_arguments(name,args):
    """Reject undeclared inputs and basic schema/type errors before tool dispatch."""
    selected=next((t for t in TOOLS if t['name']==name),None)
    if selected is None:raise KeyError(f"Unknown tool: {name}")
    schema=selected['inputSchema']
    for required in schema.get('required',()):
        if required not in args:raise ValueError(f"Missing required argument: {required}")
    properties=schema.get('properties',{})
    for key,value in args.items():
        if key not in properties:raise ValueError(f"Unexpected argument: {key}")
        spec=properties[key]
        kind=spec.get('type')
        if kind=='string' and not isinstance(value,str):raise ValueError(f"{key} must be a string")
        if kind=='boolean' and not isinstance(value,bool):raise ValueError(f"{key} must be boolean")
        if kind=='integer' and (not isinstance(value,int) or isinstance(value,bool)):raise ValueError(f"{key} must be integer")
        if kind=='integer' and (value<spec.get('minimum',-10**20) or value>spec.get('maximum',10**20)):
            raise ValueError(f"{key} out of allowed range")
        if 'enum' in spec and value not in spec['enum']:raise ValueError(f"{key} must be one of {spec['enum']}")
    return args

def handle(message, allowed_tools=None):
    method=message.get('method'); params=message.get('params') or {}
    if method=='initialize':
        version=params.get('protocolVersion','2025-11-25')
        return {'protocolVersion':version if version in PROTOCOLS else '2025-11-25',
                'capabilities':{'tools':{}},'serverInfo':{'name':'cfx-devkit','version':VERSION}}
    if method=='ping': return {}
    if method=='tools/list':return {'tools':[entry for entry in TOOLS if allowed_tools is None or entry['name'] in allowed_tools]}
    if method=='tools/call':
        name=params.get('name'); args=params.get('arguments') or {}
        if name not in CALLS or (allowed_tools is not None and name not in allowed_tools): raise KeyError(f'Unknown tool: {name}')
        if not isinstance(args,dict): raise ValueError('Tool arguments must be an object')
        try:
            result=CALLS[name](validate_arguments(name,args))
            return {'content':[{'type':'text','text':json.dumps(result,ensure_ascii=False)}], 'isError':False}
        except (ValueError, KeyError, OSError) as e:
            return {'content':[{'type':'text','text':f'{type(e).__name__}: {e}'}],'isError':True}
    raise KeyError(f'Unknown method: {method}')

def main(allowed_tools=None):
    # Explicit UTF-8 on every host, including Windows with cp1252 stdio pipes.
    # ASCII-safe JSON is an additional safeguard for MCP tool descriptions.
    if hasattr(sys.stdout,'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8',errors='backslashreplace')
    if hasattr(sys.stderr,'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8',errors='backslashreplace')
    for line in sys.stdin:
        if not line.strip(): continue
        try:
            req=json.loads(line)
            if not isinstance(req,dict): raise ValueError('JSON-RPC message must be an object')
            if 'id' not in req: continue
            if req.get('jsonrpc')!='2.0': raise ValueError('Expected jsonrpc=2.0')
            try: result=handle(req, allowed_tools)
            except KeyError as e:
                reply={'jsonrpc':'2.0','id':req.get('id'),'error':{'code':-32601,'message':str(e)}}
            except Exception as e:
                reply={'jsonrpc':'2.0','id':req.get('id'),'error':{'code':-32603,'message':str(e)}}
            else: reply={'jsonrpc':'2.0','id':req['id'],'result':result}
        except (ValueError, TypeError, json.JSONDecodeError) as e:
            reply={'jsonrpc':'2.0','id':None,'error':{'code':-32700,'message':str(e)}}
        sys.stdout.write(json.dumps(reply,ensure_ascii=True,separators=(',',':'))+'\n');sys.stdout.flush()

if __name__=='__main__':main()
