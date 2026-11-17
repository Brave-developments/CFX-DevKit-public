# Changelog

## 1.0.0-rc.1 (pre-release)

- Confined asset inventories prune Windows reparse points/junctions and report skipped links and inventory limits. Indirect source reads are confined and bounded too.
- Manifest validation and the dependency graph flag client-visible dependencies on server-only resources, including literal provider aliases and bounded transitive failures. Dynamic metadata and ambiguous/missing resources remain explicitly unverified.
- Freebuff joins the generated host configurations and outside-checkout stdio smoke tests; the unsupported direct-server.py launch instructions are removed.

- Native local txAdmin plan, authentication and profile verification in the existing startup tools; manager/control mutation remains disabled pending independent security review. Direct mode remains available. No direct fallback after managed errors.

- 75 MCP tools, 19 agent skills, 6 coding rules, 27 code snippets and 11 reusable resource/NUI templates.
- Six read-only server health, process metrics, resource timing/comparison, stability log and capture-plan tools; optional monitoring extra.
- Shared source-scan coverage reporting distinguishes incomplete scans from limited findings. Default source and discovery budgets are raised and configurable.
- MCP-started FXServer stdout/stderr are preserved in a workspace log. Join requests wait for the advertised resource inventory to settle; endpoint readiness alone is not script-health verification.
- FiveM URI launches are delegated to Windows Explorer to avoid the shell/browser launch error from console-attached agents.
- Stability logs distinguish absent dependencies from dependencies that failed to start and count OneSync-required markers. Direct launch responses warn that txAdmin runtime settings are not applied. Automatic process metrics prefer the live process started by the current MCP session.
- Optional real Lua grammar AST-based event and command source inspection (tree-sitter-lua).
- Token-authenticated, localhost-only, opt-in developer diagnostic bridge and server-side resource lifecycle reporter.
- GTA V/FiveM native and animation indexes, searchable event references, 9 user-local asset dataset catalogs.
- Project dependency, NUI, security, performance, SQL, server.cfg, exports, commands and GTA streaming reference checks.
- Optional in-game animation/particle preview resource for an owned development server.
- Official MCP Python SDK smoke tests, Python 3.10–3.13, frontend build tests, Lua syntax CI, wheel and source-package integrity checks.
- **Release status:** pre-release. Real FiveM client/FXServer and installed Codex/Cursor/Claude acceptance are pending. The static audit is not a proof of security.

No RedM/RDR2 support.
