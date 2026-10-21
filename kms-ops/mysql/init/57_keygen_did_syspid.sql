-- Keep one public DID identifier per generated key. Existing rows and FISCO receipts are preserved.
SET @ddl = IF((SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema=DATABASE() AND table_name='keymanage' AND column_name='sys_pid')=0,
    'ALTER TABLE keymanage ADD COLUMN sys_pid VARCHAR(182) NULL', 'SELECT 1');
PREPARE keygen_did_stmt FROM @ddl; EXECUTE keygen_did_stmt; DEALLOCATE PREPARE keygen_did_stmt;
SET @ddl = IF((SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema=DATABASE() AND table_name='keymanage' AND column_name='did_request_id')=0,
    'ALTER TABLE keymanage ADD COLUMN did_request_id VARCHAR(36) NULL', 'SELECT 1');
PREPARE keygen_did_stmt FROM @ddl; EXECUTE keygen_did_stmt; DEALLOCATE PREPARE keygen_did_stmt;
SET @ddl = IF((SELECT COUNT(*) FROM information_schema.statistics
    WHERE table_schema=DATABASE() AND table_name='keymanage' AND index_name='idx_keymanage_sys_pid')=0,
    'CREATE INDEX idx_keymanage_sys_pid ON keymanage(sys_pid)', 'SELECT 1');
PREPARE keygen_did_stmt FROM @ddl; EXECUTE keygen_did_stmt; DEALLOCATE PREPARE keygen_did_stmt;
