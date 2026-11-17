# CFX txAdmin integration

Install this package from its own folder with `python -m pip install .`.
Register this folder's `.mcp.json` using that Python environment.
Both folders carry the same shared runtime; installing either is sufficient.
Each configuration exposes only its own tools.

This package exposes server/client integration and live server diagnostics only.
It includes no skills or coding rules. Existing approval and security gates still apply;
native txAdmin mutation remains disabled pending independent review.

Enable either package or both. Do not also register the legacy combined
MCP configuration, which would duplicate tool registrations.

Source folder: `txadmin-integration`. Profile: `txadmin`.
