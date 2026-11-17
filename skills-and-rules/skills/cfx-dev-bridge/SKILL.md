---
name: cfx-dev-bridge
description: Configure and inspect the opt-in loopback-only sanitized FiveM development reporter, with no privileged remote commands.
---
Use cfx_bridge_setup to explain configuration; CFX_BRIDGE_ENABLE must be explicitly set to 1 and CFX_BRIDGE_TOKEN must be a fresh private high-entropy token. The bridge accepts only resource lifecycle/error category notifications through 127.0.0.1 and has no server-control channel. Use cfx_bridge_recent for previously saved sanitized records, not a false live-status claim. Never request the user to paste secrets into a public repo or replicated setr variable. Never enable on a production server. Check docs/DEV_BRIDGE.md.
