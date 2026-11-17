-- Client only. PlayerPedId() is a local client native.
local ped = PlayerPedId()
if ped ~= 0 then
    local coords = GetEntityCoords(ped)
    print(coords.x, coords.y, coords.z)
end
