-- Server only. Parameterized SQL: no string concatenation.
local rows = MySQL.query.await('SELECT id FROM demo_users WHERE citizenid = ?', { citizenid })
