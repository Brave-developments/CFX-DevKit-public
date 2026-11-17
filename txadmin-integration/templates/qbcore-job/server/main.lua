local QBCore = exports['qb-core']:GetCoreObject()
RegisterCommand('myjob', function(src)
    if src == 0 then return end
    local player = QBCore.Functions.GetPlayer(src)
    if not player or not player.PlayerData.job then return end
    TriggerClientEvent('chat:addMessage', src, { args = { 'Job', player.PlayerData.job.name } })
end, false)
