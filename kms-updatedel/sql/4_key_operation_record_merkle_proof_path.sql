-- 为 key_operation_record 增加真正的 Merkle 证明路径列。
--
-- 背景：早前 refreshBatchProof 只是把各记录的 consistency_hash 用 '|' 拼接后
-- 再取一次 SHA-256（线性哈希链），却把 verify_message 写成 "tree proof verified"，
-- 字段名也用了 tree_path / tree_fanout / node_index，容易被理解为 Merkle 证明。
-- 线性哈希链只能证明「服务端声称这些记录都在」，无法证明「某条记录属于该批次」。
--
-- 现在改为二叉 Merkle 树（见 MerkleTree.java）：
--   叶子 H(0x00 || leafValue)，内部节点 H(0x01 || left || right)。
-- 本列存储单条记录的兄弟路径，形如：
--   R:<hash>|L:<hash>|ROOT:<hash>
-- 验证方可仅凭该路径 + 叶子值 + batch_root 独立重算，无需访问数据库。
--
-- 幂等说明：MySQL 不支持 ADD COLUMN IF NOT EXISTS（8.0 亦不支持），
-- 重复执行会报 Duplicate column name，属预期，可忽略。

ALTER TABLE key_operation_record
    ADD COLUMN proof_path VARCHAR(2000) DEFAULT NULL COMMENT 'Merkle proof path: R:<hash>|L:<hash>|ROOT:<hash>';