-- verify.sql
-- 用于验证密钥回收成功率的 SQL 脚本
-- 逻辑：统计指定 ID 范围内状态变为 '3' (已回收) 的数量，并除以请求总数
-- 请在 MySQL 客户端中执行

-- ==========================================
-- 1. 输入参数 (请根据实际压测情况修改这里)
-- ==========================================
SET @start_id = 10000;      -- 起始 Key ID (需与 wrk 脚本一致)
SET @request_count = 10000; -- 压测发送的请求总数 (wrk -n 或估算值)

-- ==========================================
-- 2. 自动计算结束 ID
-- ==========================================
SET @end_id = @start_id + @request_count - 1;

-- ==========================================
-- 3. 执行统计
-- ==========================================
SELECT 
    @start_id as '起始ID',
    @end_id as '结束ID',
    @request_count as '计划请求总数',
    -- 统计该范围内实际存在的 Key 总数 (检查数据准备是否充分)
    COUNT(*) as '库中实际Key数',
    -- 统计状态为 3 (REVOKED) 的数量
    SUM(CASE WHEN status = '3' THEN 1 ELSE 0 END) as '成功回收数',
    -- 计算回收率：成功回收数 / 计划请求总数
    CONCAT(ROUND(SUM(CASE WHEN status = '3' THEN 1 ELSE 0 END) / @request_count * 100, 2), '%') as '回收成功率'
FROM keymanage 
WHERE key_id BETWEEN @start_id AND @end_id;

-- ==========================================
-- 4. 状态抽查 (随机选取5条记录确认状态)
-- ==========================================
SELECT key_id, user_name, status, upd_time 
FROM keymanage 
WHERE key_id BETWEEN @start_id AND @end_id AND status = '3' 
ORDER BY RAND()
LIMIT 5;
