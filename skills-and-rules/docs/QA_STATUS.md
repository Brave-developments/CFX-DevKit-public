# CFX DevKit release-candidate QA status

This is an engineering status document, **not** a stable-release certification.

## Addressed in the QA hardening commit

1. Windows MCP transport: UTF-8 output and ASCII-safe JSON responses. The Windows CI suite explicitly starts MCP with `PYTHONIOENCODING=cp1252`.
2. AST stability: require `tree-sitter==0.25.2` and fail closed before opening a mismatched native parser.
3. CfxLua: unsupported operator syntax is marked `syntax_validated=false`, never automatically declared invalid.
4. Cursor MCP config points to `.cursor/plugin-mcp.json`.
5. Security scan and event review detect file side using standard names, resource paths, and manifest declarations. Unknown side is no longer presumed to be server code.
6. Event/export static lookup skips Lua long comments and quoted examples; JS export declarations are not confused with resource export calls.
7. Resource list reveals when more than 100 results exist. Manifest asset checks report unmatched streaming assets, with caveat that implicit stream loading is valid.
8. Bare `sv_licenseKey` and `rcon_password` entries are flagged without revealing values.
9. Full-animation dictionary detail separately reports `clip_count` for the dataset and `dictionary_clip_count` for the requested dictionary.
10. Native cache downloads gain SHA-256, source URL, timestamp and count metadata sidecars.
11. Startup configuration failures in the read-only bridge give a concise error instead of an exception traceback.
12. Path formatting is normalized and Windows filesystem permission limitations in tests are handled.

## Remaining acceptance gates

- Rerun the entire affected large FiveM Lua codebase on a Windows developer workstation; isolated CI cannot validate all custom Lua syntax.
- Test actual Codex/Cursor/Claude integration inside the target editor versions.
- Test against a running FXServer and FiveM game client; no game UI/runtime behavior has been independently verified by this QA suite.
- Review the privilege boundaries of any optional live-control feature separately before enabling it.

A source-level AST's inability to parse FiveM-specific operators must remain visible as *unverified*, not counted as a clean syntax pass.
