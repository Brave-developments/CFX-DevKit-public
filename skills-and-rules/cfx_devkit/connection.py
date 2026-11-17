"""Launch an installed integration with its private, installer-created settings.

Starts only the loopback broker, never FXServer or an authorization session.
"""
from pathlib import Path
import argparse
import json
import os
import threading

from . import livecontrol, profiles, server

ENV_KEYS = frozenset({
    "CFX_WORKSPACE_ROOT", "CFX_ENABLE_WRITES", "CFX_ENABLE_NETWORK",
    "CFX_LIVE_ENABLE", "CFX_LIVE_MODE", "CFX_LIVE_TOKEN",
    "CFX_LIVE_SERVER_LOG", "CFX_LIVE_CLIENT_LOG",
    "CFX_DEVKIT_DATA_DIR",
})


def load_settings(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    env = data.get("env")
    if not isinstance(env, dict) or set(env) - ENV_KEYS:
        raise ValueError("Invalid connection settings")
    if not all(isinstance(value, str) for value in env.values()):
        raise ValueError("Connection settings must contain strings")
    return env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", required=True, type=Path)
    parser.add_argument("--arm", action="store_true", help="Human interactive approval using this connection's settings")
    args = parser.parse_args()
    os.environ.update(load_settings(args.settings))
    if args.arm:
        print(json.dumps(livecontrol.arm()))
        return
    broker = livecontrol.make_server()
    thread = threading.Thread(target=broker.serve_forever, daemon=True)
    thread.start()
    try:
        server.main(profiles.tool_names("txadmin"))
    finally:
        broker.shutdown()
        broker.server_close()
        thread.join(timeout=3)


if __name__ == "__main__":
    main()
