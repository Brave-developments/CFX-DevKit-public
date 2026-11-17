# GTA V / FiveM animation dictionary reference

Data source: [DurtyFree/gta-v-data-dumps animDictsCompact.json](https://github.com/DurtyFree/gta-v-data-dumps/blob/master/animDictsCompact.json).

On 2026-10-24 its actual JSON contained **20,179 distinct `DictionaryName` values** and **269,414 entries in `Animations` arrays**. Other animation explorers have different totals due to extraction date, DLC/build, or ped-only filtering. Our tool reports **actual** sync counts and the dataset provenance hash.

## What is in the dataset?

~~~json
{
  "DictionaryName": "random@mugging3",
  "Animations": ["handsup_standing_base", "sit_base"]
}
~~~

This is a simplified illustration; the upstream file has other clips in the same dictionary.

- Dictionary name: passed to `RequestAnimDict` and `TaskPlayAnim`.
- Clip name: passed as the second string argument to `TaskPlayAnim`.
- Dictionary names are *case-sensitive*. No fake clips or category claims.
- Some asset names represent vehicle, object or cutscene animations rather than normal freemode-ped animation. The data dump cannot confirm a particular ped will play the animation.
- This index is not a movement clipset or scenario list; those use different natives and data.

## Full import

~~~powershell
$env:CFX_ENABLE_NETWORK = "1"
python -m cfx_devkit.cli sync-animations
python -m cfx_devkit.cli animation-status
~~~

Download uses a fixed raw GitHub URL to the cited upstream file, bounded to 30 MB, and validates expected list fields/types, unique dictionary names and substantial dictionary/clip counts before writing your cache. It stores original records in user-local cache and a SHA-256/source/timestamp sidecar. This project does **not** redistribute that full file, because upstream license terms are not clearly specified.

## Discover, check and generate

~~~powershell
python -m cfx_devkit.cli search-animation-dict "amb@world_human" --limit 25
python -m cfx_devkit.cli search-animation-clip "handsup" --limit 25
python -m cfx_devkit.cli search-animation-clip "idle" --dictionary "random@mugging3"
python -m cfx_devkit.cli animation-detail "mp_arresting" --limit 50
python -m cfx_devkit.cli validate-animation "random@mugging3" "handsup_standing_base"
python -m cfx_devkit.cli animation-lua "random@mugging3" "handsup_standing_base" --flag 49 --duration -1
~~~

An MCP agent can use the equivalent eight cfx_* animation tools directly, with offsets up to 1,000,000 and up to 100 results per page.

## Runtime usage

The generated Lua snippet:

1. Runs client-side, against PlayerPedId() only.
2. Requests the selected dictionary.
3. Waits until it loads, with a bounded 5-second default timeout.
4. Calls TaskPlayAnim with user-selected `duration` and `flag` (default 49: loop + upper body + secondary).
5. Removes the dictionary loading request after the task is started.
6. Does **not** prove game-build/ped compatibility.

Reference: [FiveM TaskPlayAnim native](https://docs.fivem.net/natives/?_0xEA47FE3719165B94).

## Verification

~~~bash
python -m unittest discover -s tests -v
~~~

The [animation-upstream GitHub Action](../.github/workflows/animation-upstream.yml) downloads the entire source into its temporary runner cache and checks totals without committing the upstream dataset.

## Provenance and redistribution

The full dump comes from DurtyFree's game-data extraction. Attribution does not automatically grant redistribution rights; obtain appropriate permission before publishing mirrored datasets, even if a tool can download them. Full sync happens on each user's machine under their own decision.
