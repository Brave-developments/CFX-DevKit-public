"""Read-only, bounded performance observations; no commands sent to FXServer."""
from collections import Counter
import json
import math
import re
import time
from urllib.request import build_opener, ProxyHandler, HTTPRedirectHandler
from . import core, clientlaunch

MAX_HTTP_BYTES = 2_000_000
MAX_LOG_BYTES = 4_000_000
RESOURCE = r'[A-Za-z0-9_.-]{1,96}'


def integer(value, name, low, high):
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise ValueError(f'{name} must be {low}..{high}')
    return value


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _http_json(port, endpoint):
    # Never follow redirects off loopback or send diagnostics through a proxy.
    opener = build_opener(ProxyHandler({}), NoRedirect())
    started = time.perf_counter()
    try:
        with opener.open(f'http://127.0.0.1:{port}/{endpoint}', timeout=3) as response:
            raw = response.read(MAX_HTTP_BYTES + 1)
            if response.status != 200 or len(raw) > MAX_HTTP_BYTES:
                return None, {'available': False, 'reason': 'invalid-or-oversized-response'}
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None, {'available': False, 'reason': 'invalid-json-shape'}
        return data, {'available': True, 'response_ms': round((time.perf_counter()-started)*1000, 3)}
    except (OSError, ValueError):
        return None, {'available': False, 'reason': 'unreachable-or-invalid-json'}


def _count(value):
    if isinstance(value, str) and value.isascii() and value.isdigit() and len(value) <= 9:
        value = int(value)
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 1_000_000 else None


def server_health(port=30120):
    clientlaunch._port(port)
    info, info_status = _http_json(port, 'info.json')
    dynamic, dynamic_status = _http_json(port, 'dynamic.json')
    resources = (info or {}).get('resources')
    return {'source': 'live-loopback-http', 'port': port, 'observed_at_unix': int(time.time()),
            'available': bool(info is not None and isinstance(info.get('vars'), dict)),
            'endpoints': {'info': info_status, 'dynamic': dynamic_status},
            'clients': _count((dynamic or {}).get('clients')),
            'max_clients': _count((dynamic or {}).get('sv_maxclients')),
            'advertised_resource_count': len(resources) if isinstance(resources, list) else None,
            'script_ms_available': False,
            'note': 'HTTP response latency is not server tick time. Resource advertisements are not '
                    'proof of successful startup. No convars, player identities or raw responses returned.'}


def process_metrics(pid=0, interval_ms=1000):
    integer(pid, 'pid', 0, 2**31-1)
    integer(interval_ms, 'interval_ms', 100, 3000)
    try:
        import psutil
    except ImportError:
        return {'available': False, 'reason': 'optional-dependency-missing',
                'hint': "From the project checkout run: python -m pip install -e '.[monitoring]'"}
    allowed = {'fxserver', 'fxserver.exe'}
    try:
        if not pid:
            candidates = []
            for proc in psutil.process_iter(['pid', 'name']):
                if (proc.info.get('name') or '').casefold() in allowed:
                    candidates.append(proc.info['pid'])
                if len(candidates) >= 50:
                    break
            from . import fxserverlaunch
            started = fxserverlaunch._started_process
            owned_pid = started.pid if (started is not None and started.poll() is None and
                                        fxserverlaunch._started_process_role=='game-server') else None
            if owned_pid in candidates:
                pid = owned_pid
            elif len(candidates) != 1:
                return {'available': False, 'reason': 'select-pid' if candidates else 'no-fxserver-process',
                        'candidate_pids': sorted(candidates),
                        'note': 'Multiple FXServer workers/managers are not combined or assumed to be one profile.'}
            else:
                pid = candidates[0]
        proc = psutil.Process(pid)
        if proc.name().casefold() not in allowed:
            raise ValueError('Selected PID is not named FXServer; refusing unrelated process sampling')
        created = proc.create_time()
        first_cpu = proc.cpu_times()
        first_memory = proc.memory_info().rss
        started = time.perf_counter()
        time.sleep(interval_ms/1000)
        last_cpu = proc.cpu_times()
        memory = proc.memory_info()
        threads = proc.num_threads()
        elapsed = time.perf_counter()-started
        if proc.create_time() != created:
            return {'available': False, 'reason': 'process-changed-during-sample'}
        used = last_cpu.user+last_cpu.system-first_cpu.user-first_cpu.system
        cores = psutil.cpu_count() or 1
        cpu = max(0.0, used)/elapsed*100
        return {'available': True, 'source': 'live-os-process-sample', 'pid': pid,
                'sample_ms': round(elapsed*1000, 3), 'cpu_percent_one_core': round(cpu, 3),
                'cpu_percent_machine_capacity': round(cpu/cores, 3), 'logical_cpu_count': cores,
                'rss_bytes': memory.rss, 'rss_change_bytes': memory.rss-first_memory,
                'threads': threads, 'uptime_seconds': round(max(0, time.time()-created), 3),
                'note': 'One PID only. One-core CPU can exceed 100% on multicore workloads. '
                        'RSS is resident process memory, not resource memory or a leak diagnosis. '
                        'CPU and memory do not measure per-script milliseconds.'}
    except psutil.Error:
        return {'available': False, 'reason': 'process-unavailable-or-access-denied', 'pid': pid}


def stability_log(path, lines=10000):
    integer(lines, 'lines', 1, 50000)
    target = core.safe_path(path)
    if not target.is_file() or target.suffix.lower() not in ('.log', '.txt'):
        raise ValueError('Provide a workspace-relative .log or .txt server log, not server.cfg')
    with target.open('rb') as stream:
        stream.seek(0, 2)
        length = stream.tell()
        offset = max(0, length-MAX_LOG_BYTES)
        stream.seek(offset)
        raw = stream.read(MAX_LOG_BYTES)
    if offset:
        raw = raw.split(b'\n', 1)[-1]
    all_lines = raw.decode('utf-8', errors='replace').splitlines()
    sample = all_lines[-lines:]
    hitches = []
    errors = Counter()
    starts = Counter()
    dependencies = Counter()
    failed_dependencies = Counter()
    onesync_required = 0
    fatal = 0
    for line in sample:
        match = re.search(r'hitch warning:.*?interval of (\d{1,9}(?:\.\d{1,3})?) milliseconds', line, re.I)
        if match:
            hitches.append(float(match[1]))
        if 'SCRIPT ERROR' in line:
            match = re.search(r'SCRIPT ERROR:\s*@('+RESOURCE+r')/', line)
            if not match:
                match = re.search(r'\bscript:('+RESOURCE+r')\]', line)
            errors[match[1] if match else 'unattributed'] += 1
        match = re.search(r'Could not find dependency ('+RESOURCE+r') for resource ('+RESOURCE+r')(?:\.|\s|$)', line)
        if match:
            dependencies[(match[2].rstrip('.'), match[1])] += 1
        match = re.search(r'Could not start dependency ('+RESOURCE+r') for resource ('+RESOURCE+r')(?:\.|\s|$)', line)
        if match:
            failed_dependencies[(match[2].rstrip('.'), match[1])] += 1
        onesync_required += bool(re.search(r'OneSync needs to be enabled', line, re.I))
        match = re.search(r'\bStarted resource ('+RESOURCE+r')(?:\s|$)', line)
        if match:
            starts[match[1]] += 1
        fatal += bool(re.search(r'\bfatal error\b|\bprocess crashed\b', line, re.I))
    ordered = sorted(hitches)
    return {'source': 'bounded-server-log-tail', 'path': target.relative_to(core.workspace_root()).as_posix(),
            'sample_lines': len(sample), 'file_bytes': length,
            'tail_only': bool(offset or len(all_lines)>lines),
            'hitches': {'count': len(hitches), 'max_ms': max(hitches) if hitches else None,
                        'p95_ms': ordered[max(0, math.ceil(len(ordered)*.95)-1)] if ordered else None},
            'script_errors': [{'resource': r, 'count': n} for r, n in errors.most_common(100)],
            'missing_dependencies': [{'resource': r, 'dependency': d, 'count': n}
                                     for (r, d), n in dependencies.most_common(100)],
            'failed_dependencies': [{'resource': r, 'dependency': d, 'count': n}
                                    for (r, d), n in failed_dependencies.most_common(100)],
            'onesync_required_markers': onesync_required,
            'repeated_starts': [{'resource': r, 'count': n} for r, n in starts.most_common(100) if n>1],
            'fatal_error_markers': fatal,
            'note': 'Counts in this bounded tail, not rates or a complete health verdict. '
                    'Repeated starts may be deliberate. Raw lines, errors, identifiers and secrets are not returned.'}


def capture_plan(frames=500, filename='performance-profile.json', side='server'):
    integer(frames, 'frames', 100, 10000)
    if side not in ('server', 'client'):
        raise ValueError('side must be server or client')
    if not isinstance(filename, str) or not re.fullmatch(r'[A-Za-z0-9_-][A-Za-z0-9_.-]{0,74}\.json', filename):
        raise ValueError('filename must be a simple .json basename without paths or command characters')
    return {'source': 'instructions-only', 'side': side, 'frames': frames, 'commands_executed': False,
            'commands': [f'profiler record {frames}', 'profiler status', f'profiler saveJSON {filename}'],
            'steps': ['Run record in the FXServer console for server work, or F8 for client work.',
                      'Reproduce the slow action; wait until status shows recording has stopped.',
                      'Run saveJSON, then place the exported file inside CFX_WORKSPACE_ROOT.',
                      'Call cfx_resource_timings with the path and the same side.'],
            'note': 'Frames are not milliseconds. Capture can add overhead; compare matching workloads. '
                    'No recording is started and no Full Control permission is granted.',
            'documentation': 'https://docs.fivem.net/docs/scripting-manual/debugging/using-profiler/'}
