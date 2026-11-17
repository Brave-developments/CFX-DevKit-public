RegisterCommand('devpanel', function(src)
    if src > 0 and not IsPlayerAceAllowed(src, 'command.devpanel') then return end
    print('Authorized devpanel command')
end, true)
