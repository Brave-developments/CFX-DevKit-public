"""Opt-in local FXServer process launcher, distinct from resource lifecycle and RCON.

Discover targets within the workspace or use explicit absolute path overrides.
Startup still requires a short-lived local-terminal permission for that target.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import secrets
from urllib.request import build_opener, ProxyHandler
from . import clientlaunch, serverdiscovery, core

MAX_INFO_BYTES = 1_000_000
STARTUP_POLLS = 60
JOIN_STABLE_SECONDS = 10
_started_process = None
_started_process_role = 'game-server'
DIRECT_LAUNCH_WARNING = ('Direct FXServer +exec launch does not apply txAdmin runtime settings. '
                        'A discovered txAdmin profile supplies paths only; OneSync and other '
                        'txAdmin-supplied settings may be absent. Use txAdmin for an equivalent '
                        'managed startup; this tool does not verify OneSync configuration.')

def urlopen(url,timeout):
    """Readiness requests stay local even when proxy variables are configured."""
    from .performance import NoRedirect
    return build_opener(ProxyHandler({}),NoRedirect()).open(url,timeout=timeout)

def _grant_path():
    from .natives import _cache_dir
    return _cache_dir()/"fxserver-launch-grant.json"

def configuration():
    """Report automatic discovery or the validated explicit override, without writes."""
    if not os.environ.get('CFX_FXSERVER_EXE') and not os.environ.get('CFX_FXSERVER_CFG'):
        result=serverdiscovery.discover()
        if result.get('selected'):
            s=result['selected']
            s['launch_plan']=_launch_plan(s['executable'],s['config'],s.get('profile_config'))
            s['target_id']=s['launch_plan']['target_id']
        return result
    exe=Path(os.environ.get("CFX_FXSERVER_EXE","")).expanduser()
    cfg=Path(os.environ.get("CFX_FXSERVER_CFG","")).expanduser()
    if not exe.is_absolute() or not cfg.is_absolute() or not exe.is_file() or not cfg.is_file():
        raise ValueError("Set CFX_FXSERVER_EXE and CFX_FXSERVER_CFG to existing absolute paths")
    if exe.name.casefold()!="fxserver.exe" or cfg.name.casefold()!="server.cfg":
        raise ValueError("Only FXServer.exe and server.cfg are accepted")
    exe,cfg=exe.resolve(),cfg.resolve()
    selected={'executable':str(exe),'config':str(cfg),'data_directory':str(cfg.parent),
              'source':'explicit-config','target_id':serverdiscovery.target_id(exe,cfg)}
    selected['launch_plan']=_launch_plan(exe,cfg)
    selected['target_id']=selected['launch_plan']['target_id']
    return {'state':'configured','selected':selected,'candidates':[selected],'truncated':False}

def _launch_plan(exe,cfg,profile=None):
    from . import txadmin
    if (not profile and not os.environ.get('CFX_FXSERVER_EXE') and
        not os.environ.get('CFX_FXSERVER_CFG') and
        os.environ.get('CFX_FXSERVER_MODE','auto')=='auto'):
        selected=serverdiscovery.discover().get('selected') or {}
        if selected.get('config')==str(cfg) and selected.get('executable')==str(exe):
            profile=selected.get('profile_config')
    return txadmin.plan(exe,cfg,profile)

def _managed_requested():
    if os.environ.get('CFX_FXSERVER_MODE')=='direct':return False
    if os.environ.get('CFX_FXSERVER_MODE')=='txadmin' or os.environ.get('CFX_TXADMIN_PROFILE'):return True
    if not os.environ.get('CFX_FXSERVER_EXE') and not os.environ.get('CFX_FXSERVER_CFG'):
        return (serverdiscovery.discover().get('selected') or {}).get('source')=='txadmin-profile'
    return False

def _config():
    if sys.platform!="win32":
        raise ValueError("Local FXServer launch is available on Windows only")
    result=configuration()
    selected=result['selected']
    if not selected:
        raise ValueError('FXServer discovery: '+result['state']+'. Inspect cfx_fxserver_status; '
                         'select CFX_FXSERVER_EXE and CFX_FXSERVER_CFG if multiple targets exist, '
                         'or set CFX_WORKSPACE_ROOT to your server installation folder.')
    return Path(selected['executable']),Path(selected['config'])

def permission():
    try:
        value=json.loads(_grant_path().read_text(encoding="utf-8"))
        expiry=int(value["expires_at"])
        port=clientlaunch._port(value["port"])
        target=value.get('target_id')
        if not isinstance(target,str) or len(target)!=64:
            raise ValueError('Re-arm legacy port-only authorization for the selected server')
    except (OSError,ValueError,TypeError,KeyError):
        return {"approved":False,"expires_at":None,"port":None}
    return {"approved":expiry>int(time.time()),"expires_at":expiry,"port":port,'target_id':target}

def arm(port=30120,minutes=15):
    clientlaunch._port(port)
    if not isinstance(minutes,int) or isinstance(minutes,bool) or not 1<=minutes<=60:
        raise ValueError("Minutes must be 1..60")
    if not sys.stdin.isatty():
        raise ValueError("FXServer launch permission requires an interactive terminal")
    exe,cfg=_config()
    plan=_launch_plan(exe,cfg)
    phrase="ALLOW LOCAL FXSERVER"
    if input(f"Permit {plan['mode']} startup of {exe} with {cfg} for localhost port {port} for {minutes} minutes? Type '{phrase}': ")!=phrase:
        raise ValueError("Permission refused")
    dest=_grant_path();dest.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=".fxserver-",dir=str(dest.parent))
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as stream:
            json.dump({"expires_at":int(time.time())+minutes*60,"port":port,
                       'target_id':plan['target_id']},stream)
        os.replace(tmp,dest)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    return permission()

def disarm():
    _grant_path().unlink(missing_ok=True)
    return {"approved":False}

def _server_info(port=30120):
    clientlaunch._port(port)
    try:
        with urlopen(f"http://127.0.0.1:{port}/info.json",timeout=1.5) as response:
            # Resource names and server metadata routinely exceed 4 KiB. A
            # truncated JSON document incorrectly marks a live server stopped.
            raw=response.read(MAX_INFO_BYTES + 1)
            if response.status!=200:return None
            if len(raw)>MAX_INFO_BYTES:return None
            info=json.loads(raw)
            return info if isinstance(info,dict) and isinstance(info.get("vars"),dict) else None
    except (OSError,ValueError,TypeError):
        return None

def ready(port=30120):
    """Endpoint reachability only; never proof that startup/resources are complete."""
    return _server_info(port) is not None

def _join_readiness(port,deadline=None):
    try:
        minimum=int(os.environ.get('CFX_READY_RESOURCE_COUNT','1'))
    except ValueError:
        raise ValueError('CFX_READY_RESOURCE_COUNT must be an integer from 1 to 10000') from None
    if not 1<=minimum<=10000:
        raise ValueError('CFX_READY_RESOURCE_COUNT must be 1..10000')
    previous=None
    stable_since=None
    count=0
    for attempt in range(STARTUP_POLLS+1):
        info=_server_info(port)
        resources=info.get('resources') if info else None
        inventory=tuple(sorted(set(resources))) if isinstance(resources,list) and all(isinstance(r,str) for r in resources) else None
        now=time.monotonic()
        count=len(inventory) if inventory else 0
        if inventory is None or count<minimum:
            previous=None;stable_since=None
        elif inventory!=previous:
            previous=inventory;stable_since=now
        elif stable_since is not None and now-stable_since>=JOIN_STABLE_SECONDS:
            return {'settled':True,'advertised_resource_count':count,'minimum_resource_count':minimum,
                    'stable_seconds':JOIN_STABLE_SECONDS,'resource_health_verified':False}
        if deadline is not None and now>=deadline:break
        if attempt<STARTUP_POLLS:time.sleep(2)
    return {'settled':False,'advertised_resource_count':count,'minimum_resource_count':minimum,
            'stable_seconds':0,'resource_health_verified':False}

def status(port=30120,verify_txadmin=False):
    if not isinstance(verify_txadmin,bool):raise ValueError('verify_txadmin must be boolean')
    grant=permission()
    try:
        target=configuration()
    except ValueError as error:
        target={'state':'invalid-configuration','selected':None,'candidates':[],
                'note':str(error)}
    selected=target.get('selected') or {}
    plan=selected.get('launch_plan') or {'mode':'invalid-configuration' if target['state']=='invalid-configuration' else 'direct-server-cfg'}
    managed=plan['mode']=='txadmin'
    panel=None
    if managed:
        from . import txadmin
        session=txadmin.Session(plan)
        panel={'url':plan['url'],'reachable':session.reachable(),
               'credentials_configured':txadmin.credentials_configured(),
               'authenticated':False,'profile_verified':False,'control_reviewed':txadmin.CONTROL_REVIEWED}
        if verify_txadmin:
            if not panel['reachable']:raise ValueError('Selected txAdmin panel is unreachable; no login attempted')
            panel.update(session.verify(Path(selected['config'])))
    endpoint_ready=ready(port)
    return {"port":clientlaunch._port(port),"server_ready":endpoint_ready,'http_ready':endpoint_ready,
            'join_readiness':'not-evaluated','resource_health_verified':False,
            'launch_mode':plan['mode'],'txadmin_runtime_settings_applied':False,
            'txadmin':panel,'warnings':[DIRECT_LAUNCH_WARNING] if plan['mode']=='direct-server-cfg' else [],
            "approved":bool(grant["approved"] and grant["port"]==port and
                            grant.get('target_id')==selected.get('target_id')),
            'discovery':target,
            "note":"server_ready/http_ready mean endpoint reachability only. Join additionally waits for a stable resource inventory; neither proves script health or player spawn."}

def start(port=30120):
    global _started_process, _started_process_role
    clientlaunch._port(port)
    if _managed_requested():return _start_managed(port)
    if ready(port):
        # A responding port must not bypass an ambiguous local selection.
        _config()
        return {"started":False,"already_ready":True,"port":port}
    grant=permission()
    if not grant["approved"] or grant["port"]!=port:
        raise ValueError("Approve this port with cfx-devkit fxserver-arm from a local interactive terminal")
    exe,cfg=_config()
    if grant.get('target_id')!=_launch_plan(exe,cfg)['target_id']:
        raise ValueError('Selected FXServer target changed; re-arm it with cfx-devkit fxserver-arm')
    log_dir=core.safe_path('.cfx-devkit/logs')
    log_dir.mkdir(parents=True,exist_ok=True)
    log_file=log_dir/('fxserver-'+str(int(time.time()))+'-'+secrets.token_hex(6)+'.log')
    fd=os.open(log_file,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'wb') as log:
        process=subprocess.Popen([str(exe),"+exec",str(cfg)],cwd=str(cfg.parent),
                                 shell=False,stdin=subprocess.DEVNULL,
                                 stdout=log,stderr=subprocess.STDOUT,
                                 creationflags=getattr(subprocess,"CREATE_NEW_PROCESS_GROUP",0))
    _started_process=process
    _started_process_role='game-server'
    return {"started":True,"pid":process.pid,"port":port,"server_ready":False,
            'launch_mode':'direct-server-cfg','txadmin_runtime_settings_applied':False,
            'warnings':[DIRECT_LAUNCH_WARNING],
            'log_path':log_file.relative_to(core.workspace_root()).as_posix(),'stderr_combined':True,
            "note":"FXServer process started; call cfx_fxserver_status and wait for info.json before launching FiveM."}

def _start_managed(port):
    """Start the manager without +exec; only txAdmin starts its game worker."""
    global _started_process, _started_process_role
    from . import txadmin
    exe,cfg=_config()
    plan=_launch_plan(exe,cfg)
    session=txadmin.Session(plan)
    game_ready=ready(port)
    if game_ready:
        session.verify(cfg)
        return {'started':False,'already_ready':True,'port':port,'launch_mode':'txadmin',
                'authenticated':True,'profile_verified':True,'txadmin_runtime_settings_applied':True}
    if not txadmin.CONTROL_REVIEWED:
        raise ValueError('Native txAdmin startup is pending independent security review; no process or control request started')
    grant=permission()
    if not (grant['approved'] and grant['port']==port and grant.get('target_id')==plan['target_id']):
        raise ValueError('Approve this txAdmin target with cfx-devkit fxserver-arm')
    if not txadmin.credentials_configured():
        raise ValueError('Set TXADMIN_USERNAME and TXADMIN_PASSWORD in the local MCP environment')
    manager=None
    if not session.reachable():
        log_dir=core.safe_path('.cfx-devkit/logs');log_dir.mkdir(parents=True,exist_ok=True)
        log_path=log_dir/('txadmin-'+secrets.token_hex(12)+'.log')
        with os.fdopen(os.open(log_path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600),'wb') as log:
            process=subprocess.Popen([str(exe),'+set','serverProfile',plan['profile_name']],
                cwd=str(exe.parent),env=txadmin.manager_environment(plan),shell=False,
                stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0))
        _started_process=process
        _started_process_role='txadmin-manager'
        manager={'pid':process.pid,'log_path':log_path.relative_to(core.workspace_root()).as_posix()}
        for _ in range(30):
            if session.reachable():break
            if process.poll() is not None:raise ValueError('txAdmin manager exited; inspect the startup log')
            time.sleep(1)
        else:raise ValueError('txAdmin panel did not become reachable; no direct-start fallback')
    session.verify(cfg)
    # Revalidate the on-disk profile and target immediately before mutation.
    if _launch_plan(exe,cfg)!=plan:raise ValueError('txAdmin target changed during startup; re-arm it')
    if ready(port):
        return {'started':bool(manager),'already_ready':True,'port':port,'launch_mode':'txadmin',
                'authenticated':True,'profile_verified':True,'manager':manager,
                'txadmin_runtime_settings_applied':True}
    grant=permission()
    if not (grant['approved'] and grant['port']==port and grant.get('target_id')==plan['target_id']):
        raise ValueError('txAdmin startup approval expired or changed; no control request sent')
    result=session.start()
    result.update(started=True,port=port,manager=manager,server_ready=False,
                  note='txAdmin accepted startup; game readiness and join remain unverified.')
    return result

def start_and_connect(port=30120):
    clientlaunch._port(port)
    deadline=time.monotonic()+STARTUP_POLLS*2
    start_result=None
    if _managed_requested() or not ready(port):
        start_result=start(port)
        for _ in range(STARTUP_POLLS):
            if ready(port):break
            if time.monotonic()>=deadline:break
            time.sleep(2)
        if not ready(port):
            return {"server_ready":False,"fivem_launch_requested":False,
                    "note":"FXServer did not become ready within the bounded startup window; inspect server logs.",
                    "server_start":start_result}
    # Readiness confirms a server endpoint, not which discovered profile owns it.
    _config()
    if not clientlaunch.permission()["approved"] or clientlaunch.permission()["port"]!=port:
        return {"server_ready":True,"fivem_launch_requested":False,'server_start':start_result,
                "note":"Grant separate FiveM permission with client-launch-arm; server is ready."}
    readiness=_join_readiness(port,deadline)
    if not readiness['settled']:
        return {'server_ready':True,'fivem_launch_requested':False,'server_start':start_result,
                'join_readiness':readiness,'note':'HTTP responds but resource startup has not settled or the configured minimum has not been reached. Inspect the startup log; FiveM was not launched.'}
    result=clientlaunch.launch(port)
    return {"server_ready":True,"fivem_launch_requested":True,"client":result,
            'server_start':start_result,'join_readiness':readiness,
            "joined":False,"note":"FiveM protocol open requested; joined-state not verified."}

def connect(port=30120,minutes=15):
    """Human CLI workflow: resolve target, obtain missing approvals, then connect.

    Not an MCP arm method. Existing grants are reused; missing grants still
    require the original interactive terminal prompts.
    """
    clientlaunch._port(port)
    if not isinstance(minutes,int) or isinstance(minutes,bool) or not 1<=minutes<=60:
        raise ValueError('Minutes must be 1..60')
    exe,cfg=_config()
    clientlaunch._client_path()
    if not ready(port):
        grant=permission()
        if not (grant['approved'] and grant['port']==port and
                grant.get('target_id')==_launch_plan(exe,cfg)['target_id']):
            arm(port,minutes)
    grant=clientlaunch.permission()
    if not (grant['approved'] and grant['port']==port):
        clientlaunch.arm(port,minutes)
    return start_and_connect(port)
