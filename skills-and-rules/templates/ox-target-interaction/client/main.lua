local zone = exports.ox_target:addSphereZone({
  coords = vec3(0.0, 0.0, 72.0), radius = 1.5,
  options = {{ name = 'devkit_inspect', icon = 'fa-solid fa-circle-info', label = 'Inspect',
    onSelect = function() print('Local target interaction') end }}
})
AddEventHandler('onResourceStop', function(name)
  if name == GetCurrentResourceName() then exports.ox_target:removeZone(zone) end
end)
