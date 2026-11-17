-- CFX DevKit full-control client (dev server only).
-- Requires server-side ACE permission 'devkit.live'. No token is sent to clients.
local function enabled()
    return GetConvarInt('devkit_live_client_enabled',0)==1
end
local function respond(id,ok,value,error,note)
    if type(value)=='table' then
        local success,out=pcall(json.encode,value)
        value=success and out or tostring(value)
    end
    local function short(v)
        if v==nil then return nil end
        local text=tostring(v)
        if #text>10000 then return text:sub(1,10000)..' [truncated]' end
        return text
    end
    TriggerServerEvent('cfx-devkit-live:client-result',id,{
        ok=ok==true,value=short(value),error=short(error),note=short(note)
    })
end
local function validId(id)
    return type(id)=='string' and #id==32 and id:match('^[a-f0-9]+$')~=nil
end
local function executeLua(script)
    if type(script)~='string' or #script<1 or #script>16000 then return false,nil,'Invalid Lua snippet' end
    local chunk,err=load(script,'@cfx-devkit-live-client','t',_ENV)
    if not chunk then return false,nil,err end
    local ok,out=pcall(chunk)
    return ok,out,ok and nil or out
end
local function perform(data)
    if type(data)~='table' or type(data.action)~='string' then
        return false,nil,'Invalid client action'
    end
    local ped=PlayerPedId()
    if ped==0 or not DoesEntityExist(ped) then return false,nil,'No local player ped' end
    if data.action=='position' then
        local c=GetEntityCoords(ped)
        return true,('x=%.3f y=%.3f z=%.3f heading=%.1f'):format(c.x,c.y,c.z,GetEntityHeading(ped))
    elseif data.action=='teleport' then
        local x,y,z=data.x,data.y,data.z
        if type(x)~='number' or type(y)~='number' or type(z)~='number' or
            math.abs(x)>100000 or math.abs(y)>100000 or math.abs(z)>100000 then
            return false,nil,'Invalid coordinates'
        end
        SetEntityCoords(ped,x,y,z,false,false,false,false)
        return true,'SetEntityCoords invoked'
    elseif data.action=='freeze' then
        FreezeEntityPosition(ped,true);return true,'Ped frozen'
    elseif data.action=='unfreeze' then
        FreezeEntityPosition(ped,false);return true,'Ped unfrozen'
    elseif data.action=='clear_tasks' then
        ClearPedTasks(ped);return true,'Ped tasks cleared'
    elseif data.action=='heal' then
        SetEntityHealth(ped,GetEntityMaxHealth(ped));return true,'Ped health set to maximum'
    elseif data.action=='play_animation' then
        local dict,clip=data.dictionary,data.clip
        if type(dict)~='string' or type(clip)~='string' or #dict>150 or #clip>150 then
            return false,nil,'Invalid animation pair'
        end
        RequestAnimDict(dict)
        local deadline=GetGameTimer()+5000
        while not HasAnimDictLoaded(dict) and GetGameTimer()<deadline do Wait(0) end
        if not HasAnimDictLoaded(dict) then return false,nil,'Dictionary did not load' end
        TaskPlayAnim(ped,dict,clip,8.0,-8.0,-1,49,0.0,false,false,false)
        RemoveAnimDict(dict)
        return true,'Animation requested; visual outcome must be checked'
    end
    return false,nil,'Unsupported action'
end
RegisterNetEvent('cfx-devkit-live:client-execute',function(id,kind,data)
    if not enabled() or not validId(id) or type(data)~='table' then return end
    if kind~='client_lua' and kind~='client_action' then return end
    -- Execution request is sent from the development server resource only.
    -- The associated server resource independently checks devkit.live ACE.
    CreateThread(function()
        local ok,value,error
        if kind=='client_lua' then
            ok,value,error=executeLua(data.code)
        else
            ok,value,error=perform(data)
        end
        respond(id,ok,value,error)
    end)
end)
