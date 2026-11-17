-- Example ONLY: replace checkPlayerPermission with your framework/ACE validation.
RegisterNetEvent('demo:request', function(itemId)
    local src = source
    if not src or src <= 0 then return end
    if type(itemId) ~= 'string' or #itemId > 40 then return end
    if not IsPlayerAceAllowed(src, 'demo.request') then return end
    -- Validate itemId against server configuration before any action.
    print(('Approved request from %d'):format(src))
end)
