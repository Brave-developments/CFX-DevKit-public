-- Client-only UI/display event.
RegisterNetEvent('demo:notify', function(message)
    if type(message) ~= 'string' then return end
    print(message:sub(1, 200))
end)
