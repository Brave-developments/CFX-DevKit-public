---
name: cfx-fivem-full-control
description: Use for the owner's expressly requested Full Control inspection, code testing, debugging or operation of a disposable local FiveM development server and authorized test client.
---

Call cfx_live_status before sending any command. It must show an owner-armed session and a recently polling server. Do not claim connectivity if the server has not polled. Use cfx_live_run with a specific supported kind and valid payload_json, and target only an ACE-authorized developer client. Prefer read-only queries before changing game state. Respect user-requested scope. Report the real cfx_live_result outcome rather than claiming an operation worked simply because it queued. Read configured logs via cfx_live_log when investigating errors. Never arm a session yourself, expose credentials, port-forward the broker, or run high-privilege commands on production servers. See docs/FULL_CONTROL.md.
