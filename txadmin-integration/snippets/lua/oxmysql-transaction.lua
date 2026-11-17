-- Server only. Provide validated IDs and amounts from authoritative state.
local ok = MySQL.transaction.await({
  { query = 'UPDATE demo_wallet SET balance = balance - ? WHERE id = ? AND balance >= ?', values = { amount, senderId, amount } },
  { query = 'UPDATE demo_wallet SET balance = balance + ? WHERE id = ?', values = { amount, receiverId } },
})
-- Verify transaction semantics and affected rows for your schema.
