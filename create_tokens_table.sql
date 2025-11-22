-- Tokens tábla létrehozása
CREATE TABLE IF NOT EXISTS tokens (
    id INT(11) UNSIGNED NOT NULL AUTO_INCREMENT,
    token VARCHAR(100) NOT NULL,
    user_id INT(11) UNSIGNED NULL,
    token_type VARCHAR(20) NOT NULL,
    generated_by_id INT(11) UNSIGNED NOT NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 0,
    activated_at DATETIME NULL,
    expires_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY token (token),
    KEY user_id (user_id),
    KEY generated_by_id (generated_by_id),
    KEY expires_at (expires_at),
    CONSTRAINT fk_tokens_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT fk_tokens_generated_by FOREIGN KEY (generated_by_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

