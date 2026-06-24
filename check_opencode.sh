#!/usr/bin/env bash
#
# check_opencode.sh — Verify opencode setup integrity
#
# Usage:
#   ./check_opencode.sh
#
# Checks: env vars, config files, plugins, providers, Ollama, DeepSeek, opencode version, oh-my-openagent doctor
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0
FAILURES=""

check() {
  local label="$1" cmd="$2"
  if eval "$cmd" 2>/dev/null; then
    echo -e "  ${GREEN}[PASS]${NC} $label"
    PASS=$((PASS + 1))
  else
    echo -e "  ${RED}[FAIL]${NC} $label"
    FAIL=$((FAIL + 1))
    FAILURES+="  - $label"$'\n'
  fi
}

check_nz() {
  local label="$1" var_name="$2"
  if [[ -n "${!var_name}" ]]; then
    local masked="${!var_name:0:8}..."
    echo -e "  ${GREEN}[PASS]${NC} $label ($masked)"
    PASS=$((PASS + 1))
  else
    echo -e "  ${RED}[FAIL]${NC} $label (not set)"
    FAIL=$((FAIL + 1))
    FAILURES+="  - $label"$'\n'
  fi
}

echo "=============================================="
echo "  OpenCode Setup Verification"
echo "=============================================="
echo ""

echo "=== 1. 环境变量 ==="
check_nz "BAILIAN_API_KEY" BAILIAN_API_KEY
check_nz "OLLAMA_HOST" OLLAMA_HOST
echo ""

echo "=== 2. 配置文件 ==="
CONFIG_DIR="$HOME/.config/opencode"
AUTH_DIR="$HOME/.local/share/opencode"
check "opencode.jsonc 存在"    "[[ -f $CONFIG_DIR/opencode.jsonc ]]"
check "oh-my-openagent.json 存在" "[[ -f $CONFIG_DIR/oh-my-openagent.json ]]"
check "auth.json 存在"         "[[ -f $AUTH_DIR/auth.json ]]"
check "auth.json 含 deepseek"  "jq -e '.deepseek' $AUTH_DIR/auth.json >/dev/null"
check "opencode.jsonc 含 bailian-payg"  "grep -q 'bailian-payg' $CONFIG_DIR/opencode.jsonc"
check "opencode.jsonc 含 ollama"        "grep -q '\"ollama\"' $CONFIG_DIR/opencode.jsonc"
PLUGIN_COUNT=$(jq '.plugin | length' "$CONFIG_DIR/opencode.jsonc" 2>/dev/null || echo 0)
check "plugin 数量 >= 3（当前: $PLUGIN_COUNT）" "[[ $PLUGIN_COUNT -ge 3 ]]"
echo ""

echo "=== 3. Ollama（本地） ==="
OLLAMA_URL="http://192.168.160.1:11434"
check "Ollama 宿主机可达" "curl -sfo /dev/null $OLLAMA_URL/api/tags"
check "qwen3.5_9B_Q4 存在" \
  "curl -s $OLLAMA_URL/api/tags | jq -e '.models[] | select(.name | startswith(\"qwen3.5_9B\"))' >/dev/null"
check "qwen2.5:3b 存在" \
  "curl -s $OLLAMA_URL/api/tags | jq -e '.models[] | select(.name | startswith(\"qwen2.5:3b\"))' >/dev/null"
check "nomic-embed-text 存在" \
  "curl -s $OLLAMA_URL/api/tags | jq -e '.models[] | select(.name | startswith(\"nomic-embed\"))' >/dev/null"
echo ""

echo "=== 4. OpenCode 本体 ==="
check "opencode 可执行"  "command -v opencode &>/dev/null"
check "opencode 版本号"  'opencode --version 2>/dev/null | grep -qE "[0-9]+\.[0-9]+"'
echo ""

echo "=== 5. oh-my-openagent 诊断 ==="
echo "  (运行 bun x oh-my-openagent doctor...)"
echo ""
BUN_PATH="/usr/local/bin/bun"
if [[ -x "$BUN_PATH" ]]; then
  "$BUN_PATH" x oh-my-openagent doctor 2>&1 || true
else
  echo "  [WARN] bun 不在 /usr/local/bin/bun，跳过 doctor"
fi
echo ""

echo "=== 6. Provider 连通性 ==="
check "DeepSeek 模型可发现"  'opencode models 2>/dev/null | grep -qi "deepseek"'
check "bailian/qwen3.7-max 可发现" 'opencode models 2>/dev/null | grep -qi "qwen3.7"'
check "ollama 模型可发现"    'opencode models 2>/dev/null | grep -qi "ollama"'
echo ""

echo "=============================================="
if [[ $FAIL -eq 0 ]]; then
  echo -e "  ${GREEN}全部通过！${NC}  $PASS/$((PASS+FAIL))"
else
  echo -e "  ${RED}$FAIL 项失败：${NC}"
  echo "$FAILURES"
fi
echo "=============================================="

exit $FAIL
