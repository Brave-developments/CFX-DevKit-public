AddStateBagChangeHandler('devkit:flag', nil, function(bag, key, value)
  if type(value) == 'boolean' then print('State changed for', bag, value) end
end)
