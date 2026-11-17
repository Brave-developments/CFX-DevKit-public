# Server performance and stability tools

Six read-only MCP tools supplement the static `cfx_audit_performance` and generic
`cfx_analyze_profiler_trace` tools. No server restart, bridge installation, resource
injection, recording or Full Control authorization is performed by these tools.

| Tool | Evidence returned |
| --- | --- |
| `cfx_server_health` | Live loopback HTTP availability/response latency, client/max-client counts and advertised resource count |
| `cfx_server_process_metrics` | Sampled CPU, resident memory and change, threads, uptime for one FXServer PID |
| `cfx_resource_timings` | Captured per-resource tick mean, p95 and maximum milliseconds, observed total time and frame-normalized average when frame scopes exist |
| `cfx_compare_resource_timings` | Before/after timing differences with span counts, coverage and explicit normalization basis |
| `cfx_server_stability_log` | Bounded hitch count/max/p95, script errors by resource, missing dependencies, repeated starts and fatal-error markers |
| `cfx_performance_capture_plan` | Fixed profiler instructions for a server or client capture; no commands executed |

## Live server and process observations

Call `cfx_server_health` with the game port (default 30120). It reads only the
loopback `info.json` and `dynamic.json` endpoints. Redirects and HTTP proxies are
disabled, responses are bounded, and raw convars, hostnames and player identities
are never returned. A failed endpoint reports unavailable/null, not zero players.
Response latency measures that HTTP request, not tick time or script cost.
An advertised resource count is not a count of verified healthy resources.

For CPU and memory, install the optional dependency from your checkout:

```sh
python -m pip install -e '.[monitoring]'
```

Call `cfx_server_process_metrics` with `pid` and `interval_ms` (100–3000; default
1000). Without a PID, the still-running process started by this MCP session is
preferred when it appears among the FXServer candidates. This uses the retained
process handle, so an exited or reused PID is not trusted. The association is not
retained across MCP restarts. Otherwise one matching FXServer process is sampled
automatically; multiple matches return candidate PIDs for selection. A txAdmin manager and its
workers must not be treated as one process or silently combined. Process matching
checks the executable name, not which profile owns a socket.

`cpu_percent_one_core` can exceed 100% for multicore work.
`cpu_percent_machine_capacity` divides this value by the machine's logical CPU
count; it is not a container-quota or CPU-affinity-normalized measurement.
`rss_bytes` is resident process memory, and its change is measured across the
sampling interval. RSS growth alone does not prove a memory leak. Process metrics
do not attribute work or memory to individual resources. No command line,
environment, credentials or network connections are collected.

## Measuring script milliseconds

Stability logs report `missing_dependencies` for “Could not find dependency” and
`failed_dependencies` for “Could not start dependency”. The latter does not prove
that a dependency is absent. `onesync_required_markers` counts “OneSync needs to
be enabled” lines. All are counts within the bounded log tail, not full-server totals.

Call `cfx_performance_capture_plan` with `side: "server"` and a simple output
filename. In the actual FXServer console, capture a reproducible action:

```text
profiler record 500
profiler status
```

After recording has stopped:

```text
profiler saveJSON performance-profile.json
```

For client cost use F8 instead and label the analysis `side: "client"`. The
tool does not infer or verify capture side. The built-in profiler records a
number of frames, not a duration in milliseconds; capture overhead can affect
results. The export is saved relative to the server/client working location.
Place it under `CFX_WORKSPACE_ROOT` before analysis.

Example tool arguments:

```json
{"path":"profiles/performance-profile.json","side":"server","limit":20}
```

`cfx_resource_timings` recognizes the upstream `tick (resource)` and
`Resource Manager Tick` scopes in Chrome Trace complete (`X`) events or matched
begin/end (`B`/`E`) events. Begin/end stacks are separated by process and thread.
Malformed/unmatched spans are counted. Traces above 40 MB or 300,000 events are
rejected, and mixed-process resource captures must be split.

- `mean_tick_span_ms`, `p95_tick_span_ms`, `max_tick_span_ms`: inclusive duration of
  the observed resource tick spans; not an idle resmon rolling average.
- `observed_total_ms`: overlapping spans of the same resource on the same thread
  are merged to prevent duplicate nested cost.
- `mean_ms_per_observed_frame`: observed total divided by captured Resource
  Manager Tick count. Null when frame scopes are absent.

These are captured scope durations. They do not measure all event handlers,
exclusive CPU use, database latency, GPU work or live resmon readings. Nested
different-resource spans and different threads may overlap; do not sum all rows
and call the result total CPU time. Missing scopes do not mean zero cost.

For comparisons, pass `baseline_path`, `candidate_path`, and the same declared
side to `cfx_compare_resource_timings`. Record the same scenario, load and player
conditions. The tool normalizes by observed frames when both captures have frame
scopes; otherwise it compares mean tick-span duration and says so. More than 100
resource rows per capture is rejected rather than comparing incomplete top-N
lists. A missing row is reported as missing, never as a zero-cost improvement.
Positive deltas indicate more observed time; they do not establish statistical
significance or guarantee an optimization.

## Stability evidence

`cfx_server_stability_log` accepts a workspace-relative `.log`/`.txt` path and a
line limit (default 10,000, maximum 50,000). It reads at most the last 4 MB and
returns counts and safe resource names, never raw lines, traceback text, player
identities, SQL or secrets. Copy an external log into the workspace if needed;
`server.cfg` is not accepted. Results describe the sampled tail, not a time-based
rate or a complete history. Repeated starts can be deliberate. There is no
automatic pass/fail stability score.

For servers started by this toolkit, use the `log_path` returned by
`cfx_fxserver_start`, or `server_start.log_path` from the combined startup/join
response. Both stdout and stderr are retained there. External server logs still
need to be selected by the developer.

Resource timing tests cover format-accurate fixtures and source-confirmed scope
labels. Validate real exports from the intended server separately and inspect
the reported observed frames and invalid/unmatched events. Fixture results are
not measurements of your server. On Windows, writing
profiler commands to redirected FXServer stdin is not a reliable capture method.
Use the actual server console, or separately authorized existing control tooling.

Useful practice: sample the intended FXServer worker while reproducing a hitch,
analyze the corresponding profiler capture and log tail, change one suspected
resource, then capture the same workload again. Repeat observations over time
before making claims about stability or a memory leak.

Sources: [official profiler usage](https://docs.fivem.net/docs/scripting-manual/debugging/using-profiler/)
and [upstream profiler export/scopes](https://github.com/citizenfx/fivem/blob/master/code/components/citizen-scripting-core/src/Profiler.cpp).
