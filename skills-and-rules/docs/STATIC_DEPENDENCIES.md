# Static dependency and file coverage checks

`cfx_validate_manifest` resolves its resource dependencies across the configured
workspace. `cfx_dependency_graph` uses the same analyzer for the selected tree.
Both report errors for a client-visible resource depending on a resource marked
`server_only`, and propagate a bounded set of known failures through dependencies.
The metadata flag is recognized by presence of a literal value, including
`server_only 'no'`; it is not interpreted as a yes/no option.

Literal `provide` aliases are resolved when they identify one resource. Duplicate
resource names or providers are reported as ambiguous rather than guessed.
Missing dependencies may exist outside the workspace and require review. Runtime
constraints such as `/onesync` remain in the dependency list; their live state is
not established by static analysis.

The analyzer never executes a manifest. Computed values, conditional declarations,
unsupported expressions and `client_only` custom metadata are explicitly marked
unverified. `client_only` is not used as an official Cfx runtime-side boundary.
Read `analysis_complete`, source scan coverage, findings and result limits together;
a complete file walk does not establish complete semantic or runtime validation.

Asset inventories include binary asset filenames without reading binary content.
They use a bounded walk that prunes symlinks and Windows reparse points before
descent and checks resolved file paths. Skipped links are counted in
`linked_paths_skipped` and prevent a complete-coverage claim. Each resource reports
`inventory_coverage` and whether its missing-file list is conclusive within that
inventory. A capped or inaccessible inventory cannot prove a declared file absent.
Indirect manifest/config reads are also checked against the workspace boundary
and source byte limit. These checks are not isolation from a hostile local user
changing filesystem links concurrently.

References: [official resource manifest reference](https://docs.fivem.net/docs/scripting-reference/resource-manifest/)
(`server_only`, `dependency`, `provide`). Validate runtime behavior in an owned
development environment before declaring a server healthy.
