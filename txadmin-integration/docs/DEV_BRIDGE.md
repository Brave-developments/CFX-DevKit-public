# Local development bridge (v1.0 release candidate)

This bridge is an **optional, loopback-only diagnostic receiver** on the FXServer machine. It never issues commands to a running server, has no client routes or permissions, and only accepts limited sanitized resource lifecycle/error-category messages. It is not a substitute for txAdmin.

## Configuration

Create a random secret **on the FXServer machine**:

~~~powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
~~~

Start the Python diagnostic bridge in the same host/machine as the development FXServer. Pass the generated secret through the process environment rather than hard-coding it:

~~~powershell
$env:CFX_BRIDGE_ENABLE = "1"
$env:CFX_BRIDGE_TOKEN = "<unique random secret>"
python -m cfx_devkit.devbridge --port 8765
~~~

Put the same secret in **private development server.cfg**, never in a client script and never with a replicated `setr` variable:

~~~cfg
set devkit_bridge_enable 1
set devkit_bridge_token "<unique random secret>"
ensure cfx-devkit-reporter
~~~

Copy `examples/cfx-devkit-reporter/` into the development resources directory. The reporter sends reports to **127.0.0.1:8765** only. If FXServer is remote or containerized, localhost refers to that server/container, not the developer laptop. Do not expose port 8765 on a public interface and do not forward it externally.

Supported reports have a strict whitelist: `resource_started`, `resource_stopped`, `heartbeat`, `resource_error`, and only `resource` names or short predefined `detail` categories. No player IDs, IP addresses, names, arbitrary messages, or tracebacks can be transmitted/stored by this reporter. Every POST requires a 32+ character shared token and is capped at 1 KiB. Logs rotate after 2 MB.

Query the observed sanitized records with:
~~~powershell
python -m cfx_devkit.cli bridge-recent
~~~
or with the MCP `cfx_bridge_recent` tool. This only reads local previously received records; it does **not** prove that the bridge is still live.

## Security checks

- Network is **disabled by default** (`CFX_BRIDGE_ENABLE=1` is required to start).
- HTTP server explicitly binds 127.0.0.1; remote binding cannot be configured.
- All routes require `X-CFX-DevKit-Token`; never log that header.
- Accepts only small, whitelisted data. No remote command endpoint.
- Server-side Lua code uses `GetConvar` with a private `set` key, never a replicated convar.
- The bridge does not modify FiveM resources, kick players, execute scripts or restart services.
- HTTP security does not replace OS controls; localhost programs could potentially observe the endpoint, so rotate secrets and run it only on trusted development machines.

## Manual acceptance (must run on your own test server)

1. Start the Python receiver and verify the local health endpoint with token.
2. Start the developer FXServer and ensure the reporter resource, with `devkit_bridge_enable=1`.
3. Start and stop a known test resource. Verify two events in `cfx_bridge_recent`.
4. Confirm no player identifiers/secret values appear in records.
5. Disable the dev bridge and ensure no further reports are delivered.
6. Remove the resource before production deployment.

Passing CI proves the HTTP contract in an isolated test process. CI does **not** perform steps 2â€“6 against a real FiveM runtime.

## Automatic installation

Use `install.py --diagnostics` to let an authorized AI prepare the reporter,
private token and host settings. See [AI installation](AI_INSTALLATION.md).
The integration process starts/stops the receiver automatically. The resource
still needs to be loaded on the selected server. `cfx_bridge_setup` reports current
configuration, authenticated receiver reachability and recorded history separately.
This is lifecycle/category telemetry, not a generic traceback or player-data feed.
