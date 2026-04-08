-- wrk_revoke_key.lua
-- 用于测试 REVOKE_KEY 接口的 wrk 压测脚本
-- 目标: 6000 TPS
-- 使用方法: wrk -t12 -c400 -d30s -s wrk_revoke_key.lua http://localhost:8080

-- 初始化计数器 (用于生成不同的 keyid)
local counter = 0
local threads = {}

-- 测试配置
local test_config = {
    -- 测试用户信息 (需要预先在系统中注册)
    user = "testuser",
    password = "Test@123456",
    -- 起始 keyid (需要预先在系统中生成一批密钥)
    -- 注意: REVOKE 是不可逆操作，测试后这些密钥将变为已回收状态
    start_keyid = 10001,
    -- 密钥数量范围 (每次测试需要重新生成)
    key_count = 10000
}

function setup(thread)
    thread:set("id", counter)
    table.insert(threads, thread)
    counter = counter + 1
end

function init(args)
    requests = 0
    responses = 0
    
    -- 每个线程独立的计数器
    local_counter = id * 100000
end

function request()
    requests = requests + 1
    local_counter = local_counter + 1
    
    -- 使用不同的 keyid (REVOKE 后密钥状态改变，不能重复回收)
    -- 如果需要持续测试，需要预先准备足够多的密钥
    local keyid = test_config.start_keyid + (local_counter % test_config.key_count)
    
    -- 构建 JSON 请求体
    local body = string.format([[{
        "keyid": "%d",
        "user": "%s",
        "password": "%s"
    }]], keyid, test_config.user, test_config.password)
    
    -- 设置请求头
    local headers = {
        ["Content-Type"] = "application/json",
        ["Accept"] = "application/json"
    }
    
    return wrk.format("POST", "/keymanage/request/REVOKE_KEY", headers, body)
end

function response(status, headers, body)
    responses = responses + 1
    
    -- 可选: 统计错误响应
    if status ~= 200 then
        -- 解析错误信息用于调试
        -- print("Error response: " .. status .. " - " .. body)
    end
end

function done(summary, latency, requests)
    -- 打印测试结果摘要
    print("------------ REVOKE_KEY 测试结果 ------------")
    print(string.format("总请求数: %d", summary.requests))
    print(string.format("总响应数: %d", summary.responses))
    print(string.format("平均延迟: %.2f ms", latency.mean / 1000))
    print(string.format("最大延迟: %.2f ms", latency.max / 1000))
    print(string.format("P50延迟: %.2f ms", latency:percentile(50) / 1000))
    print(string.format("P99延迟: %.2f ms", latency:percentile(99) / 1000))
    print(string.format("每秒请求数(TPS): %.2f", summary.requests / (summary.duration / 1000000)))
    print(string.format("错误数: %d (连接: %d, 读取: %d, 写入: %d, 超时: %d)", 
        summary.errors.connect + summary.errors.read + summary.errors.write + summary.errors.timeout,
        summary.errors.connect,
        summary.errors.read, 
        summary.errors.write,
        summary.errors.timeout))
    
    -- TPS 目标检查
    local tps = summary.requests / (summary.duration / 1000000)
    if tps >= 6000 then
        print(">>> TPS 达标! (>= 6000)")
    else
        print(string.format(">>> TPS 未达标! (%.2f < 6000)", tps))
    end
    print("----------------------------------------------")
end

--[[
使用说明:

1. 前置准备:
   - 确保后端服务运行在 localhost:8080
   - 注册测试用户: testuser / Test@123456
   - 为该用户预先生成大量密钥 (keyid: 10001-20000)
   - 注意: REVOKE 操作不可逆，每次测试需要重新准备密钥数据

2. 运行测试:
   # 轻量测试 (验证接口)
   wrk -t4 -c100 -d10s -s wrk_revoke_key.lua http://localhost:8080
   
   # 标准测试 (目标 6000 TPS)
   wrk -t12 -c400 -d30s -s wrk_revoke_key.lua http://localhost:8080
   
   # 压力测试 (极限性能)
   wrk -t16 -c800 -d60s -s wrk_revoke_key.lua http://localhost:8080

3. 参数说明:
   -t: 线程数 (建议为 CPU 核心数)
   -c: 并发连接数
   -d: 测试持续时间
   -s: Lua 脚本路径

4. 特别注意:
   - REVOKE 操作会将密钥状态改为已回收 (status=3)
   - 已回收的密钥不能再次回收，会返回错误
   - 每次性能测试前需要重新准备测试数据
   - 可以通过 SQL 批量重置密钥状态: 
     UPDATE kms_keymanage SET status='0' WHERE key_id BETWEEN 10001 AND 20000;

5. 调优建议:
   - 如果 TPS 不达标，检查数据库连接池配置
   - 检查 Kafka 消息队列是否成为瓶颈
   - REVOKE 涉及区块链上链，可能需要异步处理优化
   - 考虑增加后端实例数量
]]
