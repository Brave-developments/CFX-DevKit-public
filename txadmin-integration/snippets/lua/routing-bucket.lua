-- Server only: permission check required before invoking this function.
local function setPlayerBucket(src, bucket)
    if type(bucket) ~= 'number' or bucket < 0 or bucket > 1000 or bucket % 1 ~= 0 then return false end
    if not GetPlayerName(src) then return false end
    SetPlayerRoutingBucket(src, bucket)
    return true
end
