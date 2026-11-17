-- Requires ox_lib, client side. Do not trust completion as server-side proof.
local done = lib.progressBar({ duration = 1500, label = 'Working', canCancel = true })
if done then print('Local progress complete') end
