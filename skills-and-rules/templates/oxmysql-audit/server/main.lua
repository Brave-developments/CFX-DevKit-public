RegisterCommand('devdbcheck', function(src)
  if src ~= 0 then return end -- server console only
  local result = MySQL.single.await('SELECT 1 AS ready', {})
  print('Database connection:', result and result.ready or 'unavailable')
end, false)
