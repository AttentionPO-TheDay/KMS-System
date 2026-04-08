-- wrk_revoke_key.lua
-- Pressure test script for REVOKE_KEY endpoint
-- Target: 5000+ TPS
-- Usage: wrk -t12 -c400 -d30s -s wrk_revoke_key.lua http://localhost:8082

local counter = 0
local threads = {}

local test_config = {
    user = "testuser",
    password = "Test@123456",
    -- NOTE: REVOKE is irreversible; ensure keys are pre-generated and reset between runs
    start_keyid = 10001,
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
    local_counter = id * 100000
end

function request()
    requests = requests + 1
    local_counter = local_counter + 1
    -- Use different keyId per request to avoid duplicate rejection
    local keyid = test_config.start_keyid + (local_counter % test_config.key_count)

    local body = string.format([[{
        "keyId": %d,
        "user": "%s",
        "password": "%s"
    }]], keyid, test_config.user, test_config.password)

    local headers = {
        ["Content-Type"] = "application/json",
        ["Accept"] = "application/json"
    }

    return wrk.format("POST", "/lifecycle/request/REVOKE_KEY", headers, body)
end

function response(status, headers, body)
    responses = responses + 1
end

function done(summary, latency, requests)
    print("------------ REVOKE_KEY Test Results ------------")
    print(string.format("Total Requests:   %d", summary.requests))
    print(string.format("Total Responses:  %d", summary.responses))
    print(string.format("Mean Latency:     %.2f ms", latency.mean / 1000))
    print(string.format("Max Latency:      %.2f ms", latency.max / 1000))
    print(string.format("P50 Latency:      %.2f ms", latency:percentile(50) / 1000))
    print(string.format("P99 Latency:      %.2f ms", latency:percentile(99) / 1000))
    local tps = summary.requests / (summary.duration / 1000000)
    print(string.format("TPS:              %.2f", tps))
    print(string.format("Errors: %d (connect:%d read:%d write:%d timeout:%d)",
        summary.errors.connect + summary.errors.read + summary.errors.write + summary.errors.timeout,
        summary.errors.connect,
        summary.errors.read,
        summary.errors.write,
        summary.errors.timeout))
    if tps >= 5000 then
        print(">>> TPS target MET! (>= 5000)")
    else
        print(string.format(">>> TPS below target (%.2f < 5000)", tps))
    end
    print("--------------------------------------------------")
end
