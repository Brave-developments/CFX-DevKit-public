"""Human-approved input only to foreground FiveM windows on Windows.

No generic desktop automation, no background input, no unrestricted scripts.
"""
from __future__ import annotations
import ctypes
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from . import clientlaunch

KEYS={"w":0x11,"a":0x1e,"s":0x1f,"d":0x20,"space":0x39,"shift":0x2a,
      "ctrl":0x1d,"e":0x12,"f":0x21,"escape":0x01,"enter":0x1c,
      "tab":0x0f,"i":0x17,"m":0x32,"f1":0x3b,"f2":0x3c,"f8":0x42}
MOUSE_BUTTONS={"left":(0x0002,0x0004),"right":(0x0008,0x0010)}
INPUT_KEYBOARD=1
INPUT_MOUSE=0
KEYEVENTF_SCANCODE=0x0008
KEYEVENTF_KEYUP=0x0002
MAX_DURATION_MS=2000

def _path():
    from .natives import _cache_dir
    return _cache_dir()/"game-input-grant.json"

def _windows():
    if sys.platform!="win32":raise ValueError("In-game input works only on Windows")

def permission():
    from . import delegation
    if delegation.allows("game-input"):
        return {"approved": True, "expires_at": None, "authorization_mode": "owner-delegated-until-revoked"}
    try:
        data=json.loads(_path().read_text(encoding="utf-8"))
        expires=int(data["expires_at"])
    except (OSError,KeyError,ValueError,TypeError):
        return {"approved":False,"expires_at":None}
    return {"approved":expires>int(time.time()),"expires_at":expires}

def arm(minutes=15):
    _windows()
    if not isinstance(minutes,int) or isinstance(minutes,bool) or not 1<=minutes<=60:
        raise ValueError("Minutes must be 1..60")
    if not sys.stdin.isatty():raise ValueError("Input permission requires a real interactive terminal")
    clientlaunch._client_path()
    phrase="ALLOW FIVEM INPUT"
    if input(f"Permit foreground FiveM keyboard/mouse actions for {minutes} minutes? Type '{phrase}': ")!=phrase:
        raise ValueError("Approval refused")
    p=_path();p.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=".game-input-",dir=str(p.parent))
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            json.dump({"expires_at":int(time.time())+minutes*60},f)
        os.replace(tmp,p)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    return permission()

def disarm():
    from . import delegation
    delegation.revoke("game-input")
    _path().unlink(missing_ok=True)
    return {"approved":False}

def _foreground():
    _windows()
    user=ctypes.windll.user32
    kernel=ctypes.windll.kernel32
    hwnd=user.GetForegroundWindow()
    if not hwnd:raise ValueError("No active window")
    pid=ctypes.c_ulong()
    user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
    PROCESS_QUERY_LIMITED_INFORMATION=0x1000
    handle=kernel.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,False,pid.value)
    if not handle:raise ValueError("Cannot verify foreground process")
    try:
        buf=ctypes.create_unicode_buffer(32768)
        size=ctypes.c_ulong(len(buf))
        kernel.QueryFullProcessImageNameW.argtypes=[ctypes.c_void_p,ctypes.c_ulong,ctypes.c_wchar_p,ctypes.POINTER(ctypes.c_ulong)]
        kernel.QueryFullProcessImageNameW.restype=ctypes.c_int
        if not kernel.QueryFullProcessImageNameW(handle,0,buf,ctypes.byref(size)):
            raise ValueError("Cannot read foreground executable")
        name=Path(buf.value).name.casefold()
        if not (name=="fivem.exe" or name.startswith("fivem_") and name.endswith(".exe")):
            raise ValueError("Foreground window is not FiveM; refusing desktop input")
    finally:
        kernel.CloseHandle(handle)
    return hwnd

def status():
    grant=permission()
    foreground=False
    try:_foreground();foreground=True
    except (ValueError,AttributeError):pass
    return {"approved":grant["approved"],"expires_at":grant["expires_at"],
            "fivem_foreground":foreground,"supported":sys.platform=="win32"}

def _ready():
    if not permission()["approved"]:raise ValueError("Explicit authorization required: run cfx-devkit game-input-arm")
    _foreground()

def _send_scan(scan,up=False):
    # SendInput structures use pointer-sized alignment on both 32-bit and 64-bit Windows.
    class KEYBDINPUT(ctypes.Structure):
        _fields_=[("wVk",ctypes.c_ushort),("wScan",ctypes.c_ushort),
                  ("dwFlags",ctypes.c_ulong),("time",ctypes.c_ulong),
                  ("dwExtraInfo",ctypes.c_void_p)]
    class MOUSEINPUT(ctypes.Structure):
        _fields_=[("dx",ctypes.c_long),("dy",ctypes.c_long),("mouseData",ctypes.c_ulong),
                  ("dwFlags",ctypes.c_ulong),("time",ctypes.c_ulong),("dwExtraInfo",ctypes.c_void_p)]
    class UNION(ctypes.Union):
        _fields_=[("ki",KEYBDINPUT),("mi",MOUSEINPUT)]
    class INPUT(ctypes.Structure):
        _fields_=[("type",ctypes.c_ulong),("data",UNION)]
    entry=INPUT();entry.type=INPUT_KEYBOARD
    entry.data.ki=KEYBDINPUT(0,scan,KEYEVENTF_SCANCODE|(KEYEVENTF_KEYUP if up else 0),0,None)
    if ctypes.windll.user32.SendInput(1,ctypes.byref(entry),ctypes.sizeof(entry))!=1:
        raise ValueError("Windows rejected keyboard input")

def press(key,duration_ms=80):
    if key not in KEYS:raise ValueError("Key is not on approved game-key list")
    if not isinstance(duration_ms,int) or isinstance(duration_ms,bool) or not 20<=duration_ms<=MAX_DURATION_MS:
        raise ValueError("Duration must be between 20 and 2000 milliseconds")
    _ready()
    scan=KEYS[key]
    _send_scan(scan)
    try:time.sleep(duration_ms/1000)
    finally:_send_scan(scan,True)
    return {"sent":True,"key":key,"duration_ms":duration_ms}

def _mouse(flags,dx=0,dy=0,data=0):
    class MOUSEINPUT(ctypes.Structure):
        _fields_=[("dx",ctypes.c_long),("dy",ctypes.c_long),("mouseData",ctypes.c_ulong),
                  ("dwFlags",ctypes.c_ulong),("time",ctypes.c_ulong),("dwExtraInfo",ctypes.c_void_p)]
    class KEYBDINPUT(ctypes.Structure):
        _fields_=[("wVk",ctypes.c_ushort),("wScan",ctypes.c_ushort),("dwFlags",ctypes.c_ulong),
                  ("time",ctypes.c_ulong),("dwExtraInfo",ctypes.c_void_p)]
    class U(ctypes.Union):_fields_=[("mi",MOUSEINPUT),("ki",KEYBDINPUT)]
    class I(ctypes.Structure):_fields_=[("type",ctypes.c_ulong),("data",U)]
    item=I();item.type=INPUT_MOUSE;item.data.mi=MOUSEINPUT(dx,dy,data,flags,0,None)
    if ctypes.windll.user32.SendInput(1,ctypes.byref(item),ctypes.sizeof(item))!=1:
        raise ValueError("Windows rejected mouse input")

def click(button="left"):
    if button not in MOUSE_BUTTONS:raise ValueError("Only left/right mouse buttons are supported")
    _ready()
    down,up=MOUSE_BUTTONS[button]
    _mouse(down)
    try:time.sleep(0.06)
    finally:_mouse(up)
    return {"sent":True,"button":button}

def move(dx,dy):
    if any(not isinstance(v,int) or isinstance(v,bool) or abs(v)>500 for v in (dx,dy)):
        raise ValueError("Relative mouse movement must be integers between -500 and 500")
    _ready()
    _mouse(0x0001,dx,dy)
    return {"sent":True,"dx":dx,"dy":dy}

def scroll(amount):
    if not isinstance(amount,int) or isinstance(amount,bool) or amount not in (-3,-2,-1,1,2,3):
        raise ValueError("Scroll must be 1..3 or -1..-3 steps")
    _ready()
    _mouse(0x0800,data=amount*120)
    return {"sent":True,"steps":amount}

def type_text(value):
    if not isinstance(value,str) or not 1<=len(value)<=120 or any(ord(c)<32 or ord(c)==127 for c in value):
        raise ValueError("Type 1..120 printable characters only; no newline or control characters")
    _ready()
    class K(ctypes.Structure):
        _fields_=[("wVk",ctypes.c_ushort),("wScan",ctypes.c_ushort),("dwFlags",ctypes.c_ulong),
                  ("time",ctypes.c_ulong),("dwExtraInfo",ctypes.c_void_p)]
    class M(ctypes.Structure):
        _fields_=[("dx",ctypes.c_long),("dy",ctypes.c_long),("mouseData",ctypes.c_ulong),
                  ("dwFlags",ctypes.c_ulong),("time",ctypes.c_ulong),("dwExtraInfo",ctypes.c_void_p)]
    class U(ctypes.Union):_fields_=[("ki",K),("mi",M)]
    class I(ctypes.Structure):_fields_=[("type",ctypes.c_ulong),("data",U)]
    count=0
    # Explicit UTF-16 code units for Windows Unicode input; key-up always follows.
    for raw in value.encode("utf-16-le"):
        pass
    data=value.encode("utf-16-le")
    for i in range(0,len(data),2):
        code=data[i]|(data[i+1]<<8)
        for up in (False,True):
            _ready()
            entry=I();entry.type=INPUT_KEYBOARD
            entry.data.ki=K(0,code,0x0004|(KEYEVENTF_KEYUP if up else 0),0,None)
            if ctypes.windll.user32.SendInput(1,ctypes.byref(entry),ctypes.sizeof(entry))!=1:
                raise ValueError("Windows rejected text input")
        count+=1
    return {"sent":True,"utf16_units":count,"text_redacted":True}

def screenshot():
    _ready()
    try:
        from PIL import ImageGrab
    except ImportError as exc:
        raise ValueError("Screenshots require optional Pillow on Windows: pip install Pillow") from exc
    hwnd=_foreground()
    rect=(ctypes.c_long*4)()
    if not ctypes.windll.user32.GetWindowRect(hwnd,ctypes.byref(rect)):
        raise ValueError("Cannot determine FiveM window bounds")
    left,top,right,bottom=rect
    if right<=left or bottom<=top or (right-left)*(bottom-top)>16_000_000:
        raise ValueError("FiveM window bounds exceed safe screenshot size")
    capture=ImageGrab.grab(bbox=(left,top,right,bottom),all_screens=True)
    from .natives import _cache_dir
    folder=_cache_dir()/"game-screenshots"
    folder.mkdir(parents=True,exist_ok=True)
    output=folder/("fivem-"+str(int(time.time()*1000))+".png")
    capture.save(output,format="PNG")
    return {"captured":True,"path":str(output),"width":capture.width,"height":capture.height,
            "note":"Foreground window rectangle only; overlapping desktop windows may appear. Local screenshot may contain private game information."}
