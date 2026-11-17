local visible = false
local function setVisible(nextValue)
  visible = nextValue
  SetNuiFocus(visible, visible)
  SendNUIMessage({ action = 'visibility', visible = visible })
end
RegisterCommand('devkitui', function() setVisible(not visible) end, false)
RegisterNUICallback('close', function(data, cb)
  setVisible(false)
  cb({ ok = true })
end)
AddEventHandler('onResourceStop', function(resource)
  if resource == GetCurrentResourceName() then SetNuiFocus(false, false) end
end)
