---
name: cfx-project-audit
description: Analyze FiveM resources for manifest issues, framework usage, likely vulnerabilities, performance pitfalls, and NUI integration.
---
First use cfx_scan_project, then validate each relevant fxmanifest.lua with cfx_validate_manifest. Run cfx_detect_framework, cfx_audit_security, and cfx_audit_nui. Clearly distinguish a static heuristic warning from a proven bug; verify with source code and official Cfx documentation. Do not claim a live server was tested. Do not reveal credentials from any files. Require human review before editing resources.
