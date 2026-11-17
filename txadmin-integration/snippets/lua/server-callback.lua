-- Example ox_lib callback, server only. Authorize and validate source.
lib.callback.register('demo:getStatus', function(src)
    if not src or src <= 0 then return nil end
    return { ready = true }
end)
