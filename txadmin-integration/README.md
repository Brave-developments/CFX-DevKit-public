# CFX txAdmin integration

Install this package from its own folder with `python -m pip install .`.
Register this folder's `.mcp.json` using that Python environment.
When using both profiles, install skills-and-rules for its coding assets.
Each configuration exposes only its own tools.

This package connects an AI tool to a local FiveM/FXServer development environment.
It exposes console-log reading, server health/process diagnostics, local startup and
client connection tools. Authorized resource and console actions use the opt-in
control integration and require its server resource and approval.

It includes no skills, coding rules, snippets or starter templates. The examples
folder contains the actual connection/control resources, not general script templates. Existing approval and security gates still apply;
native txAdmin mutation remains disabled pending independent review.

Enable either package or both. Do not also register the legacy combined
MCP configuration, which would duplicate tool registrations.

Source folder: `txadmin-integration`. Profile: `txadmin`.
