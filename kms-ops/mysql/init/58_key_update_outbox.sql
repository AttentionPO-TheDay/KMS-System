-- Durable follow-up work; committed atomically with the updated key and its history.
CREATE TABLE IF NOT EXISTS key_update_outbox (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    event_json LONGTEXT NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
