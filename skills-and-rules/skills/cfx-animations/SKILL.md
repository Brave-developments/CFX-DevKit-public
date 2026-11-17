---
name: cfx-animations
description: Search complete FiveM/GTA V animation dictionaries and clip names, validate pairs, and generate safe client-side TaskPlayAnim code.
---
1. Call cfx_animation_status and report whether data coverage is complete. The bundled 12-dictionary sample is NOT a full index.
2. When the user wants the full database and has approved the network download, set CFX_ENABLE_NETWORK=1 and run cfx_sync_animations on the user's own machine. Never claim the whole dump is bundled.
3. Use cfx_search_animation_dicts to locate a dictionary and cfx_search_animation_clips to find a clip by name. Use cfx_animation_dict_detail for all clips within an exact dictionary, with offset pagination.
4. Call cfx_validate_animation_pair before outputting code. Names are case-sensitive.
5. Use cfx_generate_animation_lua for a client-side timed RequestAnimDict / HasAnimDictLoaded / TaskPlayAnim example.
6. Remember: dictionary and clip presence in the dump does not guarantee ped compatibility, current game-build availability or an in-game tested result. Validate by playing it in a development FiveM server.
7. Movement clipsets, ped scenarios, props, synced scenes and animation flags have separate semantics; do not claim all entries work on freemode peds.
