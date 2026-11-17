---
name: cfx-live-dev-control
description: Use when explicitly asked to test and restart an owned FiveM development server resource safely.
---

1. Call cfx_control_status. Do not claim the actual FXServer is connected if no observed result exists.
2. Only propose ensure/restart/stop for exactly allowlisted development resources requested by the user.
3. Call cfx_control_propose with action, resource, and a specific reason. This returns a pending ID, not execution.
4. Ask the owner to review and approve separately via interactive CLI (control-approve). Never approve on their behalf.
5. Call cfx_control_result to read the observation; state does not establish in-game success.
6. Do not use this prototype to administer production servers, players, SQL, SSH or arbitrary Lua. See docs/CONTROL_BRIDGE.md.
