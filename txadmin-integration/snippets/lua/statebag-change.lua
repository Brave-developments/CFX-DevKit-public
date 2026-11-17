AddStateBagChangeHandler('demo:active', nil, function(bagName, key, value, reserved, replicated)
    if type(value) ~= 'boolean' then return end
    print(bagName, key, value)
end)
