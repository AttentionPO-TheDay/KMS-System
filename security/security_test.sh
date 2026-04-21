#!/bin/bash
set -e

# Default values
CaseId=""
GenerateGoBaseUrl="http://127.0.0.1:8081"
LifecycleGoBaseUrl="http://127.0.0.1:8082"
GenerateJavaBaseUrl="http://127.0.0.1:9081"
LifecycleJavaBaseUrl="http://127.0.0.1:9082"
GenerateKeyPoolUrl="http://127.0.0.1:9081/internal/generate/keys/recent"
LifecycleVerifyUrl="http://127.0.0.1:9082/internal/lifecycle/key-status"
InternalToken="kms-generate-internal-secret-2026"
AcceptanceUser="acceptance_user"
AttackUserName="acceptance_user"
AttackUserPassword=""
AttackAdminName="admin"
AttackAdminPassword=""
AttackForeignUser="admin"
JsonOutput=0

# Parse arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --CaseId) CaseId="$2"; shift ;;
        --GenerateGoBaseUrl) GenerateGoBaseUrl="$2"; shift ;;
        --LifecycleGoBaseUrl) LifecycleGoBaseUrl="$2"; shift ;;
        --GenerateJavaBaseUrl) GenerateJavaBaseUrl="$2"; shift ;;
        --LifecycleJavaBaseUrl) LifecycleJavaBaseUrl="$2"; shift ;;
        --GenerateKeyPoolUrl) GenerateKeyPoolUrl="$2"; shift ;;
        --LifecycleVerifyUrl) LifecycleVerifyUrl="$2"; shift ;;
        --InternalToken) InternalToken="$2"; shift ;;
        --AcceptanceUser) AcceptanceUser="$2"; shift ;;
        --AttackUserName) AttackUserName="$2"; shift ;;
        --AttackUserPassword) AttackUserPassword="$2"; shift ;;
        --AttackAdminName) AttackAdminName="$2"; shift ;;
        --AttackAdminPassword) AttackAdminPassword="$2"; shift ;;
        --AttackForeignUser) AttackForeignUser="$2"; shift ;;
        --Json) JsonOutput=1 ;;
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift
done

if [ -z "$CaseId" ]; then
    echo "CaseId is required"
    exit 1
fi

ValidUa="04e5df58dcdd1d8bba99bc62b825fd1abbb8b4c2d32aa4ed79f48bb5b1dd2e14e09f5d47296df715dd748951b6e22805b0e71bfd4097e7db93cd6528cb68870f2a"
ValidEncrytType="无证书非对称加密"

# Initialize result state
res_caseId="$CaseId"
res_status="completed"
res_verdict="blocked"
res_passed=true
res_summary=""
res_error=""
res_notes="[]"
res_requests="[]"

# Helpers
add_trace() {
    local name="$1"
    local method="$2"
    local url="$3"
    local status_code="$4"
    local outcome="$5"
    local message="$6"
    local response_body="$7"

    # Truncate response_body if > 400 chars
    if [ ${#response_body} -gt 400 ]; then
        response_body="${response_body:0:400}"
    fi

    # Append to res_requests JSON array using jq
    local new_req
    new_req=$(jq -n \
        --arg name "$name" \
        --arg method "$method" \
        --arg url "$url" \
        --argjson statusCode "$status_code" \
        --arg outcome "$outcome" \
        --arg msg "$message" \
        --arg body "$response_body" \
        '{name: $name, method: $method, url: $url, statusCode: $statusCode, outcome: $outcome, message: $msg, responseBody: $body}')
    
    res_requests=$(echo "$res_requests" | jq ". + [$new_req]")
}

add_note() {
    local note="$1"
    res_notes=$(echo "$res_notes" | jq --arg n "$note" '. + [$n]')
}

invoke_http_request() {
    local method="$1"
    local url="$2"
    local headers_json="$3"
    local body="$4"
    local user_agent="$5"

    local curl_cmd=(curl -s -w "\n%{http_code}" -X "$method" "$url")
    
    if [ -n "$user_agent" ]; then
        curl_cmd+=(-A "$user_agent")
    fi

    if [ "$headers_json" != "null" ] && [ -n "$headers_json" ]; then
        while read -r key value; do
            curl_cmd+=(-H "$key: $value")
        done < <(echo "$headers_json" | jq -r 'to_entries | .[] | "\(.key) \(.value)"')
    fi

    if [ -n "$body" ]; then
        curl_cmd+=(-H "Content-Type: application/json")
        curl_cmd+=(-d "$body")
    fi

    local response
    response=$("${curl_cmd[@]}") || true
    
    local http_code
    http_code=$(echo "$response" | tail -n1)
    local response_body
    response_body=$(echo "$response" | sed '$d')

    echo "$http_code|||$response_body"
}

get_auth_token() {
    local base_url="$1"
    local username="$2"
    local password="$3"
    local trace_name="$4"

    if [ -z "$username" ] || [ -z "$password" ]; then
        echo "missing credentials for $trace_name" >&2
        exit 1
    fi

    local captcha_url="${base_url}/captchaImage"
    local res
    res=$(invoke_http_request "GET" "$captcha_url" "null" "")
    local code="${res%%|||*}"
    local body="${res#*|||}"
    
    add_trace "$trace_name captcha" "GET" "$captcha_url" "$code" "captcha" "load captcha config" "$body"
    
    local captcha_enabled
    captcha_enabled=$(echo "$body" | jq -r '.captchaEnabled // false')
    if [ "$captcha_enabled" = "true" ]; then
        echo "$trace_name requires captcha disabled" >&2
        exit 1
    fi

    local login_url="${base_url}/login"
    local payload
    payload=$(jq -n --arg u "$username" --arg p "$password" '{username: $u, password: $p, code: "", uuid: ""}')
    
    res=$(invoke_http_request "POST" "$login_url" "null" "$payload")
    code="${res%%|||*}"
    body="${res#*|||}"
    
    add_trace "$trace_name login" "POST" "$login_url" "$code" "login" "$username" "$body"
    
    local token
    token=$(echo "$body" | jq -r '.token // empty')
    if [ -z "$token" ] || [ "$code" -ge 400 ]; then
        echo "$trace_name login failed" >&2
        exit 1
    fi
    echo "$token"
}

get_internal_recent_keys() {
    local username="$1"
    local limit="$2"
    local created_after="$3"

    local url="${GenerateKeyPoolUrl}?userName=${username}&limit=${limit}"
    if [ -n "$created_after" ]; then
        # very simple url encoding for +
        created_after="${created_after//+/%2B}"
        url="${url}&createdAfter=${created_after}"
    fi

    local headers
    headers=$(jq -n --arg t "$InternalToken" '{"X-Internal-Token": $t}')
    
    local res
    res=$(invoke_http_request "GET" "$url" "$headers" "")
    local code="${res%%|||*}"
    local body="${res#*|||}"
    
    if [ "$code" -ge 400 ]; then
        echo "recent key query failed" >&2
        exit 1
    fi
    echo "$body" | jq -c '.data // []'
}

get_owned_lifecycle_key_id() {
    local token="$1"
    
    local url="${LifecycleJavaBaseUrl}/lifecycle/keymanage/list?pageNum=1&pageSize=1"
    local headers
    headers=$(jq -n --arg t "Bearer $token" '{"Authorization": $t}')
    
    local res
    res=$(invoke_http_request "GET" "$url" "$headers" "")
    local code="${res%%|||*}"
    local body="${res#*|||}"
    
    add_trace "lifecycle own list" "GET" "$url" "$code" "query" "load own key" "$body"
    
    local key_id
    key_id=$(echo "$body" | jq -r '.rows[0].keyId // empty')
    if [ -z "$key_id" ]; then
        key_id=$(echo "$body" | jq -r '.data[0].keyId // empty')
    fi
    
    if [ -z "$key_id" ]; then
        echo "no lifecycle key for attack user" >&2
        exit 1
    fi
    echo "$key_id"
}

# =====================================================================
# Generate 3 Attacks (Crypto Algorithm Core)
# =====================================================================

run_algo_tamper() {
    local url="${GenerateGoBaseUrl}/generate/request/ENROLL_KEY"
    local headers
    headers=$(jq -n --arg t "$InternalToken" '{"X-Internal-Token": $t}')

    local not_on_curve_ua="${ValidUa:0:128}00"
    local short_ua="${ValidUa:0:64}"
    local bad_prefix_ua="05${ValidUa:2}"
    
    local accepted=0

    # Test 1
    local payload
    payload=$(jq -n --arg u "$AcceptanceUser" --arg et "$ValidEncrytType" --arg ua "$not_on_curve_ua" '{user: $u, encryt_type: $et, encryt_name: "SSCL", ua: $ua, key_domain: "algo-test", key_name: "test", key_use: "attack"}')
    local res
    res=$(invoke_http_request "POST" "$url" "$headers" "$payload")
    local code="${res%%|||*}"
    local body="${res#*|||}"
    add_trace "algo tamper not-on-curve" "POST" "$url" "$code" "tamper" "not-on-curve" "$body"
    if [ "$code" -lt 400 ] && [[ ! "$body" == *"error"* ]] && [[ "$body" == *"\"code\":200"* || ! "$body" == *"code"* ]]; then
        ((accepted++))
    fi

    # Test 2
    payload=$(jq -n --arg u "$AcceptanceUser" --arg et "$ValidEncrytType" --arg ua "$short_ua" '{user: $u, encryt_type: $et, encryt_name: "SSCL", ua: $ua, key_domain: "algo-test", key_name: "test", key_use: "attack"}')
    res=$(invoke_http_request "POST" "$url" "$headers" "$payload")
    code="${res%%|||*}"
    body="${res#*|||}"
    add_trace "algo tamper invalid-length" "POST" "$url" "$code" "tamper" "invalid-length" "$body"
    if [ "$code" -lt 400 ] && [[ ! "$body" == *"error"* ]] && [[ "$body" == *"\"code\":200"* || ! "$body" == *"code"* ]]; then
        ((accepted++))
    fi

    # Test 3
    payload=$(jq -n --arg u "$AcceptanceUser" --arg et "$ValidEncrytType" --arg ua "$bad_prefix_ua" '{user: $u, encryt_type: $et, encryt_name: "SSCL", ua: $ua, key_domain: "algo-test", key_name: "test", key_use: "attack"}')
    res=$(invoke_http_request "POST" "$url" "$headers" "$payload")
    code="${res%%|||*}"
    body="${res#*|||}"
    add_trace "algo tamper invalid-prefix" "POST" "$url" "$code" "tamper" "invalid-prefix" "$body"
    if [ "$code" -lt 400 ] && [[ ! "$body" == *"error"* ]] && [[ "$body" == *"\"code\":200"* || ! "$body" == *"code"* ]]; then
        ((accepted++))
    fi

    if [ "$accepted" -gt 0 ]; then
        res_verdict="vulnerable"
        res_passed=false
        res_summary="Tampered public key parameters (curve/length/prefix) were accepted."
    else
        res_summary="All tampered algorithm parameters were correctly rejected."
    fi
}

run_algo_weak_param() {
    local url="${GenerateGoBaseUrl}/generate/request/ENROLL_KEY"
    local headers
    headers=$(jq -n --arg t "$InternalToken" '{"X-Internal-Token": $t}')
    
    local accepted=0

    # Test 1
    local payload
    payload=$(jq -n --arg u "$AcceptanceUser" --arg et "$ValidEncrytType" --arg ua "$ValidUa" '{user: $u, encryt_type: $et, encryt_name: "RSA-512", ua: $ua, key_domain: "algo-test", key_name: "test", key_use: "attack"}')
    local res
    res=$(invoke_http_request "POST" "$url" "$headers" "$payload")
    local code="${res%%|||*}"
    local body="${res#*|||}"
    add_trace "algo weak param weak-rsa" "POST" "$url" "$code" "weak-param" "weak-rsa" "$body"
    if [ "$code" -lt 400 ] && [[ ! "$body" == *"error"* ]] && [[ ! "$body" == *"unsupported"* ]]; then
        ((accepted++))
    fi

    # Test 2
    payload=$(jq -n --arg u "$AcceptanceUser" --arg et "$ValidEncrytType" --arg ua "$ValidUa" '{user: $u, encryt_type: $et, encryt_name: "MD5", ua: $ua, key_domain: "algo-test", key_name: "test", key_use: "attack"}')
    res=$(invoke_http_request "POST" "$url" "$headers" "$payload")
    code="${res%%|||*}"
    body="${res#*|||}"
    add_trace "algo weak param weak-md5" "POST" "$url" "$code" "weak-param" "weak-md5" "$body"
    if [ "$code" -lt 400 ] && [[ ! "$body" == *"error"* ]] && [[ ! "$body" == *"unsupported"* ]]; then
        ((accepted++))
    fi

    # Test 3
    payload=$(jq -n --arg u "$AcceptanceUser" --arg ua "$ValidUa" '{user: $u, encryt_type: "", encryt_name: "SSCL", ua: $ua, key_domain: "algo-test", key_name: "test", key_use: "attack"}')
    res=$(invoke_http_request "POST" "$url" "$headers" "$payload")
    code="${res%%|||*}"
    body="${res#*|||}"
    add_trace "algo weak param empty-type" "POST" "$url" "$code" "weak-param" "empty-type" "$body"
    if [ "$code" -lt 400 ] && [[ ! "$body" == *"error"* ]] && [[ ! "$body" == *"only certless"* ]]; then
        ((accepted++))
    fi

    if [ "$accepted" -gt 0 ]; then
        res_verdict="vulnerable"
        res_passed=false
        res_summary="Weak algorithm names or empty types were accepted by the system."
    else
        res_summary="Weak algorithms and parameter downgrades were correctly rejected."
    fi
}

run_algo_malformed() {
    local url="${GenerateGoBaseUrl}/generate/request/ENROLL_KEY"
    local headers
    headers=$(jq -n --arg t "$InternalToken" '{"X-Internal-Token": $t}')
    
    local non_hex_ua="04abXXzz"
    for i in {1..122}; do non_hex_ua="${non_hex_ua}A"; done
    local super_long_ua="04"
    for i in {1..2000}; do super_long_ua="${super_long_ua}F"; done

    local accepted=0

    # Test 1
    local payload
    payload=$(jq -n --arg u "$AcceptanceUser" --arg et "$ValidEncrytType" --arg ua "$non_hex_ua" '{user: $u, encryt_type: $et, encryt_name: "SSCL", ua: $ua}')
    local res
    res=$(invoke_http_request "POST" "$url" "$headers" "$payload")
    local code="${res%%|||*}"
    local body="${res#*|||}"
    add_trace "algo malformed non-hex" "POST" "$url" "$code" "malformed" "non-hex" "$body"
    if [ "$code" -lt 400 ] && [[ ! "$body" == *"error"* ]] && [[ ! "$body" == *"invalid"* ]]; then
        ((accepted++))
    fi

    # Test 2
    payload=$(jq -n --arg u "$AcceptanceUser" --arg et "$ValidEncrytType" --arg ua "$super_long_ua" '{user: $u, encryt_type: $et, encryt_name: "SSCL", ua: $ua}')
    res=$(invoke_http_request "POST" "$url" "$headers" "$payload")
    code="${res%%|||*}"
    body="${res#*|||}"
    add_trace "algo malformed super-long" "POST" "$url" "$code" "malformed" "super-long" "$body"
    if [ "$code" -lt 400 ] && [[ ! "$body" == *"error"* ]] && [[ ! "$body" == *"invalid"* ]]; then
        ((accepted++))
    fi

    # Test 3
    local malformed_json='{ "user": "acceptance", "encryt_type": "无证书非对称加密", "ua": "'"$ValidUa"'", "broken'
    res=$(invoke_http_request "POST" "$url" "$headers" "$malformed_json")
    code="${res%%|||*}"
    body="${res#*|||}"
    add_trace "algo malformed broken-json" "POST" "$url" "$code" "malformed" "broken-json" "$body"
    if [ "$code" -lt 400 ] && [[ ! "$body" == *"error"* ]]; then
        ((accepted++))
    fi

    if [ "$accepted" -gt 0 ]; then
        res_verdict="vulnerable"
        res_passed=false
        res_summary="Malformed cryptographic payload was accepted or caused unhandled errors."
    else
        res_summary="Malformed payloads were safely intercepted and rejected."
    fi
}

run_lifecycle_sql() {
    local token
    token=$(get_auth_token "$LifecycleJavaBaseUrl" "$AttackUserName" "$AttackUserPassword" "lifecycle normal user")
    
    # URL encoded values: "' OR 1=1 -- kms_sql_test" -> %27%20OR%201%3D1%20--%20kms_sql_test
    # "' OR '1'='1 kms_sql_test" -> %27%20OR%20%271%27%3D%271%20kms_sql_test
    local keyPayload="%27%20OR%201%3D1%20--%20kms_sql_test"
    local recordPayload="%27%20OR%20%271%27%3D%271%20kms_sql_test"

    local headers
    headers=$(jq -n --arg t "Bearer $token" '{"Authorization": $t}')

    local keyUrl="${LifecycleJavaBaseUrl}/lifecycle/keymanage/list?pageNum=1&pageSize=10&keyName=${keyPayload}"
    local res
    res=$(invoke_http_request "GET" "$keyUrl" "$headers" "")
    local code="${res%%|||*}"
    local body="${res#*|||}"
    add_trace "lifecycle sql key-list" "GET" "$keyUrl" "$code" "sql-injection" "inject keyName" "$body"
    local keyRowsCount
    keyRowsCount=$(echo "$body" | jq '.rows | length // 0')

    local recordUrl="${LifecycleJavaBaseUrl}/lifecycle/operation-record/list?pageNum=1&pageSize=10&actionType=${recordPayload}"
    local res2
    res2=$(invoke_http_request "GET" "$recordUrl" "$headers" "")
    local code2="${res2%%|||*}"
    local body2="${res2#*|||}"
    add_trace "lifecycle sql record-list" "GET" "$recordUrl" "$code2" "sql-injection" "inject actionType" "$body2"
    local recordRowsCount
    recordRowsCount=$(echo "$body2" | jq '.rows | length // 0')

    if [ "$code" -ge 500 ] || [ "$code2" -ge 500 ] || [[ "$body" == *"SQL"* ]] || [[ "$body2" == *"SQL"* ]] || [ "$keyRowsCount" -gt 0 ] || [ "$recordRowsCount" -gt 0 ]; then
        res_verdict="vulnerable"
        res_passed=false
        res_summary="SQL injection probe returned data or triggered server-side SQL errors."
    else
        res_summary="SQL injection probe returned no data and no SQL error."
    fi
}

run_lifecycle_xss() {
    local token
    token=$(get_auth_token "$LifecycleJavaBaseUrl" "$AttackUserName" "$AttackUserPassword" "lifecycle normal user")
    
    local key_id
    key_id=$(get_owned_lifecycle_key_id "$token")
    
    local payload_text='\"><script>alert("kms-xss")</script>'
    local update_url="${LifecycleJavaBaseUrl}/lifecycle/keymanage"
    
    local headers
    headers=$(jq -n --arg t "Bearer $token" '{"Authorization": $t}')
    
    local payload
    payload=$(jq -n --arg kid "$key_id" --arg text "$payload_text" '{keyId: $kid, keyName: $text, keyUse: $text, keyDomain: $text}')
    
    local res
    res=$(invoke_http_request "PUT" "$update_url" "$headers" "$payload")
    local code="${res%%|||*}"
    local body="${res#*|||}"
    add_trace "lifecycle xss update" "PUT" "$update_url" "$code" "xss" "submit payload" "$body"

    sleep 4

    local detail_url="${LifecycleJavaBaseUrl}/lifecycle/keymanage/${key_id}"
    local res2
    res2=$(invoke_http_request "GET" "$detail_url" "$headers" "")
    local code2="${res2%%|||*}"
    local body2="${res2#*|||}"
    add_trace "lifecycle xss detail" "GET" "$detail_url" "$code2" "xss" "read back value" "$body2"

    if [ "$code" -lt 400 ] && [[ "$body2" == *"<script>"* ]]; then
        res_verdict="vulnerable"
        res_passed=false
        res_summary="XSS payload was accepted and returned in lifecycle detail output."
    else
        res_summary="XSS payload was not visible in lifecycle detail output."
    fi
}

run_platform_scanner() {
    local url="${LifecycleJavaBaseUrl}/captchaImage"
    
    local res
    res=$(invoke_http_request "GET" "$url" "null" "" "sqlmap/1.5.8#dev")
    local code="${res%%|||*}"
    local body="${res#*|||}"
    add_trace "scanner sqlmap" "GET" "$url" "$code" "scanner" "sqlmap UA" "$body"
    local sqlmap_code="$code"
    
    res=$(invoke_http_request "GET" "$url" "null" "" "Mozilla/4.75 (Nikto/2.1.6)")
    code="${res%%|||*}"
    body="${res#*|||}"
    add_trace "scanner nikto" "GET" "$url" "$code" "scanner" "nikto UA" "$body"
    local nikto_code="$code"
    
    res=$(invoke_http_request "GET" "$url" "null" "" "Mozilla/5.0 Windows NT 10.0")
    code="${res%%|||*}"
    body="${res#*|||}"
    add_trace "scanner normal-ua" "GET" "$url" "$code" "scanner" "normal UA check" "$body"
    local normal_code="$code"
    
    local reset_url="${LifecycleJavaBaseUrl}/internal/security/reset-blacklist"
    local headers
    headers=$(jq -n --arg t "$InternalToken" '{"X-Internal-Token": $t}')
    res=$(invoke_http_request "POST" "$reset_url" "$headers" "")
    code="${res%%|||*}"
    body="${res#*|||}"
    add_trace "scanner reset" "POST" "$reset_url" "$code" "reset" "clear blacklist" "$body"

    if [ "$sqlmap_code" != "403" ] || [ "$nikto_code" != "403" ]; then
        res_verdict="vulnerable"
        res_passed=false
        res_summary="Scanner User-Agents were not blocked with HTTP 403."
    elif [ "$normal_code" == "403" ]; then
        res_verdict="vulnerable"
        res_passed=false
        res_summary="Normal User-Agent was incorrectly blocked after scanner requests."
    else
        res_summary="Scanner User-Agents were correctly detected and blocked with 403. Blacklist cleared."
    fi
}

run_platform_bruteforce() {
    local url="${LifecycleJavaBaseUrl}/login"
    local login_fail_count=0
    local was_locked=false

    for i in {1..6}; do
        local payload
        payload=$(jq -n --arg u "$AttackUserName" --arg p "wrongpassword_$i" '{username: $u, password: $p, code: "", uuid: ""}')
        local res
        res=$(invoke_http_request "POST" "$url" "null" "$payload")
        local code="${res%%|||*}"
        local body="${res#*|||}"
        add_trace "bruteforce attempt $i" "POST" "$url" "$code" "bruteforce" "login attempt" "$body"
        
        if [ "$code" -ge 400 ] || [[ "$body" == *"\"code\": 500"* ]] || [[ "$body" == *"\"code\":500"* ]]; then
            ((login_fail_count++))
        fi
        if [[ "$body" == *"锁定"* ]] || [[ "$body" == *"lock"* ]]; then
            was_locked=true
        fi
    done
    
    local reset_url="${LifecycleJavaBaseUrl}/internal/security/reset-login-lock"
    local headers
    headers=$(jq -n --arg t "$InternalToken" '{"X-Internal-Token": $t}')
    local res_reset
    res_reset=$(invoke_http_request "POST" "$reset_url" "$headers" "")
    local code_reset="${res_reset%%|||*}"
    local body_reset="${res_reset#*|||}"
    add_trace "bruteforce reset" "POST" "$reset_url" "$code_reset" "reset" "clear login lock" "$body_reset"

    if [ "$was_locked" = true ] && [ "$login_fail_count" -ge 6 ]; then
        res_summary="Login brute-force successfully triggered account lock after 5 attempts. Lock cleared."
    else
        res_verdict="vulnerable"
        res_passed=false
        res_summary="Login brute-force failed to trigger account lock after 6 attempts."
    fi
}

run_platform_clickjack() {
    local vulnerable_count=0
    
    # URL 1
    local url1="${GenerateJavaBaseUrl}/login"
    local res1
    res1=$(invoke_http_request "GET" "$url1" "null" "")
    local code1="${res1%%|||*}"
    add_trace "clickjack java-generate" "GET" "$url1" "$code1" "headers" "fetch headers" "Headers fetched"
    
    # For curl we didn't output headers in the bash helper cleanly yet.
    # Let's do a dedicated curl -I
    local headers1
    headers1=$(curl -s -I -X GET "$url1" || true)
    
    local has_protection1=false
    if echo "$headers1" | grep -iE "X-Frame-Options:.*(SAMEORIGIN|DENY)" >/dev/null; then has_protection1=true; fi
    if echo "$headers1" | grep -iE "Content-Security-Policy:.*frame-ancestors" >/dev/null; then has_protection1=true; fi
    if [ "$has_protection1" = false ]; then ((vulnerable_count++)); fi

    # URL 2
    local url2="${LifecycleJavaBaseUrl}/login"
    local res2
    res2=$(invoke_http_request "GET" "$url2" "null" "")
    local code2="${res2%%|||*}"
    add_trace "clickjack java-lifecycle" "GET" "$url2" "$code2" "headers" "fetch headers" "Headers fetched"
    
    local headers2
    headers2=$(curl -s -I -X GET "$url2" || true)
    
    local has_protection2=false
    if echo "$headers2" | grep -iE "X-Frame-Options:.*(SAMEORIGIN|DENY)" >/dev/null; then has_protection2=true; fi
    if echo "$headers2" | grep -iE "Content-Security-Policy:.*frame-ancestors" >/dev/null; then has_protection2=true; fi
    if [ "$has_protection2" = false ]; then ((vulnerable_count++)); fi

    if [ "$vulnerable_count" -gt 0 ]; then
        res_verdict="vulnerable"
        res_passed=false
        res_summary="Some endpoints are missing X-Frame-Options or CSP frame-ancestors protection."
    else
        res_summary="All endpoints have clickjacking protection headers (SAMEORIGIN or frame-ancestors)."
    fi
}

run_case() {
    local case_id="$1"
    
    # Wrap in subshell to catch errors if we set -e, but we handle it
    case "$case_id" in
        "algo-tamper") run_algo_tamper ;;
        "algo-weak-param") run_algo_weak_param ;;
        "algo-malformed") run_algo_malformed ;;
        "lifecycle-sql") run_lifecycle_sql ;;
        "lifecycle-xss") run_lifecycle_xss ;;
        "platform-scanner") run_platform_scanner ;;
        "platform-bruteforce") run_platform_bruteforce ;;
        "platform-clickjack") run_platform_clickjack ;;
        *) 
            res_status="error"
            res_verdict="error"
            res_passed=false
            res_summary="unknown case id: $case_id"
            ;;
    esac
}

# Run the test case
set +e
run_case "$CaseId"
local_exit_code=$?
set -e

if [ $local_exit_code -ne 0 ] && [ "$res_status" != "error" ]; then
    res_status="error"
    res_verdict="error"
    res_passed=false
    res_summary="attack execution failed"
fi

if [ "$JsonOutput" -eq 1 ]; then
    jq -n \
        --arg caseId "$res_caseId" \
        --arg status "$res_status" \
        --arg verdict "$res_verdict" \
        --argjson passed "$res_passed" \
        --arg summary "$res_summary" \
        --arg error "$res_error" \
        --argjson notes "$res_notes" \
        --argjson requests "$res_requests" \
        '{caseId: $caseId, status: $status, verdict: $verdict, passed: $passed, summary: $summary, error: $error, notes: $notes, requests: $requests}'
else
    jq -n \
        --arg caseId "$res_caseId" \
        --arg status "$res_status" \
        --arg verdict "$res_verdict" \
        --argjson passed "$res_passed" \
        --arg summary "$res_summary" \
        --arg error "$res_error" \
        --argjson notes "$res_notes" \
        --argjson requests "$res_requests" \
        '{caseId: $caseId, status: $status, verdict: $verdict, passed: $passed, summary: $summary, error: $error, notes: $notes, requests: $requests}'
fi
