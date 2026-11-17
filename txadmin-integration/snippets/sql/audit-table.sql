-- Optional audit history. Supply authoritative server-derived values only.
CREATE TABLE IF NOT EXISTS demo_audit (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  event_name VARCHAR(96) NOT NULL,
  actor_identifier VARCHAR(96) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
