# Opt-in FiveM development control (experimental)

**Not full/unrestricted server control.** This is a separately configured, human-approved resource lifecycle controller for a development FXServer only. The existing read-only diagnostic bridge is unchanged.

## Architecture

MCP `cfx_control_propose` -> short-lived SQLite proposal -> human terminal `cfx-devkit control-approve <id>` -> private loopback broker 127.0.0.1:8766 -> server-only FiveM controller resource -> revalidate resource/action against FXServer private convars -> ExecuteCommand("restart <approved resource>") -> observed GetResourceState returned via authenticated HTTP -> MCP `cfx_control_result`.

The MCP agent **cannot approve a proposal**. Approvals require a real interactive terminal, manually typing `APPROVE restart test-resource` (or `REJECT ...`). Every proposal expires after ten minutes. Dispatched requests are not automatically retried. Observed resource states are not proof of full functional tests.

## Local setup (same host as FXServer)

Generate a unique private token:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

In the Python controller's and MCP server's private process environment:

```powershell
$env:CFX_CONTROL_ENABLE="1"
$env:CFX_CONTROL_TOKEN="<unique private token>"
$env:CFX_CONTROL_RESOURCES="test-garage,dev-livery"
$env:CFX_CONTROL_ACTIONS="restart,ensure"
python -m cfx_devkit.cli control-broker
```

Copy `examples/cfx-devkit-controller` into your **owned development server** resource folder. Add to the server's **private** server.cfg (use `set`, never replicated `setr`):

```cfg
set devkit_control_enable 1
set devkit_control_token "<same private token>"
set devkit_control_resources "test-garage,dev-livery"
set devkit_control_actions "restart,ensure"
ensure cfx-devkit-controller
```

Request an action in Codex, Cursor or Claude using the `cfx_control_propose` tool. Approve it **yourself** in a second terminal:

```powershell
python -m cfx_devkit.cli control-status
python -m cfx_devkit.cli control-approve <request_id>
# Type exactly: APPROVE restart test-garage
python -m cfx_devkit.cli control-status <request_id>
```

To deny: `control-reject <request_id>` then type `REJECT restart test-garage`.

## Security boundaries

* Both broker and FXServer must be on the same trusted **development** machine. Never forward or tunnel port 8766; the broker binds only 127.0.0.1 and authenticates all requests with a 32+ character shared token.
* The MCP can propose and read results only; no approve action exists in MCP or HTTP.
* Resource names must be in two explicit private allowlists. Only the verbs `restart`, `ensure`, `stop` are possible. No general RCON, Lua eval, SQL, SSH, shell, player controls or secrets exposure.
* The controller has **no client scripts or player-triggered events**. It cannot control other server settings. Current host/prod-vs-dev identity is NOT independently attested; the owner must ensure it is an isolated dev server.
* An attacker already controlling the machine, token or installed FXServer resources can potentially defeat these protections. Treat the token and resource allowlists as privileged.
* GitHub CI tests the isolated broker and Lua syntax, not a real FXServer. **Live acceptance is still required** before deployment.
