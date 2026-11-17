-- CFX DevKit controlled development-server resource lifecycle adapter.
-- Standalone optional FXServer server-only resource. NO client_scripts, no player
-- events/commands, no Lua evaluation, no general ExecuteCommand gateway.
-- It polls a loopback Python broker for *human-approved* lifecycle proposals.
local endpoint = 'http://127.0.0.1:8766'
local active = false
local REQUEST_ID = '^[a-f0-9]+$'

local function isEnabled()
    return GetConvarInt('devkit_control_enable', 0) == 1
end

local function isResourceName(name)
    return type(name) == 'string'
        and #name >= 1 and #name <= 64
        and name:match('^[A-Za-z0-9_-]+$') ~= nil
        and name ~= GetCurrentResourceName()
        and name:lower() ~= 'txadmin'
end

local function allowedItem(text, item)
    for value in (text or ''):gmatch('[^,]+') do
        value = value:match('^%s*(.-)%s*$')
        if value == item then return true end
    end
    return false
end

local function validAction(action)
    return action == 'restart' or action == 'ensure' or action == 'stop'
end

local function permitted(action, resource)
    if not isEnabled() or not isResourceName(resource) or not validAction(action) then return false end
    if not allowedItem(GetConvar('devkit_control_resources', ''), resource) then return false end
    if not allowedItem(GetConvar('devkit_control_actions', 'restart'), action) then return false end
    return true
end

local function secret()
    local key = GetConvar('devkit_control_token', '')
    if #key < 32 or #key > 256 then return nil end
    return key
end

local function headers()
    local token = secret()
    if not token then return nil end
    return { ['X-CFX-Control-Token'] = token, ['Content-Type'] = 'application/json' }
end

local function report(task)
    local hdr = headers()
    if not hdr then return end
    local state = GetResourceState(task.resource)
    local valid = {
        started=true, stopped=true, starting=true, stopping=true,
        missing=true, unknown=true, uninitialized=true
    }
    if not valid[state] then state='unknown' end
    local body = json.encode({
        id=task.id, resource=task.resource,
        action=task.action, observed_state=state
    })
    PerformHttpRequest(endpoint .. '/result', function(status)
        if status ~= 200 then
            print('[CFX DevKit Control] Could not report result: status ' .. tostring(status))
        end
    end, 'POST', body, hdr)
end

local function poll()
    if not isEnabled() then return end
    local hdr = headers()
    if not hdr then return end
    PerformHttpRequest(endpoint .. '/next', function(status, payload)
        if not isEnabled() or status ~= 200 then return end
        local ok, decoded = pcall(json.decode, payload or '')
        if not ok or type(decoded) ~= 'table' or type(decoded.request) ~= 'table' then return end
        local task=decoded.request
        if type(task.id) ~= 'string' or #task.id ~= 24 or not task.id:match(REQUEST_ID) then return end
        if not permitted(task.action, task.resource) then
            print('[CFX DevKit Control] Refused unauthorized request; resource/action not in private allowlist')
            return
        end
        -- Strictly validated tokens; no semicolon, whitespace or arbitrary command suffixes.
        print(('[CFX DevKit Control] Human-approved: %s %s'):format(task.action, task.resource))
        ExecuteCommand(task.action .. ' ' .. task.resource)
        SetTimeout(1200, function()
            report(task) -- observed state, NOT verified game behavior.
        end)
    end, 'GET', '', hdr)
end

CreateThread(function()
    while true do
        Wait(2000)
        poll()
    end
end)
