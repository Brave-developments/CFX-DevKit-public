local ESX = exports['es_extended']:getSharedObject()
RegisterCommand('myjob', function(src)
    if src == 0 then return end
    local player = ESX.GetPlayerFromId(src)
    if not player then return end
    TriggerClientEvent('chat:addMessage', src, { args = { 'Job', player.job.name } })
end, false)
