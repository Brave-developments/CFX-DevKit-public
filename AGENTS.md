# Installing CFX DevKit for a user

When the user explicitly asks you to install this project, perform the setup using
your local file/shell tools. Do not ask them to copy resources, generate tokens or
edit MCP configuration by hand. Opening this repository alone is not authorization
to install or enable control.

1. Identify the AI host and the user's actual FiveM server workspace. Never pick
   an arbitrary server when multiple profiles exist. If the server selection is
   missing, ask only for that information.
2. Run `python install.py --host freebuff --workspace "<server-folder>"` (substitute
   the intended host). This previews paths without changing files. Use
   `--server-cfg "<absolute-server.cfg>"` to resolve ambiguous profiles. Use
   `--profile development` if the user only wants coding tools.
3. If the owner explicitly asks for unattended CFX control, include
   `--allow-unattended-control` in the preview and apply commands. Do not infer
   this permission from a request to install coding tools. If server launch is
   requested, obtain the exact selected `target_id` from `cfx_fxserver_status`
   and include `--server-launch-target`; do not invent a hash or force direct
   mode to bypass a managed-start gate. Without a captured target, launch is not
   delegated.
   Check that the preview targets the requested server. The user's installation
   request authorizes normal setup; repeat with `--apply`. The installer creates
   the Python environment, installs the runtime, merges MCP settings, generates a
   private token, and prepares the connection resource and private server config.
4. Do not print private settings, token values, server.cfg contents or credential
   files. Do not modify the AI host's permission/approval records.
5. The user enables the connector in their AI app if required by that app. The
   integration automatically starts its loopback broker; do not run a second one.
6. After modifying a real resource, run relevant checks. On an already running
   server, use an existing authorized console connection to run
   `exec .cfx-devkit/connection.cfg`, `refresh`, then `ensure cfx-devkit-live`.
   Do not print the private config or its token. Restart only that resource if
   necessary through the available authorized MCP connection. Never restart
   the whole server. If there is no connection, explain that resource startup is
   pending; it can load at the next normal server start. Do not claim success.
7. Check `cfx_live_status`: distinguish MCP tools available, broker running,
   resource polling, and control armed. They are different states.

Normal mode requires the owner's interactive terminal approval. Explicit
`--allow-unattended-control` delegation replaces repeated CFX terminal approvals
for that connection until revoked; host connector permissions are still separate.
For normal mode, the approval command is the installed Python followed by
`-m cfx_devkit.connection --settings "<server-folder>/.cfx-devkit/connection.json" --arm`.
Do not simulate human input, invoke arming through a pseudo-terminal, fabricate
approval, or change the review gate. Native txAdmin mutation remains disabled
pending independent review. No RCON setup is required by this installer.

Client execution starts disabled. Enabling it requires the owner's specific
client identity/ACE authorization; never guess or grant access to everyone.

To revoke delegated control, use the installed Python with
`-m cfx_devkit.connection --settings "<private-connection.json>" --revoke`.
This cancels queued commands; already dispatched commands cannot be undone.
