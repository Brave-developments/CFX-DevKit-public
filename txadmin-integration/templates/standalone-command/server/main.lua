RegisterCommand('devkitstatus', function(src)
    if src > 0 and not IsPlayerAceAllowed(src, 'command.devkitstatus') then return end
    print('Resource running')
end, true)
