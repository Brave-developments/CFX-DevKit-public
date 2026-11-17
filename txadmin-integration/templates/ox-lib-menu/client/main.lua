lib.registerContext({ id = 'devkit_menu', title = 'CFX DevKit', options = {
  { title = 'Hello', description = 'A local menu action', onSelect = function() lib.notify({ description = 'Hello!' }) end }
} })
RegisterCommand('devkitmenu', function() lib.showContext('devkit_menu') end, false)
