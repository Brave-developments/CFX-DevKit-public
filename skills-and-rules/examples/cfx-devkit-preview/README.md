# Optional local FiveM preview resource

**Not an MCP network bridge.** This is a tiny client-side development helper with no server events or permissions escalation.

1. Copy `cfx-devkit-preview` under your development server resources.
2. Add `setr devkit_preview_enable 1` and `ensure cfx-devkit-preview` to your **development** server.cfg.
3. In game, try `/devkit_anim random@mugging3 handsup_standing_base`, `/devkit_ptfx core ent_sht_water`, and `/devkit_stop`.
4. Remove the resource or set `setr devkit_preview_enable 0` before running a production server.

It does not accept inbound network calls, perform database writes, export admin actions, or guarantee every dumped GTA V asset can be played by your character. No real FiveM runtime tests have been performed by CI.
