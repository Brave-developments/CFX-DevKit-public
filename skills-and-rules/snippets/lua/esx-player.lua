-- Server only, es_extended present.
local ESX = exports['es_extended']:getSharedObject()
local xPlayer = ESX.GetPlayerFromId(source)
if not xPlayer then return end
print(xPlayer.identifier)
