-- Server only, qbx_core present. Never trust client-supplied citizenid or money.
local player = exports.qbx_core:GetPlayer(source)
if not player then return end
print(player.PlayerData.citizenid)
