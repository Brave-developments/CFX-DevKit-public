-- CFX DevKit / FULL development server bridge.
-- Privileged! Install ONLY on your own local disposable FXServer.
-- FXServer server-only code, not a general incoming player command handler.
-- Authenticated calls originate from a separate loopback Python broker.
local endpoint = 'http://127.0.0.1:8767'
local PENDING={}
local VALID_KIND = {
    server_info=true,server_resources=true,server_players=true,server_command=true,
    server_lua=true,client_lua=true,client_action=true
}
local function enabled()
    return GetConvarInt('devkit_live_enable',0)==1
        and GetConvar('devkit_live_mode','off')=='full'
end
local function token()
    local value=GetConvar('devkit_live_token','')
    if #value<32 or #value>256 then return nil end
    return value
end
local function header()
    local secret=token()
    if not secret then return nil end
    return {['X-CFX-Live-Token']=secret,['Content-Type']='application/json'}
end
local function validId(id)
    return type(id)=='string' and #id==32 and id:match('^[a-f0-9]+$')~=nil
end
local function safeString(value)
    local s=tostring(value)
    if #s>10000 then return s:sub(1,10000)..' [truncated]' end
    return s
end
local function result(id,ok,value,error,note)
    if not enabled() then return end
    local h=header()
    if not h or not validId(id) then return end
    local object={id=id,result={ok=ok==true}}
    if value~=nil then object.result.value=safeString(value) end
    if error~=nil then object.result.error=safeString(error) end
    if note~=nil then object.result.note=safeString(note) end
    PerformHttpRequest(endpoint..'/result',function(status)
        if status~=200 then print('[CFX DevKit Live] Could not submit result ('..tostring(status)..')') end
    end,'POST',json.encode(object),h)
end
local function LuaExecution(code)
    if type(code)~='string' or #code<1 or #code>16000 then return false,nil,'Invalid Lua code' end
    local compiled, compileError=load(code,'@cfx-devkit-live','t',_ENV)
    if not compiled then return false,nil,compileError end
    local success,value=pcall(compiled)
    return success,value,success and nil or value
end
local function info()
    return ('game=gta5 resources=%s players=%s'):format(GetNumResources(),GetNumPlayerIndices())
end
local function resources()
    local entries={}
    local limit=math.min(GetNumResources(),256)
    for i=0,limit-1 do
        local name=GetResourceByFindIndex(i)
        if name and #name<=80 then
            entries[#entries+1]=name..':'..GetResourceState(name)
        end
    end
    return table.concat(entries,', ')
end
local function players()
    local entries={}
    for _,player in ipairs(GetPlayers()) do
        local id=tonumber(player)
        if id and #entries<128 then
            local authorized=IsPlayerAceAllowed(tostring(id),'devkit.live')
            entries[#entries+1]=tostring(id)..':'..(authorized and 'authorized' or 'no-ace')
        end
    end
    return table.concat(entries,', ')
end
local function process(task)
    if not enabled() or type(task)~='table' or not validId(task.id) or
        type(task.kind)~='string' or not VALID_KIND[task.kind] then return end
    local id,kind=task.id,task.kind
    local data=task.data
    if type(data)~='table' then result(id,false,nil,'Invalid JSON payload');return end
    if kind=='server_info' then
        result(id,true,info());return
    end
    if kind=='server_resources' then
        result(id,true,resources());return
    end
    if kind=='server_players' then
        result(id,true,players());return
    end
    if kind=='server_command' then
        local command=data.command
        if type(command)~='string' or #command<1 or #command>2000 or
            command:find('[%c]') then result(id,false,nil,'Invalid console command');return end
        local ok,error=pcall(ExecuteCommand,command)
        result(id,ok,ok and 'FXServer ExecuteCommand called. Inspect server logs for command output.' or nil,
               ok and nil or error,'Accepted command does not guarantee command success')
        return
    end
    if kind=='server_lua' then
        local ok,value,error=LuaExecution(data.code)
        result(id,ok,ok and value or nil,error);return
    end
    if kind=='client_lua' or kind=='client_action' then
        local player=task.target
        if type(player)~='number' or player<1 or player>2048 or player%1~=0 then
            result(id,false,nil,'Invalid target player');return
        end
        if not GetPlayerName(player) or not IsPlayerAceAllowed(tostring(player),'devkit.live') then
            result(id,false,nil,'Target client is absent or missing devkit.live ACE');return
        end
        PENDING[id]={player=player,deadline=GetGameTimer()+25000}
        TriggerClientEvent('cfx-devkit-live:client-execute',player,id,kind,data)
        return
    end
end
RegisterNetEvent('cfx-devkit-live:client-result',function(id,report)
    local sender=source
    local item=PENDING[id]
    if not item or sender~=item.player or not IsPlayerAceAllowed(tostring(sender),'devkit.live') then return end
    PENDING[id]=nil
    if type(report)~='table' or type(report.ok)~='boolean' then
        result(id,false,nil,'Invalid client report');return
    end
    result(id,report.ok,report.value,report.error,report.note)
end)
local function poll()
    if not enabled() then return end
    local h=header()
    if not h then return end
    PerformHttpRequest(endpoint..'/next',function(status,body)
        if not enabled() or status~=200 or type(body)~='string' then return end
        local ok,packet=pcall(json.decode,body)
        if not ok or type(packet)~='table' or type(packet.request)~='table' then return end
        process(packet.request)
    end,'GET','',h)
end
CreateThread(function()
    while true do
        Wait(1000)
        local now=GetGameTimer()
        for id,item in pairs(PENDING) do
            if now>item.deadline then
                PENDING[id]=nil
                result(id,false,nil,'Authorized client did not respond')
            end
        end
        poll()
    end
end)
