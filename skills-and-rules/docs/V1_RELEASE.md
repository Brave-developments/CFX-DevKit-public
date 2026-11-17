# CFX DevKit v1.0 RC acceptance checklist

**Current release:** 1.0.0-rc.1. This is a comprehensive pre-release. Stable 1.0.0 is **not** asserted until manual gates pass.

## Automated checks (GitHub Actions)

- Python 3.10, 3.11, 3.12, 3.13: unit tests, AST grammar, tool list and MCP stdio handshake
- Wheel: build, install outside source folder, verify reference seed and snippets/templates can be read
- Official MCP Python client: connect using stdio, list tools, call actual tools
- GTA V native, animation, nine asset catalogs: upstream snapshot synchronization, schema and source-version tracking
- NUI: React/Vite and Svelte/Vite builds, plus Lua syntax checks
- v1 bridge: actual HTTP loopback process tests, token enforcement, payload allowlist, lack of arbitrary command endpoints
- MCP launch snippets: generated paths and stdio smoke tests for Codex/Cursor/Claude (NOT host-app installations)

## Manual gate 1: editors (must run on real installed hosts)

In each editor, generate local MCP configuration with:
~~~powershell
python scripts/host_config.py --host cursor --project "C:\FiveM\resources"
python scripts/host_config.py --host claude --project "C:\FiveM\resources"
python scripts/host_config.py --host codex --project "C:\FiveM\resources"
~~~
Paste each output into the respective host's MCP settings. Check the host discovers 75 tools and the package contains 19 agent skills. Execute \`cfx_lua_ast_status\`, \`cfx_scan_project\`, and \`cfx_animation_status\`, and verify invalid arguments are handled. Check \`scan_complete\`, \`scan_truncated\` and \`result_truncated\`; never treat an incomplete audit as a clean security result. Document tested host versions.

## Manual gate 2: game runtime

Use an **owned development-only** FiveM server, never a production instance. Test:
1. Load \`examples/cfx-devkit-preview\`, configure \`setr devkit_preview_enable 1\`, check commands \`/devkit_anim\` and \`/devkit_ptfx\`.
2. Validate example \`random@mugging3\` / \`handsup_standing_base\` and your build/ped compatibility.
3. Start the loopback receiver from \`docs/DEV_BRIDGE.md\`, ensure \`examples/cfx-devkit-reporter\`.
4. Start/stop a dummy resource; check \`cfx_bridge_recent\` shows resource lifecycle without player data.
5. Disable reporter, verify diagnostics stop. Remove from all production configurations.
6. For NUI samples, test focus, ESC/Close callbacks, client resource stop cleanup and reconnect conditions.
7. Compare a profiler trace report to the actual FiveM profiler capture.

## Manual gate 3: security and maintenance

- Independent review for project scanning path confinement, secrets handling and localhost bridge.
- Confirm third-party dataset licensing before any redistribution. Full upstream data stays in local user cache.
- Test on Windows, Linux and (where relevant) macOS with documented interpreter commands.
- Confirm no RedM/RDR2 data or runtime directives.
- Publish a stable release only when tests, documentation and smoke tests are signed off.

## Definition of 'done'

Automated passing CI = **candidate built and reproducible**.
A stable v1.0 = candidate plus completed manual checks above.
