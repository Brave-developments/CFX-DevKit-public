-- Optional CFX DevKit v1 development-only reporter.
-- This script is server-side only. No inbound network events, no commands,
-- no player identifiers, and no client-facing state. Disable in production.
local endpoint = 'http://127.0.0.1:8765/event'
local function enabled()
    return GetConvarInt('devkit_bridge_enable', 0) == 1
end
local function safeResource(name)
    return type(name) == 'string' and #name >= 1 and #name <= 96
       and name:match('^[%w_.-]+$') ~= nil
end
local function report(event, resource, detail)
    if not enabled() then return end
    if not safeResource(resource) then return end
    local token = GetConvar('devkit_bridge_token', '')
    if #token < 32 then return end
    local fields = {event = event, resource = resource}
    if detail ~= nil then fields.detail = detail end
    PerformHttpRequest(endpoint, function(status, response, headers)
        if status ~= 202 and GetConvarInt('devkit_bridge_verbose', 0) == 1 then
            print('[CFX DevKit] Bridge report not accepted (status ' .. tostring(status) .. ')')
        end
    end, 'POST', json.encode(fields), {
        ['Content-Type'] = 'application/json',
        ['X-CFX-DevKit-Token'] = token,
    })
end

AddEventHandler('onResourceStart', function(name)
    report('resource_started', name)
end)
AddEventHandler('onResourceStop', function(name)
    report('resource_stopped', name)
end)

-- Safe, server-side-only export for other trusted dev resources to report
-- a category without sending raw exception text or user/player information.
exports('ReportErrorCategory', function(resource, category)
    if category ~= 'runtime' and category ~= 'load' and
       category ~= 'dependency' and category ~= 'unknown' then return false end
    if not safeResource(resource) then return false end
    report('resource_error', resource, category)
    return true
end)
