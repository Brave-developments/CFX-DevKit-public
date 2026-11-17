# Approved FiveM localhost launch (Windows only)

This optional development feature starts the installed FiveM client and requests a join to `127.0.0.1:30120` (or another approved local FXServer port). It **does not** require txAdmin or RCON credentials. It does **not** grant server resource administration or Full Control.

## Setup

For a single command that asks for any missing approval and then immediately
requests the connection, use `cfx-devkit connect --port 30120 --minutes 15`.
It reuses valid grants and an already running server. If the server needs starting,
it requests the separate server approval too. There is no return-to-chat step
after entering the phrase. See [target discovery](FXSERVER_STARTUP.md) to select
the intended server installation.

The individual approval and MCP steps below remain available for agents that
need separate control over the session:

1. Use a Windows computer with FiveM installed at `%LOCALAPPDATA%\FiveM\FiveM.exe`, or set `CFX_FIVEM_EXE` to the actual executable.
2. Ensure your own FXServer is running on the same machine. No remote server addresses are supported.
3. From an **interactive local terminal**, grant launch permission for 15 minutes:

   `cfx-devkit client-launch-arm --port 30120 --minutes 15`

4. Type the exact displayed approval phrase.
5. Your connected MCP agent can call `cfx_fivem_launch_preview` then `cfx_fivem_launch_local` with `port=30120`.
6. Revoke permission immediately with `cfx-devkit client-launch-disarm`, or let it expire. Query `cfx-devkit client-launch-status` to inspect expiry.

## Evidence and limitations

The adapter hands the connection URI to Windows Explorer, which launches the registered FiveM handler from the desktop shell. Calling ShellExecute directly from a console-attached agent can still trigger FiveM's “should be launched directly from the shell or a web browser” error. Do not start FiveM.exe directly or add `-cl2` as a workaround.

Explorer's request-process PID is not the game PID, so the tool returns no client PID. A successful protocol launch request is **not** evidence that FiveM connected or joined a session. To establish an actual join, inspect authorized client log/bridge evidence or verify in-game. Do not treat an FXServer port being reachable as proof of joining.

Permission applies only to client launch; it never enables `cfx_live_run` or arbitrary Lua. The tool validates the FiveM installation and opens the fixed `fivem://connect/127.0.0.1:<port>` URI through its registered Windows protocol handler, with a loopback-only destination. It invokes no command shell and does not obtain txAdmin/RCON credentials.

This adapter does not restart the FXServer process. Resource lifecycle control remains governed separately by `cfx_control_propose` and the approved controller bridge.

**Not suitable for unattended production administration.** Do not run with elevated privileges. Use only on a trusted local Windows development machine. Real FiveM client acceptance requires a Windows host with FiveM and the local game server installed.
