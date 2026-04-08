-- revoke_test.lua
-- 用于测试 KMS 密钥回收接口吞吐量的 wrk 脚本

-- 配置项：请根据实际情况修改
local start_key_id = 10000      -- 起始密钥ID（请确保数据库中存在这些ID）
local username = "test"        -- 测试用户名
local password = "123456"  -- 测试密码（需与数据库一致）

local counter = 0

-- 初始化函数
function setup(thread)
   thread:set("id", counter)
   -- 每个线程分配一个独立的 ID 段，避免并发冲突
   -- 但为了简单起见，这里假设单线程执行或不介意重复尝试删除
   -- 如果要多线程精确删除，需要更复杂的逻辑，这里简化为递增
end

-- 请求构造函数
function request()
   -- 获取当前请求的 ID
   local current_id = start_key_id + counter
   counter = counter + 1
   
   -- 构造 JSON 请求体
   -- 对应 Java Controller 的参数: keyid, user, password
   local body = string.format('{"keyid": "%d", "user": "%s", "password": "%s"}', 
       current_id, username, password)
   
   -- 返回 POST 请求对象
   return wrk.format("POST", "/keymanage/request/REVOKE_KEY", 
       {["Content-Type"] = "application/json"}, 
       body)
end

-- 响应处理函数（可选，用于调试）
-- function response(status, headers, body)
--    if status ~= 200 then
--       print("Error status: " .. status)
--    end
-- end
