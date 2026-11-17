# Native txAdmin integration: independent review required

AGENTS.md requires: “Do not add live FXServer/txAdmin changing operations without
independent security review and explicit approval.” The user authorized this
implementation. Independent review has not been completed by its author.

`cfx_devkit.txadmin.CONTROL_REVIEWED` remains false. Tests temporarily replace it
only for mocked processes and local fixture HTTP servers. There is no environment
flag or MCP tool that arms/reviews the feature. A reviewer must review the final
patch, resolve findings, and approve an explicit follow-up change to the gate
before any native managed mutation is enabled or live acceptance is claimed.

Review `txadmin.py`, the managed branches of `fxserverlaunch.py`, discovery hints,
and the new protocol tests. In particular, verify:

- URL parsing accepts only explicit literal loopback origins (localhost is
  normalized), disallows credentials, query/fragment/path injection, proxies
  and redirects. HTTP loopback assumes a trusted local machine; another local
  process taking over the configured port remains an important trust boundary.
- Saved profile mappings, returned panel data root and server.cfg are verified
  before a start request. The target-specific approval binds mode, URL, profile
  path, executable and selected config. No arbitrary `.bat` file is evaluated.
  A dedicated one-profile txData root is required because the settings API does
  not return an independently verifiable legacy profile name.
- Only fixed login, settings-read and start routes exist. No arbitrary console,
  resource, player, restart, stop or settings-write operations are exposed.
- Existing grants and the separate client-launch approval remain enforced.
  Requests cannot mint, extend, or substitute approval grants through MCP.
- Authentication is attempted once per operation. Cookies/CSRF stay in memory.
  Responses, credentials, cookies and raw network exceptions never reach outputs.
  The panel settings response may contain secrets in memory; it is not persisted.
- Control POST timeouts are ambiguous, are not retried, and never trigger direct
  fallback. The caller must inspect the panel before retrying.
- Startup uses a minimal child environment, fixed argv and loopback binding.
  Manager output is captured locally; log files can still contain server secrets
  and must not be published. A manager is never assumed to be the game worker.

Known acceptance limits: this is a Windows local-development integration with
an unversioned txAdmin API. Permissions `settings.view` and `control.server` are
required. Profile identity is checked from authenticated saved settings; this
does not independently prove socket ownership, character spawn, script health,
or that resources have stopped loading. The existing inventory-settling check
is a heuristic. New managed startup must receive a post-review live test.

After approval, test the exact reviewed revision using a disposable trusted
installation: reuse a running panel; cold-start its saved profile; verify OneSync
is preserved; reject a wrong panel, expired grant and bad credentials; confirm
the game worker and client connection. Keep private run reports local unless the
user separately approves publishing their contents.
