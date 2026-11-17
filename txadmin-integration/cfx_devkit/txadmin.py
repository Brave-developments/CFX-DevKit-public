"""Local txAdmin adapter: fixed authentication, identity and start routes only.

Control remains disabled pending the independent review required by AGENTS.md.
No stop/restart, console execution, profile edits, raw responses or credentials
are exposed through MCP. The authenticated session lives only in memory.
"""
import hashlib
import json
import os
from pathlib import Path
import re
from http.cookiejar import CookieJar
from urllib.parse import urlsplit
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler, HTTPCookieProcessor
from . import serverdiscovery
from .performance import NoRedirect

CONTROL_REVIEWED = False
MAX_RESPONSE_BYTES = 1_000_000


def local_url(value):
    try:
        u=urlsplit(value)
        if (u.scheme!='http' or u.hostname not in {'127.0.0.1','localhost','::1'} or
            u.username is not None or u.password is not None or u.path not in ('','/') or
            u.query or u.fragment or not u.port or not 1024<=u.port<=65535):
            raise ValueError()
    except (ValueError,TypeError):
        raise ValueError('TXADMIN_URL must be an HTTP loopback origin with an explicit port') from None
    # Normalize localhost to a literal address: no DNS/proxy credential routing.
    host='[::1]' if u.hostname=='::1' else '127.0.0.1'
    return f'http://{host}:{u.port}'


def plan(exe,cfg,profile=None):
    mode=os.environ.get('CFX_FXSERVER_MODE','auto')
    if mode not in {'auto','direct','txadmin'}:
        raise ValueError('CFX_FXSERVER_MODE must be auto, direct or txadmin')
    profile=os.environ.get('CFX_TXADMIN_PROFILE') or profile
    managed=mode=='txadmin' or mode=='auto' and bool(profile)
    if not managed:
        return {'mode':'direct-server-cfg','target_id':serverdiscovery.target_id(exe,cfg)}
    if not profile:
        raise ValueError('Managed startup needs CFX_TXADMIN_PROFILE pointing to the saved profile config.json')
    p=Path(profile).expanduser()
    if not p.is_absolute() or p.name!='config.json' or not p.is_file():
        raise ValueError('CFX_TXADMIN_PROFILE must name an existing absolute profile config.json')
    p=p.resolve()
    # The settings API identifies the txData root and server.cfg, not a legacy
    # profile name. Require a dedicated root so two profiles sharing a config
    # cannot be mistaken for one another by a panel on the wrong port.
    for index,child in enumerate(p.parent.parent.iterdir()):
        if index>=1000:
            raise ValueError('txAdmin data folder enumeration limit reached')
        candidate=child/'config.json'
        if child.is_dir() and candidate.is_file() and candidate.resolve()!=p:
            raise ValueError('Native txAdmin mode requires a dedicated data folder with one profile')
    name=p.parent.name
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',name):
        raise ValueError('Unsupported txAdmin profile name')
    try:
        with p.open('rb') as stream: raw=stream.read(MAX_RESPONSE_BYTES+1)
        if len(raw)>MAX_RESPONSE_BYTES: raise ValueError()
        d=json.loads(raw.decode('utf-8-sig'))
        server=d.get('server',d.get('fxRunner',{}))
        base=Path(server.get('dataPath',server.get('serverDataPath','')))
        config=server.get('cfgPath','')
        if not base.is_absolute() or not isinstance(config,str) or not config:
            raise ValueError()
        if (base/config).resolve()!=Path(cfg).resolve():raise ValueError()
    except (OSError,ValueError,TypeError,AttributeError,RecursionError):
        raise ValueError('txAdmin profile does not identify the selected server.cfg') from None
    url=local_url(os.environ.get('TXADMIN_URL',''))
    identity=[serverdiscovery.target_id(exe,cfg),str(p),url,'txadmin']
    return {'mode':'txadmin','profile_config':str(p),'data_path':str(p.parent.parent),
            'profile_name':name,'url':url,
            'target_id':hashlib.sha256(json.dumps(identity).encode()).hexdigest()}


def credentials_configured():
    return bool(os.environ.get('TXADMIN_USERNAME') and os.environ.get('TXADMIN_PASSWORD'))


def manager_environment(p):
    # Never pass agent launch grants, control tokens or panel credentials down
    # to game resources. Inherited provider overrides must not select another
    # profile/port or expand the listener interface.
    allowed={'SYSTEMROOT','WINDIR','PATH','PATHEXT','COMSPEC','TEMP','TMP','USERPROFILE',
             'HOMEDRIVE','HOMEPATH','APPDATA','LOCALAPPDATA','PROGRAMDATA','PROGRAMFILES',
             'PROGRAMFILES(X86)','COMMONPROGRAMFILES','NUMBER_OF_PROCESSORS',
             'PROCESSOR_ARCHITECTURE','OS'}
    env={k:v for k,v in os.environ.items() if k.upper() in allowed}
    env.update(TXHOST_DATA_PATH=p['data_path'],TXHOST_TXA_PORT=str(urlsplit(p['url']).port),
               TXHOST_INTERFACE=urlsplit(p['url']).hostname,TXHOST_GAME_NAME='fivem')
    return env


class Session:
    def __init__(self,p):
        self.plan=p
        self.opener=build_opener(ProxyHandler({}),NoRedirect(),HTTPCookieProcessor(CookieJar()))
        self.csrf=None
        self.verified=False

    def reachable(self):
        try:
            with self.opener.open(self.plan['url']+'/',timeout=2) as response:
                return True
        except HTTPError as error:
            # Login redirects/401/403 still mean a listener exists. Never
            # spawn a second manager just because its root requires login.
            error.close()
            return True
        except (OSError,ValueError):return False

    def _request(self,method,path,body=None):
        if (method,path) not in {('POST','/auth/password'),('GET','/settings/configs'),('POST','/fxserver/controls')}:
            raise ValueError('Unsupported txAdmin route')
        if path=='/fxserver/controls':
            if body!={'action':'start'}:raise ValueError('Only txAdmin server start is supported')
            if not CONTROL_REVIEWED or not self.verified:
                raise ValueError('Reviewed control and verified identity are required')
        headers={'Accept':'application/json'}
        if self.csrf:headers['x-txadmin-csrftoken']=self.csrf
        data=None
        if body is not None:
            headers['Content-Type']='application/json';data=json.dumps(body).encode()
        try:
            with self.opener.open(Request(self.plan['url']+path,data=data,headers=headers,method=method),timeout=5) as response:
                raw=response.read(MAX_RESPONSE_BYTES+1)
                if response.status!=200 or len(raw)>MAX_RESPONSE_BYTES:raise ValueError()
                result=json.loads(raw)
                if not isinstance(result,dict) or result.get('error'):raise ValueError()
                return result
        except (OSError,ValueError,TypeError,RecursionError):
            # Never echo URLs, bodies, exceptions, raw errors, tokens or cookies.
            raise ValueError('txAdmin request failed or returned an incompatible response; no direct-start fallback') from None

    def verify(self,cfg):
        self.verified=False
        self.csrf=None
        if not credentials_configured():
            raise ValueError('Set TXADMIN_USERNAME and TXADMIN_PASSWORD in the local MCP environment')
        login=self._request('POST','/auth/password',{'username':os.environ['TXADMIN_USERNAME'],'password':os.environ['TXADMIN_PASSWORD']})
        token=login.get('csrfToken')
        if not isinstance(token,str) or token in ('','not_set') or len(token)>4096:
            raise ValueError('txAdmin login did not return a valid CSRF token')
        self.csrf=token
        data=self._request('GET','/settings/configs')
        try:
            stored=data['storedConfigs']; server=stored.get('server',stored.get('fxRunner',{}))
            root=Path(data['dataPath'])
            base=Path(server.get('dataPath',server.get('serverDataPath','')))
            relative=server['cfgPath']
            if (not root.is_absolute() or root.resolve()!=Path(self.plan['data_path']).resolve() or
                not base.is_absolute() or not isinstance(relative,str) or
                (base/relative).resolve()!=Path(cfg).resolve()):raise ValueError()
        except (KeyError,ValueError,TypeError,AttributeError):
            raise ValueError('Connected txAdmin panel does not match the selected data folder and server.cfg') from None
        self.verified=True
        return {'authenticated':True,'profile_verified':True}

    def start(self):
        if not CONTROL_REVIEWED:
            raise ValueError('Native txAdmin control is pending independent security review; no start request sent')
        if not self.csrf or not self.verified:raise ValueError('Verify txAdmin identity before requesting startup')
        result=self._request('POST','/fxserver/controls',{'action':'start'})
        if result.get('type')!='success':
            raise ValueError('txAdmin did not accept the start request; inspect its panel. No retry or direct fallback performed')
        return {'start_requested':True,'launch_mode':'txadmin','authenticated':True,'profile_verified':True,
                'txadmin_runtime_settings_applied':True,'joined':False}
