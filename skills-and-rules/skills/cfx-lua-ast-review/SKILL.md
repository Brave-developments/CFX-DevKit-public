---
name: cfx-lua-ast-review
description: Perform real grammar-based structural analysis of FiveM Lua events and identify candidate network trust boundary issues.
---
Call cfx_lua_ast_status and require availability. If unavailable instruct installation with pip install -e '.[analysis]' and never mislabel lexical scanning as AST. Use cfx_lua_ast_index to list concrete parsed invocations and syntax error nodes. Use cfx_lua_ast_network_review to identify server-side RegisterNetEvent calls for manual review. This is NOT a dataflow engine; do not infer authorization correctness or exploitable vulnerabilities without reading handler logic and testing on a controlled server.
