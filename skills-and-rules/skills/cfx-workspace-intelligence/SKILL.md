---
name: cfx-workspace-intelligence
description: Analyze FiveM Lua event flows and manifests while clearly labeling all static limitations.
---
Before any code changes use cfx_scan_project, cfx_detect_framework, cfx_workspace_index, and cfx_manifest_asset_report. For an event use cfx_trace_event and cfx_authority_review. Check both registrations and sends; external resources and dynamically created event names will be missed. Every security finding must be manually reviewed, and no network / runtime testing can be claimed from static analysis alone. Avoid writing to live resources without explicit permission and a rollback plan.
