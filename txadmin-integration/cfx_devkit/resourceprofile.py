"""Resource tick timing from genuine Chrome Trace X or per-thread B/E spans."""
from collections import defaultdict
import json
import math
import re
from . import core, profiler

TICK = re.compile(r'^tick \(([A-Za-z0-9_.-]{1,96})\)$')


def _number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and -1e18 <= value <= 1e18 and math.isfinite(value))


def _spans(events):
    stacks = defaultdict(list)
    spans = []
    invalid = 0
    for e in events:
        if not isinstance(e, dict):
            invalid += 1
            continue
        pid, tid = e.get('pid', 0), e.get('tid', 0)
        # Untrusted metadata is never used as an output label or dictionary key.
        if not isinstance(pid, int) or isinstance(pid, bool) or not isinstance(tid, int) or isinstance(tid, bool):
            invalid += 1
            continue
        phase = e.get('ph')
        ts = e.get('ts')
        if phase not in ('B', 'E', 'X'):
            continue
        if not _number(ts) or ts < 0:
            invalid += 1
            continue
        if phase == 'B':
            stacks[pid, tid].append(e)
            continue
        if phase == 'E':
            if not stacks[pid, tid]:
                invalid += 1
                continue
            begin = stacks[pid, tid].pop()
            if e.get('name') and e['name'] != begin.get('name'):
                invalid += 1
                continue
            duration = ts-begin['ts']
            name = begin.get('name')
            ts = begin['ts']
        else:
            duration, name = e.get('dur'), e.get('name')
        if not _number(duration) or duration < 0 or not isinstance(name, str):
            invalid += 1
            continue
        if _number(ts+duration):
            spans.append((name, pid, tid, ts, ts+duration))
        else:
            invalid += 1
    return spans, invalid+sum(len(stack) for stack in stacks.values())


def _union(intervals):
    total = 0.0
    end = None
    for a, b in sorted(intervals):
        if end is None or a > end:
            total += b-a
        else:
            total += max(0, b-end)
        end = b if end is None else max(end, b)
    return total


def resource_timings(path, side='server', limit=20):
    from .performance import integer
    integer(limit, 'limit', 1, 100)
    if side not in ('server', 'client'):
        raise ValueError('side must be server or client')
    target = core.safe_path(path)
    if not target.is_file() or target.suffix.lower() not in ('.json', '.trace'):
        raise ValueError('Provide a workspace-relative profiler .json or .trace file')
    with target.open('rb') as stream:
        raw = stream.read(profiler.MAX_TRACE_BYTES+1)
    if len(raw)>profiler.MAX_TRACE_BYTES:
        raise ValueError('Trace exceeds 40 MB analysis limit')
    obj = json.loads(raw)
    events = obj.get('traceEvents') if isinstance(obj, dict) else obj
    if not isinstance(events, list) or len(events)>profiler.MAX_EVENTS:
        raise ValueError('Expected Chrome Trace events with at most 300000 entries')
    spans, invalid = _spans(events)
    groups = defaultdict(list)
    frames = defaultdict(set)
    pids = set()
    for name, pid, tid, a, b in spans:
        match = TICK.fullmatch(name)
        if match:
            groups[match[1]].append((pid, tid, a, b))
            pids.add(pid)
        if name == 'Resource Manager Tick' and b>a:
            frames[pid].add((tid, a, b))
    if len(pids)>1:
        raise ValueError('Trace contains resource ticks from multiple processes; split captures before comparison')
    pid = next(iter(pids), None)
    frame_count = len(frames.get(pid, ()))
    rows = []
    for resource, items in groups.items():
        durations = sorted((b-a)/1000 for _, _, a, b in items)
        by_thread = defaultdict(list)
        for pid, tid, a, b in items:
            by_thread[pid, tid].append((a, b))
        total = sum(_union(intervals) for intervals in by_thread.values())/1000
        rows.append({'resource': resource, 'tick_spans': len(items),
                     'mean_tick_span_ms': round(sum(durations)/len(durations), 6),
                     'p95_tick_span_ms': round(durations[math.ceil(len(durations)*.95)-1], 6),
                     'max_tick_span_ms': round(max(durations), 6), 'observed_total_ms': round(total, 6),
                     'mean_ms_per_observed_frame': round(total/frame_count, 6) if frame_count else None})
    rows.sort(key=lambda r: -(r['mean_ms_per_observed_frame'] if frame_count else r['mean_tick_span_ms']))
    return {'source': 'captured-profiler-trace', 'side_declared': side, 'side_independently_verified': False,
            'path': target.relative_to(core.workspace_root()).as_posix(), 'live_sample': False,
            'events_read': len(events), 'invalid_or_unmatched_events': invalid,
            'observed_frames': frame_count, 'resources_total': len(rows), 'resources': rows[:limit],
            'truncated': len(rows)>limit,
            'note': 'Measures tick (resource) scopes only, including nested work. Same-resource '
                    'overlaps are merged per thread; different resources/threads can overlap. '
                    'Frame averages require Resource Manager Tick scopes. Not live resmon, total CPU, '
                    'all handlers, or proof of stability. Missing scopes are not zero cost.'}


def compare_timings(baseline_path, candidate_path, side='server', limit=20):
    from .performance import integer
    integer(limit, 'limit', 1, 100)
    # Comparing a truncated top-N list would misclassify resources as missing.
    baseline = resource_timings(baseline_path, side, 100)
    candidate = resource_timings(candidate_path, side, 100)
    if baseline['truncated'] or candidate['truncated']:
        raise ValueError('Comparison supports at most 100 distinct resources per capture; narrow the captures')
    field = ('mean_ms_per_observed_frame' if baseline['observed_frames'] and candidate['observed_frames']
             else 'mean_tick_span_ms')
    a = {r['resource']: r for r in baseline['resources']}
    b = {r['resource']: r for r in candidate['resources']}
    rows = []
    for resource in sorted(a.keys() | b.keys()):
        before, after = a.get(resource), b.get(resource)
        x, y = before[field] if before else None, after[field] if after else None
        delta = y-x if before and after else None
        rows.append({'resource': resource, 'baseline_ms': x, 'candidate_ms': y,
                     'delta_ms': round(delta, 6) if delta is not None else None,
                     'change_percent': round(delta/x*100, 3) if delta is not None and x else None,
                     'coverage': 'both' if before and after else 'candidate-only' if after else 'baseline-only',
                     'baseline_spans': before['tick_spans'] if before else 0,
                     'candidate_spans': after['tick_spans'] if after else 0})
    rows.sort(key=lambda r: (r['delta_ms'] is None, -(r['delta_ms'] or 0)))
    return {'source': 'captured-profiler-comparison', 'side_declared': side, 'metric': field,
            'baseline_frames': baseline['observed_frames'], 'candidate_frames': candidate['observed_frames'],
            'resources_total': len(rows), 'resources': rows[:limit], 'truncated': len(rows)>limit,
            'note': 'Positive delta means more observed time. Compare the same side and workload; '
                    'capture side is caller-declared. Missing resources are not improvements. '
                    'These samples do not establish statistical significance.'}
