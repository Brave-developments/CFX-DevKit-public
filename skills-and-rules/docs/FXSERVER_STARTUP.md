# Start FXServer before launching FiveM (local Windows development only)

The startup adapter supports separate direct and native txAdmin plans. Managed
startup never falls back to `FXServer.exe +exec server.cfg` after an error.

**Review gate:** native txAdmin mutation is disabled in this revision pending the
independent security review required by AGENTS.md. Read-only authenticated profile
verification works against an already running panel. The manager/start path is
covered by isolated protocol tests but must not be enabled or described as live
accepted until reviewed. See [review checklist](TXADMIN_SECURITY_REVIEW.md).

## Native txAdmin mode

The existing status, start, and start-and-join tools share the managed plan; no
additional tools or separate MCP server are required. Configure the environment
that runs CFX-DevKit:

```powershell
$env:CFX_FXSERVER_MODE = 'txadmin'
$env:CFX_TXADMIN_PROFILE = 'C:\FiveM\txData\default\config.json'
$env:TXADMIN_URL = 'http://127.0.0.1:40120'
```

Also set the existing explicit executable/config overrides described below when
the workspace does not include the whole installation. Set `TXADMIN_USERNAME`
and `TXADMIN_PASSWORD` through your local host's secret/environment mechanism;
do not put their values in tracked files or tool arguments. The account needs
`settings.view` to verify identity and `control.server` to request startup.

`CFX_FXSERVER_MODE` accepts `auto` (default), `txadmin`, or `direct`. Automatic
discovery of a uniquely selected txAdmin profile chooses managed mode. Explicit
executable/config overrides alone cannot identify a profile; set
`CFX_TXADMIN_PROFILE` as well. A profile requires an explicit loopback panel URL;
the adapter never guesses among panels or selects a default port for you.

The profile must identify the selected server.cfg. The approval identity includes
the mode, executable/config, profile path and normalized panel URL. Changing them
invalidates the old grant. A legacy direct grant cannot authorize a managed start.

Use a dedicated txData folder containing one profile. The settings API does not
prove a legacy profile name, so multi-profile roots are rejected rather than
guessing between profiles that might share the same config. Separate txData
folders are also the upstream-recommended deployment layout.

After review, the managed sequence is:

1. Reuse the configured panel, or start the selected FXServer executable as the
   txAdmin manager with the saved profile and `TXHOST_DATA_PATH`/`TXHOST_TXA_PORT`.
   No `+exec`, batch evaluation, or arbitrary startup arguments are used.
2. Authenticate once through `/auth/password`, retaining cookies and CSRF in
   memory. Proxies and redirects are disabled; only explicit HTTP loopback URLs
   are accepted. Responses are bounded and never returned raw.
3. Read `/settings/configs` and verify its txData root and saved server.cfg match
   the selected profile. A responding port alone is not identity verification.
4. Request only `start` through `/fxserver/controls` if the game endpoint is not
   already reachable. Authentication, mismatch or request failures never trigger
   direct fallback, retries of the control POST, or a server restart.
5. Apply the existing bounded resource-inventory readiness check before requesting
   the separately approved FiveM launch. Player spawn remains unverified.

The manager receives a minimal OS environment plus its selected txAdmin settings;
MCP credentials, control tokens and unrelated environment secrets are excluded.
It binds loopback. The returned manager PID is not the game worker PID; process
metrics will not silently prefer the manager as a game worker.

Status reports reachability and whether credentials are configured, without
logging in by default. Call `cfx_fxserver_status` with `verify_txadmin: true` to
authenticate once and verify the selected profile without starting the manager
or game server. Do not repeat failed logins; inspect credentials before retrying.
`authenticated`/`profile_verified` are false until explicit verification.
An existing managed game endpoint is also authenticated and profile-verified
before the combined join workflow proceeds.

## Direct mode

Set `CFX_FXSERVER_MODE=direct` to explicitly request the original
`FXServer.exe +exec server.cfg` behavior. It does not start txAdmin or apply its
saved runtime settings such as OneSync. It needs no txAdmin/RCON credentials.
The toolkit does not infer or silently add OneSync settings.

## Automatic detection

Set `CFX_WORKSPACE_ROOT` to the folder containing your server installation, then call
`cfx_fxserver_status` or run `cfx-devkit fxserver-status`. No executable/config path
variables are required when the search finds exactly one unambiguous target.

The existing status tool now includes `discovery` with a state, candidates, and a
selected target. It finds `FXServer.exe`, `server.cfg`, and txAdmin profile JSON
using both `server.dataPath` and legacy `fxRunner.serverDataPath` fields with
`cfgPath`. It pairs a config with the unique executable under its nearest shared
installation directory. Profile paths must resolve within the search root.
It never reads server.cfg contents or returns profile secrets/startup arguments.

- `detected`: one complete target; the normal terminal approval can use it.
- `selection-required`: multiple configs; choose the intended executable and config.
- `missing-executable` / `not-found`: expand the workspace to include the installation or provide explicit paths.
- `incomplete`: a limit, unreadable folder or malformed/oversized profile prevented a complete search; automatic selection is disabled.

The search stays inside the configured workspace. It does not inspect other
drives or guess which process/profile belongs to a responding game port. Resource,
cache, log, dependency and build directories are skipped. Limits are eight directory
levels and 50,000 directory entries. Set
`CFX_DISCOVERY_MAX_ENTRIES` to 1–250,000 to change the entry budget. Reaching the
depth limit no longer prevents other queued profile folders from being inspected.
`truncated` also reports incomplete searches
when several candidates have already been found. External deployment paths,
ambiguous relative txAdmin deployment paths, nonstandard config names, and
installations outside the workspace require explicit selection. Startup remains
Windows-only; the MCP's other static tools retain their existing platform support.

## Explicit selection

These overrides take priority over automatic detection. Set both to real
**absolute** paths; an invalid or partial override is reported rather than replaced
with a guessed target:

```powershell
$env:CFX_FXSERVER_EXE = 'C:\\FXServer\\FXServer.exe'
$env:CFX_FXSERVER_CFG = 'C:\\FXServer\\server-data\\server.cfg'
```

Paths above are examples; use your actual Windows install and active `server.cfg`. txAdmin-managed instances may have different launch/profile conventions. This adapter starts a standalone FXServer process with `+exec`; do **not** use it to start a txAdmin-managed server unless you deliberately configured standalone startup.

Authorize each capability independently in a local interactive terminal:

For approval and immediate connection in one flow, run
`cfx-devkit connect --port 30120 --minutes 15`. It requests only missing approvals,
then continues automatically. The individual approval commands below are useful
when an MCP agent will perform the later operation separately.

```powershell
cfx-devkit fxserver-arm --port 30120 --minutes 15
cfx-devkit client-launch-arm --port 30120 --minutes 15
```

The FXServer approval records the exact executable/config pair as well as the port.
Switching targets requires a new approval. Older port-only FXServer grants must be
renewed. Detection itself is read-only and does not grant startup permission.
An already responding port cannot bypass an ambiguous target selection.

Then the agent invokes `cfx_dev_start_and_join` using port 30120. If the local `/info.json` endpoint is already serving a compatible response, no second FXServer process is launched. Otherwise the adapter starts FXServer. Within a shared bounded startup window (approximately 120 seconds), it requires both the HTTP endpoint and an advertised resource inventory that stays unchanged for 10 seconds before opening FiveM through Windows `fivem://connect/127.0.0.1:30120`. If startup does not settle, FiveM is not opened. A registered Windows protocol handler is required.

`server_ready`/`http_ready` in status mean **endpoint reachability only**. Status
does not run the settlement wait and returns `join_readiness: "not-evaluated"`.
The combined startup/join response returns the settlement observation separately.
For an installation with a known expected minimum, set `CFX_READY_RESOURCE_COUNT`
(1–10,000). A stable but incomplete six-resource advertisement will not pass a
minimum of 125. There is no hardcoded framework-specific expected count. Without
an explicit minimum, the default is one resource plus the stability window.
Inventory stability is a heuristic, not proof that all scripts finished loading,
dependencies are valid, or gameplay works; `resource_health_verified` remains false.

## Startup logs

MCP-started processes write combined stdout/stderr to a unique
`.cfx-devkit/logs/fxserver-*.log` inside the configured workspace. The startup
response includes the workspace-relative `log_path`; the combined join response
retains it under `server_start`, including on timeout. Pass that path to
`cfx_server_stability_log` for a sanitized summary. Existing externally started
servers are reused and do not gain a fabricated toolkit log.

Raw server logs may contain sensitive information. They are excluded from source
scans and version control; the tool creates them with restrictive file mode where
supported. Windows access control follows the workspace's inherited ACLs. The
toolkit does not rotate an actively written child-process log; manage retention
locally. Raw output is not returned by the startup tool.

Read server status through `cfx_fxserver_status`; revoke with `cfx-devkit fxserver-disarm` and `cfx-devkit client-launch-disarm`.

**Important:** HTTP readiness does not confirm a player joined or that the current FXServer process belongs to the MCP. Existing server instances are never killed. FXServer executable must be named FXServer.exe. Configuration must be an existing file named server.cfg. No shell commands, arbitrary arguments, remote hosts, or resource-administration permissions are granted.

Upstream references: [txAdmin profile layout](https://github.com/citizenfx/txAdmin/blob/master/core/boot/setup.ts)
and [txAdmin host configuration](https://github.com/citizenfx/txAdmin/blob/master/docs/env-config.md).
