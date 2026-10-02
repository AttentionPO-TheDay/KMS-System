-- =============================================================================
-- 22_purge_plaintext_aes_demo_key.sql
-- -----------------------------------------------------------------------------
-- 背景（对应重构计划 P2 的 D12 / Q9）
--
-- `kms.keymanage` 里有一行演示数据，它的 `key_value` **就是一把明文对称密钥**：
--
--   key_id=1  user_id=1  encryt_type='AES'  encryt_name='AES-256'
--   key_name='example_key'  key_value='s3cr3tK3y'  status=3（已回收）
--
-- 它是主 KMS 那条 AES 生成路径唯一能触达的数据。那条路径已按 D12 删除
-- （`LifecycleService.generateAesKey()` 与 AES 分支），理由是：
--   1. 架构上「对称密钥完全归分发模块，且统一用 SM4」，主 KMS 不该再养一套对称密钥生成；
--   2. 界面上根本走不到它 —— 没有任何前端页面能产生 AES 密钥；
--   3. 留着它等于在密钥表里存一把明文对称密钥，而这正是「管理员不得查看对称密钥明文」
--      这条要求最直白的反例。
--
-- 影响面（删除前已核对）：`key_operation_record` 与 `key_distribute_record` 中
-- 引用 key_id=1 的行数均为 0，因此删除不产生孤儿记录。
--
-- 幂等：DELETE，可重复执行。
-- =============================================================================

-- 只删这一类：明确是 AES 对称密钥、且 key_value 没有 `ua`（非无证书体系）的演示行。
-- 用 encryt_type/encryt_name 双条件，避免误伤任何非对称密钥。
-- ⚠️ 必须有这一行（2026-09-30 补）：本文件含中文，而**管道导入**
--    （docker-entrypoint-initdb.d / docker exec -i ... mysql < file）时
--    客户端字符集不保证是 utf8mb4。缺了它中文会按单字节解析后再以 utf8mb4 存储，
--    即**双重编码** —— 库里存的是 C3A5C2B7... 这类字节，前端渲染成「å·¥ä½œå°」。
--    本文件此前正因缺这一行，把 20 个菜单名写坏（由 42_*.sql 修复）。
SET NAMES utf8mb4;

DELETE FROM keymanage
WHERE (encryt_type = 'AES' OR encryt_name IN ('AES', 'AES-256'))
  AND ua IS NULL;

-- 自检：应为 0
SELECT '残留的 AES 明文对称密钥行（应为 0）' AS check_item, COUNT(*) AS actual
FROM keymanage
WHERE (encryt_type = 'AES' OR encryt_name IN ('AES', 'AES-256'))
  AND ua IS NULL;