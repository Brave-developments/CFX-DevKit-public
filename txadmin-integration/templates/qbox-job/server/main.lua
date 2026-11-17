RegisterCommand('myjob', function(src)
    if src == 0 then return end
    local player = exports.qbx_core:GetPlayer(src)
    if not player or not player.PlayerData.job then return end
    TriggerClientEvent('chat:addMessage', src, { args = { 'Job', player.PlayerData.job.name } })
end, false)
