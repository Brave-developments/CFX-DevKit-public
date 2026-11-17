"""Separate MCP entry points; the legacy combined server stays compatible."""
from cfx_devkit import server

INTEGRATION_PREFIXES = (
    "cfx_fxserver_", "cfx_fivem_", "cfx_dev_start_", "cfx_game_",
    "cfx_live_", "cfx_control_", "cfx_bridge_",
)
INTEGRATION_NAMES = frozenset({"cfx_server_health", "cfx_server_process_metrics", "cfx_server_stability_log"})

def tool_names(profile):
    if profile not in {"development", "txadmin"}:
        raise ValueError("Unknown MCP profile")
    integration = {entry["name"] for entry in server.TOOLS
                   if entry["name"].startswith(INTEGRATION_PREFIXES)
                   or entry["name"] in INTEGRATION_NAMES}
    all_names = {entry["name"] for entry in server.TOOLS}
    return integration if profile == "txadmin" else all_names - integration

def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", choices=("development", "txadmin"))
    args = parser.parse_args()
    server.main(tool_names(args.profile))

if __name__ == "__main__":
    main()
