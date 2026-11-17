---
name: cfx-nui
description: Plan, review and debug FiveM NUI browser-to-Lua message and callback workflows.
---
Read the UI bundle, browser source, client Lua and fxmanifest. Use cfx_audit_nui to spot missing message listeners, callback links, and resource-name handling. Explain the SendNUIMessage -> window message listener direction and browser fetch -> RegisterNUICallback direction. Treat missing signals as leads, not definitive bugs; bundled UI may hide source patterns. Verify against official Cfx docs and test in a local FiveM server.
