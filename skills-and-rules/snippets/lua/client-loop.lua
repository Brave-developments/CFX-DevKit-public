-- Avoid an unconditional busy loop; activate only during your UI/interactions.
CreateThread(function()
    while true do
        local sleep = 1000
        if isUiVisible then sleep = 0 end
        Wait(sleep)
    end
end)
