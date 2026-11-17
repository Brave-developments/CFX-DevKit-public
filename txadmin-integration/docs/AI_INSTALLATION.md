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

## What is still an approval, rather than installation?

The installer does not approve the connector in Freebuff or another host, arm a
Full Control session, start/restart FXServer, or change the native txAdmin review
gate. It installs no RCON password. Broker ports remain loopback-only.

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
terminal approval. Automatic arming and a replacement app-only approval flow are
not implemented by this installer. Replacing that authorization design requires
the independent review required by the project instructions.

Log-tail access additionally needs the relevant existing log path in private
connection settings (`CFX_LIVE_SERVER_LOG` / `CFX_LIVE_CLIENT_LOG`). The installer
does not guess which log contains the intended server's console output.

Verify each stage separately: tools available, broker running, resource polling,
then authorization active. A successful installation is not proof of gameplay,
live console execution or production readiness.
