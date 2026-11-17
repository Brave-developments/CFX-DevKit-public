RegisterNUICallback('close', function(data, cb)
    SetNuiFocus(false, false)
    cb({ ok = true }) -- Always reply, including on error.
end)
