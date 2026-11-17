# CFX DevKit — FiveM tools for AI coding assistants

Connect your AI assistant to FiveM development tools, or to your local development
server and game client. **FiveM / GTA V only. Python 3.10+.**

This repository contains two packages. Enable either one or both.

| Folder | What it is for | Included |
| --- | --- | --- |
| [skills-and-rules](skills-and-rules/README.md) | Writing, reviewing and improving FiveM scripts | **51 MCP tools**, **19 skills**, **6 coding rules**, snippets and starter templates |
| [txadmin-integration](txadmin-integration/README.md) | Connecting to a local FXServer/FiveM development environment | **24 MCP tools** for status, logs, diagnostics, client interaction and authorized control; no coding skills, rules, snippets or starter templates |

The tool lists do not overlap. Both enabled gives **75 tools**. The integration's
`examples` folder contains the connection/control resources that run on FXServer.

## What can I ask the AI to do?

**Skills and rules:** “Check this resource's manifest and dependencies,” “Find the
correct native,” “Review my Lua event security,” or “Preview a QBCore resource.”

**Server integration:** “Check my local server status,” “Read the configured
server console log,” or “Report server process performance.” Resource/console
commands and in-game actions need the relevant integration and local approval.

**Release status: release candidate / developer preview.** Automated protocol
checks do not establish live gameplay acceptance. Native txAdmin-managed startup
is currently disabled pending independent security review. MCP setup does not
unlock it. See [startup support](txadmin-integration/docs/FXSERVER_STARTUP.md) and
[review status](txadmin-integration/docs/TXADMIN_SECURITY_REVIEW.md).

## Ask your AI to install it

Give an AI with local file/shell access this request:

> Install CFX DevKit for Freebuff and allow unattended CFX control of my local
> development server, download the full native/animation references and set up
> read-only runtime diagnostics. Run the installer
> preview, verify the target server, then apply setup. Handle files, dependencies
> and tokens yourself; tell me which connection or approval steps remain.

From a downloaded checkout, the AI runs `python install.py --host freebuff
--workspace "C:/FiveM"`, checks the preview, then repeats with `--apply`.
If the owner explicitly delegates control, include `--allow-unattended-control`
in both commands. This authorizes privileged console/Lua tools, FiveM launch and
foreground input until revoked for that server. FXServer launch additionally needs
`--server-launch-target <target_id>` captured from `cfx_fxserver_status`; changing
the executable, mode or managed profile invalidates that launch delegation. It is not enabled by default.
For full native/animation references add `--sync-references`. For the read-only
runtime reporter add `--diagnostics`. The AI handles their setup; downloaded
reference data stays local and normal MCP network access remains off. Diagnostics
report lifecycle events and explicit categories, not every console traceback.
Other installer hosts: `cursor`, `claude` (Claude Code), `gemini`, `roo`, `copilot`,
and `codex`. Add `--server-cfg` if multiple server profiles exist.

This automates installation, private token generation, host configuration and the
server connection resource. The integration starts its own local broker. The
opt-in delegated mode removes CFX terminal arming; normal installations keep it.
The AI app still controls its own connector approvals. Native txAdmin mutation
remains review-gated. See
[AI installation details](txadmin-integration/docs/AI_INSTALLATION.md).
The opt-in delegation changes passed an [independent code/security review](txadmin-integration/docs/UNATTENDED_SECURITY_REVIEW.md); live server/gameplay acceptance remains separate.

## Already installed but the AI asks you to type an arming phrase?

Ask it to check `cfx_live_status`. With `armed: true` and
`authorization_mode: owner-delegated-until-revoked`, unattended Full Control is
already authorized. The manual `arm()` functions remain for legacy/manual mode;
they are not a required step for an active delegated connection. The AI should
use the available Full Control tools rather than the separate manual controller.
If the mode is locked, check the installed delegation policy and selected target.

## 1. Download and install

Install Git and Python 3.10 or newer, then run these commands in a terminal.
The Windows example creates a private Python environment inside the checkout:

```powershell
git clone https://github.com/Brave-developments/CFX-DevKit-public.git
cd CFX-DevKit-public
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install ./skills-and-rules
.\.venv\Scripts\python.exe -c "import sys; print(sys.executable)"
```

Keep the Python path printed by the last command. Use it as `command` in your AI
platform's MCP settings. This avoids relying on that app finding the right Python.

- **Development only or both packages:** install `./skills-and-rules` as above.
- **Integration only:** replace the install target with `./txadmin-integration`.
- Both packages carry the same Python runtime/distribution. Installing the
  development package supplies the coding assets needed when using both profiles;
  do not install the integration package over it in the same environment.
- Optional Lua AST and process-metric dependencies:
  `.\.venv\Scripts\python.exe -m pip install "./skills-and-rules[analysis,monitoring]"`.
  For integration-only metrics, use `"./txadmin-integration[monitoring]"` instead.

On macOS/Linux, use `.venv/bin/python` instead of `.venv\Scripts\python.exe`.
Reference/audit tools can run there; Windows client launch/input tools require Windows.
After pulling updates, repeat the install command for your chosen package.

## 2. Add the MCP servers to your AI platform

The GitHub URL is the **source download**, not an HTTP MCP endpoint. These servers
run locally over **stdio**. Your AI app starts Python; no hosting or public port
is needed for the MCP connection itself.

In the examples below, replace:

- `C:/Tools/CFX-DevKit-public/.venv/Scripts/python.exe` with your printed Python path.
- `C:/FiveM` with the existing folder you want the tools to inspect. For server
  auto-discovery, choose a folder containing the relevant FXServer installation
  and txData profiles. Multiple targets require explicit selection.

Merge entries into existing settings; preserve your other servers. Remove an
entry if you only want the other package. Do not also register the older combined
`cfx_devkit.server` configuration, which would expose duplicate tools.

### Cursor, Claude Desktop, Gemini CLI, Cline, Roo Code and Freebuff

Use this JSON in the location listed below:

```json
{
  "mcpServers": {
    "cfx-development": {
      "type": "stdio",
      "command": "C:/Tools/CFX-DevKit-public/.venv/Scripts/python.exe",
      "args": ["-m", "cfx_devkit.profiles", "development"],
      "env": {
        "CFX_WORKSPACE_ROOT": "C:/FiveM",
        "CFX_ENABLE_WRITES": "0",
        "CFX_ENABLE_NETWORK": "0"
      }
    },
    "cfx-txadmin": {
      "type": "stdio",
      "command": "C:/Tools/CFX-DevKit-public/.venv/Scripts/python.exe",
      "args": ["-m", "cfx_devkit.profiles", "txadmin"],
      "env": {
        "CFX_WORKSPACE_ROOT": "C:/FiveM",
        "CFX_ENABLE_WRITES": "0",
        "CFX_ENABLE_NETWORK": "0"
      }
    }
  }
}
```

| Platform | Where to put the configuration | Verify |
| --- | --- | --- |
| [Cursor](https://cursor.com/help/customization/mcp) | Project `.cursor/mcp.json`, or user `~/.cursor/mcp.json` | Open its MCP list, enable the entries and check their tools |
| [Claude Desktop](https://modelcontextprotocol.io/docs/develop/connect-local-servers) | Settings → Developer → Edit Config; Windows `%APPDATA%\Claude\claude_desktop_config.json`, macOS `~/Library/Application Support/Claude/claude_desktop_config.json` | Fully restart the app and inspect connected tools |
| [Gemini CLI](https://geminicli.com/docs/tools/mcp-server/) | Project `.gemini/settings.json`, or user `~/.gemini/settings.json` | Run `/mcp` in Gemini |
| [Cline](https://docs.cline.bot/mcp/mcp-overview) | Open MCP Servers and its configuration editor; merge the entries | Check both servers connect and list tools |
| [Roo Code](https://docs.roocode.com/features/mcp/using-mcp-in-roo) | MCP settings → Edit Project MCP (`.roo/mcp.json`), or Edit Global MCP | Check each connection in the MCP panel |
| [Freebuff](https://freebuff.com/perspectives/docs/add-an-mcp-server-in-freebuff-desktop-settings) | Use the app's MCP settings to add the JSON configuration, where supported by your version | Enable/approve the servers and inspect their tools; UI availability varies by build |

### Codex

Add these entries to `~/.codex/config.toml`, or the trusted project's
`.codex/config.toml`. Paths use forward slashes to keep Windows TOML escaping simple.

```toml
[mcp_servers.cfx_development]
command = "C:/Tools/CFX-DevKit-public/.venv/Scripts/python.exe"
args = ["-m", "cfx_devkit.profiles", "development"]

[mcp_servers.cfx_development.env]
CFX_WORKSPACE_ROOT = "C:/FiveM"
CFX_ENABLE_WRITES = "0"
CFX_ENABLE_NETWORK = "0"

[mcp_servers.cfx_txadmin]
command = "C:/Tools/CFX-DevKit-public/.venv/Scripts/python.exe"
args = ["-m", "cfx_devkit.profiles", "txadmin"]

[mcp_servers.cfx_txadmin.env]
CFX_WORKSPACE_ROOT = "C:/FiveM"
CFX_ENABLE_WRITES = "0"
CFX_ENABLE_NETWORK = "0"
```

Reload the client connection after saving. The CLI can inspect registrations with
`codex mcp list`. See the [official Codex MCP guide](https://developers.openai.com/codex/mcp/).

### Claude Code

From your FiveM project, register the profiles using your installed Python path:

```powershell
claude mcp add --scope user --env CFX_WORKSPACE_ROOT=C:/FiveM --transport stdio cfx-development -- C:/Tools/CFX-DevKit-public/.venv/Scripts/python.exe -m cfx_devkit.profiles development
claude mcp add --scope user --env CFX_WORKSPACE_ROOT=C:/FiveM --transport stdio cfx-txadmin -- C:/Tools/CFX-DevKit-public/.venv/Scripts/python.exe -m cfx_devkit.profiles txadmin
```

Quote paths containing spaces. Use `/mcp` in Claude Code to inspect connections.
For a shared project setup, use the common JSON in a project-root `.mcp.json`
instead. See [Claude Code's MCP guide](https://code.claude.com/docs/en/mcp).

### VS Code / GitHub Copilot

Open **MCP: Add Server**, select a local command/stdio server, and supply the
Python command, profile arguments and environment from the JSON above.

For current Copilot configurations, use the same `mcpServers` JSON in user
`~/.copilot/mcp-config.json`, or the workspace-root `.mcp.json` when offered.
Older/editor-managed `.vscode/mcp.json` uses `servers` rather than `mcpServers`;
use the format for your active harness instead of mixing them. See Microsoft's
[configuration reference](https://code.visualstudio.com/docs/agents/reference/mcp-configuration).

### Devin Desktop / Windsurf users

For current Devin Local, open **Customize → MCPs → This computer** and open the
configuration for the intended scope. Project configuration is
`.devin/mcp_config.json`; use its `mcpServers` object with the commands, arguments
and environment above. Omit the optional `type` fields: Devin infers stdio from
`command`. Refresh the MCP list and approve the tools you want to use.

Older Windsurf builds can have different locations; follow your installed
version's settings rather than creating both old and new config files. See
[Devin Local customizations](https://docs.devin.ai/desktop/devin-local/customizations)
and [MCP configuration](https://docs.devin.ai/cli/extensibility/mcp/configuration).

### Other AI platforms

A host must support **local stdio MCP processes** to launch these packages.
Supply the same executable, arguments and environment through its MCP settings.
If your host uses a different JSON wrapper, adapt that wrapper to its documentation.
A cloud-only connector accepting an HTTP URL cannot directly launch this local
Python server; this repository does not supply a hosted HTTP MCP endpoint.

These are configuration instructions, not a claim that every listed app/version
has passed live UI acceptance. Isolated protocol checks cover both profiles.

## 3. Install skills and rules separately, if wanted

An MCP connection exposes tools. It does **not** automatically install skill
instructions or coding rules. Those files live in `skills-and-rules/`.

Copy the individual skill directories, preserving each `SKILL.md` and any
`agents` metadata, into your host's skill directory:

| Host | Project skills destination |
| --- | --- |
| [Codex](https://developers.openai.com/codex/skills/) | `.agents/skills/`; user-wide skills can use `~/.agents/skills/` |
| [Cursor](https://cursor.com/docs/skills) | `.cursor/skills/` |
| [Claude Code](https://code.claude.com/docs/en/skills) | `.claude/skills/` |

For Cursor, copy the six `.mdc` files from `skills-and-rules/rules/` to your
project's `.cursor/rules/`. For other hosts, adapt their contents to the host's
instruction format; a `.mdc` file is not a universal MCP rule format.
Plugin-capable hosts can use the package's host manifests where supported.
Avoid installing both the plugin's skills and manual copies of the same skills.

## 4. Connect the server integration

Registering `cfx-txadmin` alone does not install a FiveM resource, configure a
console log or authorize server changes.

1. Ask for `cfx_fxserver_status` first to inspect discovery and reachability.
2. Follow [server discovery/setup](txadmin-integration/docs/FXSERVER_STARTUP.md)
   for the correct executable, config and txAdmin profile. Native managed mutation
   remains gated; do not bypass that gate.
3. For server console output, use `cfx_live_log`: it reads a configured log file
   or falls back to the native console buffer when no server log path is set.
   Client logs still need a client log source; see [Full Control setup](txadmin-integration/docs/FULL_CONTROL.md).
4. For resource lifecycle diagnostics, install the reporter described in
   [development diagnostics](txadmin-integration/docs/DEV_BRIDGE.md).
5. For authorized console/resource/in-game actions, install the matching connection
   resource and complete its local approval setup:
   [resource control](txadmin-integration/docs/CONTROL_BRIDGE.md) or
   [Full Control](txadmin-integration/docs/FULL_CONTROL.md).

Use your own local development server. Keep credentials/tokens in private local
settings, never in GitHub. Keep broker ports on loopback. Leave writes and network
downloads disabled unless a specific task needs them and you authorize it.

## Check that it worked

- Development profile: **51 tools**; integration profile: **24 tools**.
- Try `cfx_native_status` or `cfx_scan_project` for development.
- Try `cfx_fxserver_status` for integration; a clear “not configured/not running”
  result still means the MCP connection itself worked.
- `ModuleNotFoundError`: use the same Python executable you installed into.
- Wrong files/server: correct `CFX_WORKSPACE_ROOT` and select an explicit target.
- Startup/control denied: inspect setup, authorization and review status; do not
  treat a connected MCP server as proof that game/server control is enabled.

Both packages are independently selectable; the personal working copy, private
QA evidence and local credentials are not part of this public repository.

Platform setup references checked on 17 November 2026; app menus can change.
