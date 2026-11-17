AddEventHandler('onResourceStart', function(resource)
    if resource ~= GetCurrentResourceName() then return end
    print(('[%s] started'):format(resource))
end)
