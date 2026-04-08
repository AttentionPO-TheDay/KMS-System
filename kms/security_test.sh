#!/bin/bash
# ============================================================
# KMS系统非法参数注入防御测试脚本
# 测试项: 1.11.2 非法参数注入网络攻击防御测试
# 测试目标: http://74.48.83.221:80
# ============================================================

# API接口地址（后端接口需要加/prod-api前缀）
BASE_URL="http://74.48.83.221:80"
API_URL="http://74.48.83.221:80/prod-api"
PASS_COUNT=0
FAIL_COUNT=0
TOTAL_COUNT=0

# 网络连通性检测
check_connectivity() {
    echo "正在检测网络连通性..."
    echo "------------------------------------------------------------"
    
    # 测试前端页面
    frontend_code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "$BASE_URL/" 2>/dev/null)
    if [ "$frontend_code" == "000" ]; then
        echo -e "${RED}[错误]${NC} 无法连接到前端服务 $BASE_URL/"
        echo "       请检查网络连接或服务器状态"
        exit 1
    else
        echo -e "${GREEN}[OK]${NC} 前端服务连接正常 (状态码: $frontend_code)"
    fi
    
    # 测试后端API
    api_code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "$API_URL/captchaImage" 2>/dev/null)
    if [ "$api_code" == "000" ]; then
        echo -e "${RED}[错误]${NC} 无法连接到后端API $API_URL/"
        echo "       请检查网络连接或服务器状态"
        exit 1
    else
        echo -e "${GREEN}[OK]${NC} 后端API连接正常 (状态码: $api_code)"
    fi
    
    echo ""
}

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印分隔线
print_separator() {
    echo "============================================================"
}

# 打印测试标题
print_title() {
    echo ""
    print_separator
    echo -e "${BLUE}$1${NC}"
    print_separator
}

# 检测SQL注入是否被阻止
# 参数: $1=测试编号 $2=测试描述 $3=HTTP状态码 $4=响应内容
check_sql_injection() {
    local test_id=$1
    local description=$2
    local http_code=$3
    local response=$4
    TOTAL_COUNT=$((TOTAL_COUNT + 1))
    
    # 判断是否注入成功(这些情况说明注入失败/被阻止)
    # 1. 返回4xx/5xx错误码
    # 2. 响应包含错误信息但不包含敏感数据泄露
    # 3. 响应包含"参数错误"、"非法"等提示
    
    if [[ $http_code -ge 400 ]] || \
       [[ $response == *"用户不存在"* ]] || \
       [[ $response == *"密码错误"* ]] || \
       [[ $response == *"参数错误"* ]] || \
       [[ $response == *"非法"* ]] || \
       [[ $response == *"验证码"* ]] || \
       [[ $response == *"error"* ]] || \
       [[ $response == *"失败"* ]]; then
        echo -e "${GREEN}[PASS]${NC} $test_id: $description"
        echo "       状态码: $http_code | 系统正确拦截恶意请求"
        PASS_COUNT=$((PASS_COUNT + 1))
    else
        # 检查是否有SQL错误信息泄露
        if [[ $response == *"SQL"* ]] || \
           [[ $response == *"syntax"* ]] || \
           [[ $response == *"mysql"* ]] || \
           [[ $response == *"SELECT"* ]] || \
           [[ $response == *"token"* && $response != *"获取token失败"* ]]; then
            echo -e "${RED}[FAIL]${NC} $test_id: $description"
            echo "       状态码: $http_code | 可能存在SQL注入漏洞或信息泄露"
            echo "       响应: ${response:0:200}"
            FAIL_COUNT=$((FAIL_COUNT + 1))
        else
            echo -e "${GREEN}[PASS]${NC} $test_id: $description"
            echo "       状态码: $http_code | 未发现注入成功迹象"
            PASS_COUNT=$((PASS_COUNT + 1))
        fi
    fi
}

# 检测XSS是否被阻止
check_xss() {
    local test_id=$1
    local description=$2
    local http_code=$3
    local response=$4
    local payload=$5
    TOTAL_COUNT=$((TOTAL_COUNT + 1))
    
    # 检查响应中是否包含未转义的XSS payload
    if [[ $response == *"<script>"* ]] || \
       [[ $response == *"onerror="* ]] || \
       [[ $response == *"onload="* ]] || \
       [[ $response == *"onmouseover="* ]]; then
        echo -e "${RED}[FAIL]${NC} $test_id: $description"
        echo "       状态码: $http_code | XSS payload未被过滤"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    else
        echo -e "${GREEN}[PASS]${NC} $test_id: $description"
        echo "       状态码: $http_code | XSS payload被正确过滤或拦截"
        PASS_COUNT=$((PASS_COUNT + 1))
    fi
}

# 检测点击劫持防护
check_clickjacking() {
    local test_id=$1
    local description=$2
    local headers=$3
    TOTAL_COUNT=$((TOTAL_COUNT + 1))
    
    if [[ $headers == *"X-Frame-Options"* ]] || \
       [[ $headers == *"x-frame-options"* ]] || \
       [[ $headers == *"frame-ancestors"* ]]; then
        echo -e "${GREEN}[PASS]${NC} $test_id: $description"
        echo "       响应头包含点击劫持防护"
        # 提取并显示相关header
        echo "$headers" | grep -i "frame" || echo "$headers" | grep -i "content-security"
        PASS_COUNT=$((PASS_COUNT + 1))
    else
        echo -e "${RED}[FAIL]${NC} $test_id: $description"
        echo "       响应头缺少 X-Frame-Options 或 CSP frame-ancestors"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
}

# ============================================================
# 1. SQL注入测试
# ============================================================
print_title "1. SQL注入攻击测试"

# 先检测网络连通性
check_connectivity

echo ""
echo "1.1 登录接口SQL注入测试 (/prod-api/login)"
echo "------------------------------------------------------------"

# SQL-01: 用户名SQL注入 - 单引号闭合
response=$(curl -s -w "\n%{http_code}" -X POST "$API_URL/login" \
    -H "Content-Type: application/json" \
    -d '{"username":"admin'\'' OR '\''1'\''='\''1","password":"123456"}' 2>/dev/null)
http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')
check_sql_injection "SQL-01" "用户名注入(OR 1=1)" "$http_code" "$body"

# SQL-02: 密码SQL注入
response=$(curl -s -w "\n%{http_code}" -X POST "$API_URL/login" \
    -H "Content-Type: application/json" \
    -d '{"username":"admin","password":"'\'' OR '\''1'\''='\''1'\'' --"}' 2>/dev/null)
http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')
check_sql_injection "SQL-02" "密码注入(OR 1=1 注释)" "$http_code" "$body"

# SQL-03: UNION注入
response=$(curl -s -w "\n%{http_code}" -X POST "$API_URL/login" \
    -H "Content-Type: application/json" \
    -d '{"username":"'\'' UNION SELECT * FROM sys_user--","password":"123456"}' 2>/dev/null)
http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')
check_sql_injection "SQL-03" "UNION联合查询注入" "$http_code" "$body"

# SQL-04: 时间盲注
echo ""
echo "1.2 时间盲注测试 (检测响应延迟)"
echo "------------------------------------------------------------"
start_time=$(date +%s.%N)
response=$(curl -s -w "\n%{http_code}" -X POST "$API_URL/login" \
    -H "Content-Type: application/json" \
    --max-time 10 \
    -d '{"username":"admin'\'' AND SLEEP(5)--","password":"123456"}' 2>/dev/null)
end_time=$(date +%s.%N)
duration=$(echo "$end_time - $start_time" | bc 2>/dev/null || echo "0")
http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')
TOTAL_COUNT=$((TOTAL_COUNT + 1))

if (( $(echo "$duration > 4" | bc -l 2>/dev/null || echo "0") )); then
    echo -e "${RED}[FAIL]${NC} SQL-04: 时间盲注(SLEEP)"
    echo "       响应时间: ${duration}s | 可能存在时间盲注漏洞"
    FAIL_COUNT=$((FAIL_COUNT + 1))
else
    echo -e "${GREEN}[PASS]${NC} SQL-04: 时间盲注(SLEEP)"
    echo "       响应时间: ${duration}s | SLEEP函数未被执行"
    PASS_COUNT=$((PASS_COUNT + 1))
fi

echo ""
echo "1.3 注册接口SQL注入测试 (/prod-api/keymanage/request/Register)"
echo "------------------------------------------------------------"

# SQL-05: 注册接口用户名注入
response=$(curl -s -w "\n%{http_code}" -X POST "$API_URL/keymanage/request/Register" \
    -H "Content-Type: application/json" \
    -d '{"user":"test'\''--; DROP TABLE sys_user;--","password":"Test@12345"}' 2>/dev/null)
http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')
check_sql_injection "SQL-05" "注册接口DROP TABLE注入" "$http_code" "$body"

# SQL-06: 注册接口堆叠查询
response=$(curl -s -w "\n%{http_code}" -X POST "$API_URL/keymanage/request/Register" \
    -H "Content-Type: application/json" \
    -d '{"user":"test'\''; SELECT * FROM sys_user WHERE '\''1'\''='\''1","password":"Test@12345"}' 2>/dev/null)
http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')
check_sql_injection "SQL-06" "注册接口堆叠查询注入" "$http_code" "$body"

echo ""
echo "1.4 密钥申请接口SQL注入测试 (/prod-api/keymanage/request/ENROLL_KEY)"
echo "------------------------------------------------------------"

# SQL-07: 密钥申请接口注入
response=$(curl -s -w "\n%{http_code}" -X POST "$API_URL/keymanage/request/ENROLL_KEY" \
    -H "Content-Type: application/json" \
    -d '{"user":"admin'\'' AND 1=1--","password":"123456","encryt_name":"SM2","ua":"test"}' 2>/dev/null)
http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')
check_sql_injection "SQL-07" "密钥申请接口布尔注入" "$http_code" "$body"

# ============================================================
# 2. XSS跨站脚本攻击测试
# ============================================================
print_title "2. XSS跨站脚本攻击测试"

echo ""
echo "2.1 注册接口XSS测试"
echo "------------------------------------------------------------"

# XSS-01: script标签注入
response=$(curl -s -w "\n%{http_code}" -X POST "$API_URL/keymanage/request/Register" \
    -H "Content-Type: application/json" \
    -d '{"user":"<script>alert(1)</script>","password":"Test@12345"}' 2>/dev/null)
http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')
check_xss "XSS-01" "script标签注入" "$http_code" "$body" "<script>"

# XSS-02: img onerror注入
response=$(curl -s -w "\n%{http_code}" -X POST "$API_URL/keymanage/request/Register" \
    -H "Content-Type: application/json" \
    -d '{"user":"<img src=x onerror=alert(1)>","password":"Test@12345"}' 2>/dev/null)
http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')
check_xss "XSS-02" "img onerror事件注入" "$http_code" "$body" "onerror"

# XSS-03: svg onload注入
response=$(curl -s -w "\n%{http_code}" -X POST "$API_URL/keymanage/request/Register" \
    -H "Content-Type: application/json" \
    -d '{"user":"<svg onload=alert(1)>","password":"Test@12345"}' 2>/dev/null)
http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')
check_xss "XSS-03" "svg onload事件注入" "$http_code" "$body" "onload"

echo ""
echo "2.2 登录接口XSS测试"
echo "------------------------------------------------------------"

# XSS-04: 登录用户名XSS
response=$(curl -s -w "\n%{http_code}" -X POST "$API_URL/login" \
    -H "Content-Type: application/json" \
    -d '{"username":"<script>document.cookie</script>","password":"123456"}' 2>/dev/null)
http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')
check_xss "XSS-04" "登录用户名script注入" "$http_code" "$body" "<script>"

# XSS-05: 事件属性注入
response=$(curl -s -w "\n%{http_code}" -X POST "$API_URL/login" \
    -H "Content-Type: application/json" \
    -d '{"username":"\" onmouseover=\"alert(1)","password":"123456"}' 2>/dev/null)
http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')
check_xss "XSS-05" "事件属性onmouseover注入" "$http_code" "$body" "onmouseover"

# ============================================================
# 3. 点击劫持攻击测试
# ============================================================
print_title "3. 点击劫持攻击测试"

echo ""
echo "3.1 响应头安全配置检测"
echo "------------------------------------------------------------"

# CLK-01: 检测主页X-Frame-Options (前端静态页面，由Nginx返回)
headers=$(curl -s -I "$BASE_URL/" 2>/dev/null)
check_clickjacking "CLK-01" "主页X-Frame-Options检测(Nginx)" "$headers"

# CLK-02: 检测后端API (由Spring Security返回)
headers=$(curl -s -D - -o /dev/null "$API_URL/captchaImage" 2>/dev/null)
check_clickjacking "CLK-02" "后端API响应头检测(Spring)" "$headers"

# CLK-03: 检测登录接口
headers=$(curl -s -D - -o /dev/null -X POST "$API_URL/login" -H "Content-Type: application/json" -d '{}' 2>/dev/null)
check_clickjacking "CLK-03" "登录接口响应头检测" "$headers"

echo ""
echo "3.2 点击劫持测试HTML (已保存为clickjacking_test.html，点击文件在浏览器中测试)"

# ============================================================
# 测试结果汇总
# ============================================================
print_title "测试结果汇总"

echo ""
echo -e "测试总数: ${BLUE}$TOTAL_COUNT${NC}"
echo -e "通过数量: ${GREEN}$PASS_COUNT${NC}"
echo -e "失败数量: ${RED}$FAIL_COUNT${NC}"
echo ""

if [ $FAIL_COUNT -eq 0 ]; then
    echo -e "${GREEN}============================================================${NC}"
    echo -e "${GREEN}测试结论: 通过${NC}"
    echo -e "${GREEN}系统成功拦截了所有恶意参数注入攻击${NC}"
    echo -e "${GREEN}============================================================${NC}"
else
    echo -e "${RED}============================================================${NC}"
    echo -e "${RED}测试结论: 存在风险${NC}"
    echo -e "${RED}发现 $FAIL_COUNT 个潜在安全问题，请进一步分析${NC}"
    echo -e "${RED}============================================================${NC}"
fi

echo ""
echo "测试完成时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""
