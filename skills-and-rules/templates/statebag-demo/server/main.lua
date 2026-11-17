RegisterCommand('devkitflag', function(src)
  if src <= 0 or not IsPlayerAceAllowed(src, 'devkit.state.set') then return end
  local player = Player(src)
  if player then player.state:set('devkit:flag', true, true) end
end, false)
