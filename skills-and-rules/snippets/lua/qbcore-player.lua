-- Server only, qb-core present.
local QBCore = exports['qb-core']:GetCoreObject()
local player = QBCore.Functions.GetPlayer(source)
if not player then return end
print(player.PlayerData.citizenid)
