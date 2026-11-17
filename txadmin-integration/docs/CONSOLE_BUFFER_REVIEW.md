# Native console-buffer fallback review

Date: 17 November 2026. Base public commit: `2f37592`.

**Independent reviewer verdict: PASS for publication** of the corrected fallback,
within the existing trusted-local-development model. The reviewer independently
ran all nine focused console tests and reproduced the initial privacy issue
against the corrected result/status implementation. Both runtime copies match.

## Design

When no server log file is configured, cfx_live_log queues a fixed server-Lua
GetConsoleBuffer read through the existing authorized bridge. No new endpoint,
grant, native console listener, resource hook or file permission is introduced.
Known server bridge convars are redacted before trimming to a bounded UTF-8-safe
2,500-byte recent tail. Configured file reads remain preferred; client console
sources remain separate.

## Privacy fixes verified

- Internal reads are tagged atomically with their queue insertion.
- Tagged results are redacted before storage, including nested and legacy error values.
- Raw retained data from older brokers is redacted on direct-result and recent-status routes.
- Those routes withhold tagged console data after authorization is revoked.
- Server-side redaction precedes truncation, preventing secret suffix exposure.
- File-tail reads discard the initial partial line and redact before final cropping.

## Validation and limits

Full regression suite: 255 tests (254 passed, one platform skip). Nine console
checks include execution of the fixed Lua in a real local Lua runtime, token
boundary and UTF-8 handling, pending reads, native failures and revocation paths.
A live owner-authorized connection also verified the native marker read and the
final installed MCP cfx_live_log path, without a log file or resource/server restart.
No raw console text, token, player data or server-specific telemetry is published.

The buffer is a recent snapshot, not continuous capture, complete history or
uniquely command-correlated output. Broker reachability and server polling remain
necessary. Other private operational data may remain beyond the known tokens;
console output must not be copied into public reports. An accepted command still
does not establish command or gameplay success.

Official native declaration:
https://github.com/citizenfx/fivem/blob/master/ext/native-decls/GetConsoleBuffer.md
