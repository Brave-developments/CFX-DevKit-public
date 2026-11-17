# CFX DevKit 0.4 implementation scope

This release improves developer utility but is **not feature-complete v1.0**.

| Area | v0.4 state |
| --- | --- |
| FiveM native references | Official opt-in sync, smoke test not verified here |
| Animation references | Full upstream sync verified in GitHub Actions |
| Movement, particles, scenarios, IPL, interior, ped and vehicle catalogs | Opt-in local sync implemented, upstream verification by separate CI |
| Static project intelligence | Lua lexical event index + streaming file checks, not a full AST |
| Build and install | Include template and snippet assets in Python wheel |
| Security | Read-only heuristic reviews; no exploitability proofs |
| Profiler | Offline Chrome Trace JSON summaries; does not collect live traces |
| In-game resource | Local preview client included; no running FiveM validation |
| Host integration | Codex, Cursor and Claude configuration generation; final IDE compatibility unverified |
| Real-time debugging and screenshots | Not included |
| Marketplace/publishing | Not included |

Release gates before v1.0: actual FiveM-client acceptance testing, SDK interoperability tests with representative Codex/Cursor/Claude versions, comprehensive AST-based security checks, and redistribution review of external catalogs.
