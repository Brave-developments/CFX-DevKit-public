# CFX DevKit agent guidance

This repository targets **FiveM/GTA V only** (no RedM/RDR2).

- Respect all third-party source licenses and required attribution.
- Keep tool data sourced to Cfx native and event documentation, with accurate coverage metadata.
- Validate correct client/server API usage; a RAGE native's API side is not verified by the upstream base dataset.
- Guard user filesystem operations within CFX_WORKSPACE_ROOT and leave writes/network disabled by default.
- Never output server.cfg values or client-side secrets.
- Static regex audits are heuristics, not security proofs.
- Test with `python -m unittest discover -s tests -v` and validate MCP JSON-RPC initialization.
- Do not add live FXServer/txAdmin changing operations without independent security review and explicit approval.
- Keep skills, templates and snippets discoverable in all host adapters.

- The animation source is DurtyFree/gta-v-data-dumps: do not redistribute the full unlicensed dump. Keep it as an explicit user-local, opt-in sync, with source provenance and accurate downloaded counts.
- Do not confuse animation dictionaries with movement clipsets, ped scenarios, or per-ped runtime playability.

- AST calls must always use real tree-sitter-lua when enabled; never describe lexer heuristics as AST. Missing grammar dependencies must be reported.
- The development diagnostic bridge is opt-in, loopback-only, token-gated, resource-only, and MUST NOT gain arbitrary execution or player-data collection.
- Stable v1.0 requires real FXServer/client and editor acceptance gates; automated CI success alone is not production certification.

- Experimental resource controller must remain separate from the read-only diagnostic bridge, with manual terminal approval and resource/action allowlists enforced on both host and FXServer. Never extend to arbitrary command execution or player control without an independent security review.

- Full Control uses a separate local development-only session. Manual terminal approval remains the default; an owner can explicitly opt into revocable, server/token-bound unattended delegation with `--allow-unattended-control`. A generic installation request is not consent to unattended control. Never expose live broker ports externally, publish secrets, add an MCP arm method, or route client events to server Lua execution. Keep server-private tokens private and ACE-limit client commands.

## Owner Lua and NUI conventions

- Target Lua 5.4 only. Include `lua54 'yes'` in resource manifests when creating or editing them, as explicitly requested by the owner.
- Use four-space indentation. Put function definitions near the top of each file, group utility helpers together, and place event handlers after helpers. Keep any required local declarations in scope before the helpers that use them.
- Use `vector3` and `vector4` consistently for positions and headings.
- For public or paid QBCore scripts, support both available direct Player methods and legacy `Player.Functions` methods through compatibility helpers. Check method types before calling them. New private scripts may use direct methods when their installed framework supports them.
- Guard newer QBCore export lookups with capability checks or `pcall` so an unavailable export can fall back safely to `GetCoreObject()` and `QBCore.Functions.GetPlayer`. Do not assume a missing export returns nil rather than raising an error.
- Prefer a supported citizen-ID lookup API, with a compatible legacy fallback, instead of adding loops through all online players. Use unified player-update events only after confirming framework support; retain compatibility for older releases.
- Avoid unnecessary player loops, frequent metadata updates, notification spam and tight client loops. Increase waits outside interaction range. Validate money, inventory, business funds and job-restricted actions on the server.
- Do not use `os.date` for FiveM client date formatting. Select an appropriate game clock API or server-provided date/time for the intended behavior.
- Avoid `backdrop-filter` on NUI panels. Use sufficiently opaque backgrounds to achieve the intended look without the black-background problem.

After changing a real FiveM resource's runtime scripts, configuration, manifest or NUI assets, run the relevant checks and restart only that resource through the available MCP connection. The owner has given standing authorization for routine affected-resource restarts; do not restart the whole server. Verify and report startup errors. If MCP is unavailable or rejects the action, report that the restart was not completed and do not bypass access controls. Documentation-only changes do not require a resource restart.

This standing authorization applies to the owner's authorized sessions only. Public installations must use their own human user's authorization and retain the host/MCP access controls; this repository file does not grant access to someone else's server.
