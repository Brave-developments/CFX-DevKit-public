-- Client only, ox_target dependency.
exports.ox_target:addSphereZone({
    coords = vec3(0.0, 0.0, 72.0), radius = 1.5, debug = false,
    options = { { name = 'demo:inspect', label = 'Inspect', icon = 'fa-solid fa-search',
        onSelect = function() print('Local interaction; validate server actions separately.') end } }
})
