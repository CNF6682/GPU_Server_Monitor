#!/bin/bash
# Proxy Integration Test Script
# 测试 Agent 代理转发功能的集成测试脚本

set -e

# 配置变量
AGENT_HOST="${AGENT_HOST:-localhost}"
AGENT_PORT="${AGENT_PORT:-9109}"
TOKEN="${TOKEN:-test-token}"
BASE_URL="http://${AGENT_HOST}:${AGENT_PORT}"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 辅助函数
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_command() {
    if ! command -v "$1" &> /dev/null; then
        log_error "Required command '$1' not found"
        exit 1
    fi
}

# 检查依赖
log_info "Checking dependencies..."
check_command curl
check_command jq

# API 调用辅助函数
api_call() {
    local method="$1"
    local endpoint="$2"
    local data="$3"

    if [ -z "$data" ]; then
        curl -s -X "$method" \
             -H "Authorization: Bearer $TOKEN" \
             "${BASE_URL}${endpoint}"
    else
        curl -s -X "$method" \
             -H "Authorization: Bearer $TOKEN" \
             -H "Content-Type: application/json" \
             -d "$data" \
             "${BASE_URL}${endpoint}"
    fi
}

# 测试计数器
TESTS_PASSED=0
TESTS_FAILED=0

# 测试函数
test_case() {
    local test_name="$1"
    echo ""
    log_info "Running test: $test_name"
}

assert_equals() {
    local expected="$1"
    local actual="$2"
    local message="$3"

    if [ "$expected" = "$actual" ]; then
        log_info "✓ $message"
        ((TESTS_PASSED++))
        return 0
    else
        log_error "✗ $message"
        log_error "  Expected: $expected"
        log_error "  Actual: $actual"
        ((TESTS_FAILED++))
        return 1
    fi
}

assert_not_null() {
    local value="$1"
    local message="$2"

    if [ -n "$value" ] && [ "$value" != "null" ]; then
        log_info "✓ $message"
        ((TESTS_PASSED++))
        return 0
    else
        log_error "✗ $message (value is null or empty)"
        ((TESTS_FAILED++))
        return 1
    fi
}

# ============================================
# 测试用例
# ============================================

echo "=========================================="
echo "  Proxy Integration Test Suite"
echo "=========================================="
echo "Agent: ${BASE_URL}"
echo ""

# Test 1: 获取代理状态
test_case "GET /v1/proxy/status"
response=$(api_call GET /v1/proxy/status)
status=$(echo "$response" | jq -r '.status')
assert_not_null "$status" "Status field should not be null"

# Test 2: 验证状态字段
test_case "Verify status response fields"
echo "$response" | jq -e '.status' > /dev/null
assert_equals "0" "$?" "Response should contain 'status' field"

echo "$response" | jq -e '.retry_count' > /dev/null
assert_equals "0" "$?" "Response should contain 'retry_count' field"

# Test 3: 停止代理（如果正在运行）
test_case "POST /v1/proxy/stop"
stop_response=$(api_call POST /v1/proxy/stop)
stop_status=$(echo "$stop_response" | jq -r '.status')
log_info "Proxy stopped, status: $stop_status"

# Test 4: 验证停止后的状态
test_case "Verify proxy is stopped"
sleep 1
status_response=$(api_call GET /v1/proxy/status)
current_status=$(echo "$status_response" | jq -r '.status')
if [ "$current_status" = "stopped" ] || [ "$current_status" = "disabled" ]; then
    log_info "✓ Proxy is stopped or disabled"
    ((TESTS_PASSED++))
else
    log_error "✗ Expected stopped/disabled, got: $current_status"
    ((TESTS_FAILED++))
fi

# Test 5: 测试启动代理（注意：需要有效配置才能成功）
test_case "POST /v1/proxy/start (may fail if config is invalid)"
start_response=$(api_call POST /v1/proxy/start)
start_status=$(echo "$start_response" | jq -r '.status')
log_info "Start response status: $start_status"

# 如果配置有效，状态应该是 connecting 或 connected
if [ "$start_status" = "connecting" ] || [ "$start_status" = "connected" ] || [ "$start_status" = "error" ]; then
    log_info "✓ Start API responded correctly"
    ((TESTS_PASSED++))
else
    log_warn "Start API returned unexpected status: $start_status (may be expected if proxy is disabled)"
fi

# Test 6: 测试自定义配置启动（可选）
test_case "POST /v1/proxy/start with custom config"
log_warn "Skipping custom config test (requires valid SSH credentials)"

# Test 7: 最终清理 - 停止代理
test_case "Cleanup: Stop proxy"
cleanup_response=$(api_call POST /v1/proxy/stop)
log_info "Cleanup completed"

# ============================================
# 测试总结
# ============================================

echo ""
echo "=========================================="
echo "  Test Summary"
echo "=========================================="
echo -e "${GREEN}Passed:${NC} $TESTS_PASSED"
echo -e "${RED}Failed:${NC} $TESTS_FAILED"
echo "=========================================="

if [ $TESTS_FAILED -eq 0 ]; then
    log_info "All tests passed!"
    exit 0
else
    log_error "Some tests failed!"
    exit 1
fi
