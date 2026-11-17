-- CFX DevKit / local development client preview commands.
-- Not a server admin bridge. Enable ONLY on a development server:
-- setr devkit_preview_enable 1
local previewActive = false
local function enabled()
    return GetConvarInt('devkit_preview_enable', 0) == 1
end
local function notice(message)
    print(('[CFX DevKit Preview] %s'):format(tostring(message)))
end
local function loadDictionary(dict)
    RequestAnimDict(dict)
    local expires = GetGameTimer() + 5000
    while not HasAnimDictLoaded(dict) and GetGameTimer() < expires do
        Wait(0)
    end
    return HasAnimDictLoaded(dict)
end
local function loadParticleDict(dict)
    RequestNamedPtfxAsset(dict)
    local expires = GetGameTimer() + 5000
    while not HasNamedPtfxAssetLoaded(dict) and GetGameTimer() < expires do
        Wait(0)
    end
    return HasNamedPtfxAssetLoaded(dict)
end
local function validIdentifier(text)
    return type(text)=='string' and #text>0 and #text<=180
       and not text:find('[%c]')
end
RegisterCommand('devkit_anim', function(_, args)
    if not enabled() then return notice('Disabled: setr devkit_preview_enable 1 in development server.cfg') end
    local dict, clip=args[1],args[2]
    if not validIdentifier(dict) or not validIdentifier(clip) then
        return notice('Usage: /devkit_anim <dictionary> <clip>')
    end
    local ped=PlayerPedId()
    if ped==0 or not DoesEntityExist(ped) then return notice('No local player ped') end
    if not loadDictionary(dict) then return notice('Animation dictionary not loaded: '..dict) end
    TaskPlayAnim(ped,dict,clip,8.0,-8.0,-1,49,0.0,false,false,false)
    RemoveAnimDict(dict)
    previewActive=true
    notice('Requested client animation '..dict..' / '..clip..'. Visual result is not guaranteed.')
end,false)
RegisterCommand('devkit_ptfx', function(_, args)
    if not enabled() then return notice('Disabled: setr devkit_preview_enable 1 in development server.cfg') end
    local dict,effect=args[1],args[2]
    if not validIdentifier(dict) or not validIdentifier(effect) then
        return notice('Usage: /devkit_ptfx <asset_dictionary> <effect_name>')
    end
    if not loadParticleDict(dict) then return notice('Particle asset failed to load: '..dict) end
    local ped=PlayerPedId()
    if ped~=0 and DoesEntityExist(ped) then
        local pos=GetEntityCoords(ped)
        UseParticleFxAssetNextCall(dict)
        StartParticleFxNonLoopedAtCoord(effect,pos.x,pos.y,pos.z,0.0,0.0,0.0,1.0,false,false,false)
    end
    RemoveNamedPtfxAsset(dict)
    notice('Requested local particle '..dict..' / '..effect)
end,false)
RegisterCommand('devkit_stop', function()
    if not enabled() then return end
    if previewActive then
        local ped=PlayerPedId()
        if ped~=0 then ClearPedTasks(ped) end
        previewActive=false
    end
    notice('Local preview stopped')
end,false)
AddEventHandler('onResourceStop',function(name)
    if name~=GetCurrentResourceName() then return end
    if previewActive then
        local ped=PlayerPedId()
        if ped~=0 then ClearPedTasks(ped) end
    end
end)
