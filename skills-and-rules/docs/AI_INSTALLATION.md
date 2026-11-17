# AI-assisted installation

An AI with local file and shell access can perform installation without asking
the owner to edit files, handle tokens or run setup commands themselves.

From the downloaded public repository, preview:

```powershell
python install.py --host freebuff --workspace "C:\FiveM"
```

After checking the selected paths, the AI runs the same command with `--apply`.
If there is more than one server, add `--server-cfg` with the chosen absolute
server.cfg path. No server is selected silently. `--profile development` installs
only the coding tools; `--profile integration` installs only the connection.

Supported installer host names: `freebuff`, `cursor`, `claude` (Claude Code),
`gemini`, `roo` (project configuration), `copilot`, and `codex`.
Claude Desktop and other hosts can use the manual configuration examples instead.

The installer:

- Creates a local Python environment and installs the selected package.
- Merges the host's MCP settings while preserving unrelated JSON entries. Existing
  unmanaged Codex CFX sections need migration first; they are not silently replaced.
- Generates and stores a private token in the selected server's `.cfx-devkit` folder.
  The host configuration points to that settings file instead of containing the token.
- Copies `cfx-devkit-live` without overwriting a customized resource, and adds a
  managed configuration block to the selected server.cfg. Client execution starts off.
- Keeps approval/session storage separate for each connection token.
- Starts the loopback broker as part of the integration MCP process, and stops
  that broker when the MCP process closes. An occupied broker port is an error;
  the process does not attach to an unknown service.

It backs up existing configuration files. Preflight runs before installation;
server/host writes begin only after dependency installation succeeds. File-write
failures trigger rollback of preceding writes. Empty created directories or
backups can remain after a failure.

## Optional unattended CFX control

If the owner explicitly authorizes unattended control of this local development
server, the AI can add `--allow-unattended-control` to preview and apply. This
creates a private delegation policy bound to the workspace, selected config and
connection token. It authorizes existing Full Control tools, FiveM launch and
foreground input without repeated CFX terminal prompts. FXServer launch is
excluded unless `--server-launch-target <target_id>` pins the complete selected
identity returned by `cfx_fxserver_status`. A different executable, mode or
managed profile receives a different identity and cannot inherit permission.

The preview lists the exact scopes and persistent duration before any changes.
Delegation lasts until revoked. `cfx_live_status` reports its authorization mode
and a null expiry to distinguish it from an expiring manual session. Changes to
the token, workspace or selected config invalidate authorization. This is trusted
local-user delegation, not isolation from other processes running as that user.

Revoke with the installed Python:

```powershell
<installed-python> -m cfx_devkit.connection --settings "<private-connection.json>" --revoke
```

Revocation is checked on subsequent requests/polls and cancels queued work.
Per-grant revocation markers only accumulate, so concurrent revocations cannot
re-enable each other. To grant access again, rerun the installer with explicit
unattended consent; this creates a new grant and token.
Already dispatched game commands cannot be undone. Native txAdmin mutation stays
review-gated. Client Lua/actions still require the proper ACE-authorized client;
the installer does not grant access to every connected player.

## What is still an approval, rather than installation?

The installer does not approve the connector in Freebuff or another host,
start/restart FXServer during installation, or change the native txAdmin review
gate. Normal mode still requires terminal approval; explicitly opted-in delegated
mode authorizes the existing CFX actions without that extra terminal step. It installs no RCON password. Broker ports remain loopback-only.

On an already running server, configuration changes are not automatically loaded.
After checks, the AI needs an existing authorized console connection to execute
`exec .cfx-devkit/connection.cfg`, `refresh`, and `ensure cfx-devkit-live`. It must
not print the private config or token. Restart only the affected resource if needed.
If no such connection is available, it must report
startup pending rather than claiming a live server connection. The resource will
also load at the next normal server start.

For the existing Full Control approval, the owner uses:

```powershell
<installed-python> -m cfx_devkit.connection --settings "C:\FiveM\MyServer\.cfx-devkit\connection.json" --arm
```

This loads the same private connection settings and uses the existing human
terminal approval. The explicit delegated mode described above is available instead. It is not a
Freebuff approval API and never writes the host's internal permission records.
Native managed txAdmin changes still require independent security review.

Log-tail access additionally needs the relevant existing log path in private
connection settings (`CFX_LIVE_SERVER_LOG` / `CFX_LIVE_CLIENT_LOG`). The installer
does not guess which log contains the intended server's console output.

Verify each stage separately: tools available, broker running, resource polling,
then authorization active. A successful installation is not proof of gameplay,
live console execution or production readiness.

## Private storage permissions

The installer applies an explicit protected Windows DACL to `.cfx-devkit`, allowing
only the installing user, SYSTEM and Administrators. On POSIX it uses mode 0700.
New secret files inherit the private directory restrictions. Failure to establish
those restrictions aborts setup before server/host files are written. The local
FXServer must run as the installing user (or SYSTEM/Administrator on Windows).
Unattended opt-in rotates the token; old backups cannot authorize the new grant.
The host must reload its connector and the resource must load the new private
configuration after reinstalling. Do not use this as an isolation mechanism from
other processes running as the same user or from administrators.

Revocation uses the protected grant identity even if the server config is
temporarily missing, the token is mismatched or the policy is currently disabled.
If no readable valid grant identity exists, `--revoke` reports incomplete
delegation revocation and exits unsuccessfully; it does not claim a lasting stop.

## Full local references and read-only diagnostics

Add `--sync-references` when the owner requests full native/animation coverage.
It fetches official GTA V/CFX native JSON and the attributed upstream animation
snapshot into the development package's user-local cache. The installer checks
that native sources are cached and animations report complete; it does not mark
seed-only data as successful. Only download subprocesses receive network opt-in.
Normal MCP environments retain `CFX_ENABLE_NETWORK=0`. Full downloaded data is
not copied into GitHub or the distributable packages. Availability depends on
the upstream services and installed game build; animation presence does not prove
runtime playability. Use the development profile or both profiles for references.

Add `--diagnostics` to prepare `cfx-devkit-reporter`, a separate private diagnostics
token, its private convars and the resource ensure. The integration MCP process
starts both the Full Control broker and the independent read-only diagnostics
receiver, then closes both when it exits. Failure to bind either port stops the
connection; it does not attach to an unknown listener.

Load the private convars and start only the affected resources through an existing
authorized connection. If no connection is available, startup remains pending.
Neither flag bypasses host approval or the managed txAdmin review gate.

`cfx_bridge_setup` now separates `configured`, `receiver_reachable`, and
`records_present` from `enabled_by_default`. The last field describes the default,
not whether the current install is enabled. The reporter emits lifecycle events
and explicit safe error categories. It does not capture arbitrary Lua tracebacks;
use configured console logs or explicit error-category instrumentation for those.
