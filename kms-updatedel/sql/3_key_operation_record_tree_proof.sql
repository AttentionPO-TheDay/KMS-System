-- Add tree proof fields for existing key_operation_record tables.
ALTER TABLE key_operation_record
    ADD COLUMN batch_id VARCHAR(64) DEFAULT NULL COMMENT 'tree batch id',
    ADD COLUMN parent_batch_id VARCHAR(64) DEFAULT NULL COMMENT 'parent batch id',
    ADD COLUMN root_batch_id VARCHAR(64) DEFAULT NULL COMMENT 'root batch id',
    ADD COLUMN tree_path VARCHAR(500) DEFAULT NULL COMMENT 'tree path',
    ADD COLUMN tree_level INT DEFAULT NULL COMMENT 'tree level',
    ADD COLUMN node_index INT DEFAULT NULL COMMENT 'node index',
    ADD COLUMN expected_count INT DEFAULT NULL COMMENT 'expected leaf count',
    ADD COLUMN tree_fanout INT DEFAULT NULL COMMENT 'tree fanout',
    ADD COLUMN proof_mode VARCHAR(32) DEFAULT NULL COMMENT 'proof mode',
    ADD COLUMN commitment VARCHAR(128) DEFAULT NULL COMMENT 'update commitment',
    ADD COLUMN consistency_hash VARCHAR(128) DEFAULT NULL COMMENT 'consistency hash',
    ADD COLUMN batch_root VARCHAR(128) DEFAULT NULL COMMENT 'batch root hash',
    ADD COLUMN verify_status CHAR(1) DEFAULT NULL COMMENT 'verify status 0 pending 1 success 2 failed',
    ADD COLUMN verify_message VARCHAR(500) DEFAULT NULL COMMENT 'verify message',
    ADD KEY idx_batch_id (batch_id),
    ADD KEY idx_verify_status (verify_status);
