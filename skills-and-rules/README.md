# CFX development skills and rules

Install this package from its own folder with `python -m pip install .`.
Register this folder's `.mcp.json` using that Python environment.
Both folders carry the same shared runtime; installing either is sufficient.
Each configuration exposes only its own tools.

This package exposes development/reference/audit tools, skills and coding rules.
It excludes live server/client integration tools.

Enable either package or both. Do not also register the legacy combined
MCP configuration, which would duplicate tool registrations.

Source folder: `skills-and-rules`. Profile: `development`.
