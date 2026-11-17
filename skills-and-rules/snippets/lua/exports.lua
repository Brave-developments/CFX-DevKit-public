-- Resource-local callable export; validate inputs and caller trust as appropriate.
exports('GetStatus', function()
    return { ready = true, version = '1.0.0' }
end)
