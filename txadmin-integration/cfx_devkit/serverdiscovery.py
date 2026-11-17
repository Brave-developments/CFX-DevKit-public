"""Bounded, read-only discovery of Windows FXServer targets in the workspace.

Never executes launchers or reads server.cfg contents. Profile JSON contributes
only validated paths; secrets and startup arguments are never returned.
"""
from collections import deque
from hashlib import sha256
import json
import os
from pathlib import Path
from . import core

MAX_DEPTH = 8
MAX_ENTRIES = 50000
MAX_PROFILE_BYTES = 256_000
SKIP = core.IGNORE_DIRS | {'resources', 'cache', 'server-cache', 'server-cache-priv',
                         'logs', 'data', 'crashes', 'screenshots', 'backups'}


def target_id(executable, config):
    paths = [os.path.normcase(str(Path(p).resolve())) for p in (executable, config)]
    return sha256(json.dumps(paths).encode('utf-8')).hexdigest()


def discover(path='.'):
    root = core.safe_path(path)
    if not root.is_dir():
        raise ValueError('Server discovery requires an existing workspace directory')
    executables = set()
    configs = {}
    profiles = []
    queue = deque([(root, 0)])
    visited = 0
    truncated = False
    skipped = 0
    try:
        max_entries = int(os.environ.get('CFX_DISCOVERY_MAX_ENTRIES', MAX_ENTRIES))
    except (ValueError, TypeError):
        raise ValueError('CFX_DISCOVERY_MAX_ENTRIES must be an integer from 1 to 250000') from None
    if not 1 <= max_entries <= 250000:
        raise ValueError('CFX_DISCOVERY_MAX_ENTRIES must be 1..250000')
    budget_exhausted = False

    def contained(candidate):
        try:
            resolved = candidate.resolve()
            return resolved if resolved.is_relative_to(root) else None
        except (OSError, ValueError, RuntimeError):
            return None

    while queue and not budget_exhausted:
        folder, depth = queue.popleft()
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    visited += 1
                    if visited > max_entries:
                        truncated = True
                        budget_exhausted = True
                        break
                    candidate = Path(entry.path)
                    # Reparse points/junctions are excluded as well as symlinks.
                    if entry.is_symlink() or getattr(candidate, 'is_junction', lambda: False)():
                        continue
                    safe = contained(candidate)
                    if safe is None:
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name.casefold() in SKIP:
                            continue
                        if depth < MAX_DEPTH:
                            queue.append((safe, depth + 1))
                        else:
                            truncated = True
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    if entry.name.casefold() == 'fxserver.exe':
                        executables.add(safe)
                    elif entry.name.casefold() == 'server.cfg':
                        configs.setdefault(safe, {'source': 'server.cfg'})
                    elif entry.name.casefold() == 'config.json' and any(
                            part.casefold().startswith('txdata') for part in safe.relative_to(root).parts[:-1]):
                        profiles.append(safe)
        except OSError:
            skipped += 1

    for profile in sorted(profiles):
        try:
            with profile.open('rb') as stream:
                raw = stream.read(MAX_PROFILE_BYTES + 1)
            if len(raw) > MAX_PROFILE_BYTES:
                skipped += 1
                continue
            data = json.loads(raw.decode('utf-8-sig'))
            section = data.get('server', data.get('fxRunner', {}))
            data_path = section.get('dataPath', section.get('serverDataPath'))
            cfg_path = section.get('cfgPath')
            if not isinstance(data_path, str) or not isinstance(cfg_path, str):
                continue
            base = Path(data_path)
            # Relative deployment paths are ambiguous without evaluating txAdmin.
            if not base.is_absolute():
                continue
            config = contained(base / cfg_path)
            if config and config.name.casefold() == 'server.cfg' and config.is_file():
                configs[config] = {'source': 'txadmin-profile',
                                   'profile_config': str(profile)}
        except (OSError, ValueError, TypeError, AttributeError):
            skipped += 1

    candidates = []
    for config, source in sorted(configs.items()):
        matches = []
        for parent in config.parents:
            if not parent.is_relative_to(root):
                break
            matches = sorted(exe for exe in executables if exe.is_relative_to(parent))
            if matches:
                break
        executable = matches[0] if len(matches) == 1 else None
        candidates.append({**source, 'config': str(config), 'data_directory': str(config.parent),
                           'txadmin_runtime_settings_applied': False,
                           'launch_mode_hint': 'txadmin' if source['source']=='txadmin-profile' else 'direct',
                           'warnings': (['Use managed txAdmin startup to preserve its OneSync and other saved runtime settings.'] if source['source']=='txadmin-profile' else []),
                           'executable': str(executable) if executable else None,
                           'executable_candidates': [str(exe) for exe in matches],
                           'target_id': target_id(executable, config) if executable else None})
    selected = candidates[0] if len(candidates) == 1 and candidates[0]['executable'] and not truncated and not skipped else None
    state = ('detected' if selected else 'selection-required' if len(candidates) > 1 else
             'incomplete' if truncated or skipped else
             'missing-executable' if candidates else 'not-found')
    return {'state': state, 'search_root': str(root), 'candidates': candidates,
            'executables': [str(exe) for exe in sorted(executables)], 'selected': selected,
            'entries_visited': min(visited,max_entries), 'entry_limit': max_entries, 'max_depth': MAX_DEPTH,
            'truncated': truncated, 'skipped_locations': skipped,
            'note': 'Read-only workspace search; no drive scan or launcher execution. '
                    'Use CFX_FXSERVER_EXE and CFX_FXSERVER_CFG to select an ambiguous or external target. '
                    'A responding port alone does not identify a discovered profile.'}
