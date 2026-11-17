# FiveM game input (Windows development only)

After launching the local FiveM game, you may separately authorize **keyboard/mouse input** for a short period from a human interactive terminal:

```powershell
cfx-devkit game-input-arm --minutes 15
```

Confirm the phrase `ALLOW FIVEM INPUT`. Input remains disabled unless the approved FiveM executable is the **foreground** Windows process. Revoke with `cfx-devkit game-input-disarm` or let the grant expire.

Supported MCP actions: `cfx_game_input_status`, `cfx_game_press_key` (20–2000 ms, allowlisted keys), `cfx_game_click` (left/right), `cfx_game_mouse_move` (relative, bounded), `cfx_game_scroll` (1–3 steps), `cfx_game_type_text` (up to 120 printable characters), and `cfx_game_screenshot` (PNG saved locally, optional `Pillow` installation required).

Input tools **do not** grant server control, Full Control, or OS desktop automation. They reject an unapproved session and attempt to verify that FiveM is focused before input. Windows may reject synthetic input; elevated games and background windows are intentionally unsupported. Never run the MCP with elevated privileges solely to bypass this restriction.

Screenshots cover the foreground game window rectangle, and **overlapping desktop windows may appear** in the image. Local screenshots should be treated as potentially sensitive. No general screen-capture tool or remote desktop API is provided.

A successful input call only means the input was submitted to Windows. It **does not** prove the game processed it, that a server connection succeeded, or that the gameplay scenario passed. Full end-to-end acceptance requires the real local FiveM client and game bridge.
