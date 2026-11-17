# CFX DevKit Full Control

**Developer preview:** This feature has passed isolated tests but has **not yet been verified against a running FiveM client and FXServer**. It is designed for an owned, disposable development server running on the same computer as CFX DevKit.

## Scope

An AI assistant may now inspect FXServer status, resource states and developer client IDs, issue arbitrary FXServer console commands, execute Lua in server/client resource contexts, run built-in game actions, and read configured client/server logs. These are high-privilege operations. They can modify game resources and server state.

Full Control does **not** automatically include a Windows/OS shell, SSH, database credentials, desktop screenshot capture or browser DevTools automation.

## Unattended installation option

An owner can explicitly opt into `install.py --allow-unattended-control`. This
creates revocable, server-bound trusted-local-user delegation instead of requiring
repeated terminal arming. See [AI installation](AI_INSTALLATION.md). Without that
option, the manual approval steps below remain required. Host MCP approval is
separate; native txAdmin mutation remains review-gated.

## Installation

In PowerShell, generate one private random token:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

In the shell launching CFX DevKit MCP and the broker, set:

```powershell
$env:CFX_LIVE_ENABLE="1"
$env:CFX_LIVE_MODE="full"
$env:CFX_LIVE_TOKEN="<secret>"
$env:CFX_LIVE_SERVER_LOG="C:\DevFXServer\server.log"  # optional, must exist
$env:CFX_LIVE_CLIENT_LOG="C:\path\to\CitizenFX_log.log"  # optional
python -m cfx_devkit.cli live-broker
```

Copy `examples/cfx-devkit-live` into the **local development FXServer** resources directory and add to its **private server.cfg**:

```cfg
set devkit_live_enable 1
set devkit_live_mode "full"
set devkit_live_token "<same secret>"
setr devkit_live_client_enabled 1
add_ace identifier.license:<YOUR_DEV_LICENSE_ID> devkit.live allow
ensure cfx-devkit-live
```

The secret stays in **private `set`**, never `setr`. Only the harmless on/off flag is replicated. Only specifically ACE-authorized test clients may receive client-side execution requests. Never expose or forward TCP port 8767.

In **a separate interactive terminal** with the same CFX_LIVE_* environment variables, arm a short session:

```powershell
python -m cfx_devkit.cli live-arm --minutes 15
# Type: ARM FULL FIVEM CONTROL
```

An MCP agent cannot arm control itself. All commands dispatched during this 15-minute window are permitted without approving each one separately. A session expires automatically; maximum duration is 60 minutes.

## Tools

- `cfx_live_status`: active authorization and recent FXServer polling
- `cfx_live_run`: execute one developer request; choose `kind` and a JSON string `payload_json`
- `cfx_live_result`: inspect a request by its 32-character ID
- `cfx_live_log`: bounded tail of an explicitly configured log file

Kinds and payloads:

| Kind | Example JSON payload string | Target |
| --- | --- | --- |
| `server_info` | `{}` | none |
| `server_resources` | `{}` | none |
| `server_players` | `{}` | none |
| `server_command` | `{"command":"restart test-resource"}` | none |
| `server_lua` | `{"code":"return GetNumResources()"}` | none |
| `client_lua` | `{"code":"return GetEntityCoords(PlayerPedId())"}` | ACE-authorized numeric player ID |
| `client_action` | `{"action":"position"}` | ACE-authorized numeric player ID |
| `client_action` | `{"action":"teleport","x":1.0,"y":2.0,"z":30.0}` | ACE-authorized numeric player ID |

Other built-in client actions: `freeze`, `unfreeze`, `clear_tasks`, `heal`, `play_animation` (requires `dictionary` and `clip`). The `payload_json` argument contains the JSON object **as a string**, not as a nested structured object.

For example: `cfx_live_run(kind="server_command",payload_json="{\"command\":\"status\"}")`. Poll `cfx_live_result(id="<id>")` for the result; a command invoked successfully is **not proof** that in-game behavior has been validated.

## Emergency shutdown

```powershell
python -m cfx_devkit.cli live-disarm
```

Disarm cancels queued work and stops new dispatches. Already dispatched commands cannot be undone. Stop the broker and disable `devkit_live_enable`, `devkit_live_client_enabled` and remove `cfx-devkit-live` from the development server to fully disable the feature.

## Security and acceptance

Broker: token-protected HTTP bound only to `127.0.0.1:8767`. Command body is erased from the queue when dispatched. Sessions must be manually armed, expire quickly and can be disarmed. Both FXServer and Python must be on the **same trusted development machine**, not behind a public tunnel or forwarded port.

**This is powerful enough to damage an FXServer installation if misused.** A malicious local process, compromised token or already-malicious game resource may bypass portions of the controls. Do not enable it on a production/public server.

Before calling it live-ready, test an authenticated poll, `server_info`, a harmless Lua expression, a resource restart, an authorized client action, an unauthorized client refusal, log inspection, session expiry and emergency disarm in a real disposable FiveM environment.
