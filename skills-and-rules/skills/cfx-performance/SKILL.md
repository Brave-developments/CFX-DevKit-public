---
name: cfx-performance
description: Investigate FiveM server health, process CPU/memory, hitches and measured resource tick milliseconds.
---
Use cfx_audit_performance. Prefer event-driven work and idle waits when no real-time update is necessary. Consult native lookup where applicable, and require actual FiveM profiler evidence before claiming optimization.

Use `cfx_server_health` for loopback HTTP availability and client/resource counts,
and `cfx_server_process_metrics` for CPU/RSS/threads/uptime of one FXServer PID.
If several processes are found, identify the intended worker before sampling;
never describe one arbitrary process as the entire server.

Use `cfx_server_stability_log` to summarize a developer-selected workspace log
without exposing raw lines. Empty findings in a bounded tail do not prove stability.

For script milliseconds, use `cfx_performance_capture_plan`, then analyze the
developer's exported JSON with `cfx_resource_timings`. Server and client captures
measure different work; side is caller-declared. Never describe captured timings
as live resmon. Use `cfx_compare_resource_timings` on comparable workloads, retaining
sample counts and metric units. Missing resources are not performance improvements.

See [performance measurement setup](../../docs/PERFORMANCE.md). Capture plans do
not execute commands, start recording or grant live control.
