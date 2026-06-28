#!/usr/bin/env bash
# =============================================================================
# check.sh — Python 项目全量检测脚本
# 用法：./check.sh [选项]
#   -p <path>   指定项目路径（默认：当前目录 .）
#   -x          自动修复模式（ruff 自动修复 lint + 格式；safety 自动升级漏洞包）
#   -s          跳过 safety 依赖漏洞扫描（网络慢时使用）
#   -t          跳过 mypy 类型检查
#   -r          跳过 radon 复杂度检测
#   -f          发现问题时强制继续（默认遇严重错误会提示）
#   -h          显示帮助
# =============================================================================

set -euo pipefail

# ── 颜色 ──────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

# ── 默认参数 ──────────────────────────────────────────────────────────────────
TARGET="."
AUTOFIX=false
SKIP_SAFETY=false
SKIP_MYPY=false
SKIP_RADON=false
FORCE=false

# 记录自动修复的内容
FIXED=()

# ── 统计 ──────────────────────────────────────────────────────────────────────
PASS=0
FAIL=0
SKIP=0
WARNINGS=()

# ── 解析参数 ──────────────────────────────────────────────────────────────────
usage() {
  echo "用法: $0 [-p <path>] [-x] [-s] [-t] [-r] [-f] [-h]"
  echo "  -p  指定检测目录（默认：.）"
  echo "  -x  自动修复模式（ruff lint/格式修复 + safety 漏洞包升级）"
  echo "  -s  跳过 safety 依赖扫描"
  echo "  -t  跳过 mypy 类型检查"
  echo "  -r  跳过 radon 复杂度检测"
  echo "  -f  强制继续，不中断"
  echo "  -h  显示帮助"
  exit 0
}

while getopts "p:xstrfh" opt; do
  case $opt in
    p) TARGET="$OPTARG" ;;
    x) AUTOFIX=true ;;
    s) SKIP_SAFETY=true ;;
    t) SKIP_MYPY=true ;;
    r) SKIP_RADON=true ;;
    f) FORCE=true ;;
    h) usage ;;
    *) usage ;;
  esac
done

# ── 工具函数 ──────────────────────────────────────────────────────────────────
print_header() {
  echo ""
  echo -e "${BOLD}${BLUE}══════════════════════════════════════════${RESET}"
  echo -e "${BOLD}${BLUE}  $1${RESET}"
  echo -e "${BOLD}${BLUE}══════════════════════════════════════════${RESET}"
}

print_step() {
  echo ""
  echo -e "${CYAN}▶ $1${RESET}"
}

pass() {
  echo -e "${GREEN}✔ $1${RESET}"
  PASS=$((PASS + 1))
}

fail() {
  echo -e "${RED}✘ $1${RESET}"
  FAIL=$((FAIL + 1))
  WARNINGS+=("$1")
}

skipped() {
  echo -e "${YELLOW}⊘ 跳过: $1${RESET}"
  SKIP=$((SKIP + 1))
}

require_tool() {
  local tool="$1"
  local install_hint="$2"
  if ! command -v "$tool" &>/dev/null; then
    echo -e "${YELLOW}⚠ 未找到 ${tool}，正在安装...${RESET}"
    pip install "$install_hint" -q --break-system-packages 2>/dev/null \
      || pip install "$install_hint" -q 2>/dev/null \
      || { echo -e "${RED}安装 ${tool} 失败，请手动运行: pip install ${install_hint}${RESET}"; return 1; }
  fi
}

# ── 开始 ──────────────────────────────────────────────────────────────────────
print_header "Python 项目检测 — $(date '+%Y-%m-%d %H:%M:%S')"
echo -e "  检测目录: ${BOLD}${TARGET}${RESET}"
if $AUTOFIX; then
  echo -e "  模式: ${YELLOW}${BOLD}自动修复已开启 (-x)${RESET}"
fi
echo ""

# ── 1. Ruff — Lint + 格式检查 ─────────────────────────────────────────────────
print_step "1/5  Ruff — 代码规范 & 潜在错误"
require_tool ruff ruff

if $AUTOFIX; then
  # 先自动修复可修复的 lint 问题
  RUFF_FIX_OUT=$(ruff check "$TARGET" --fix --output-format=concise 2>&1 || true)
  FIXED_COUNT=$(echo "$RUFF_FIX_OUT" | grep -oE 'Fixed [0-9]+' | grep -oE '[0-9]+' || echo "0")
  if [ "${FIXED_COUNT:-0}" -gt 0 ]; then
    echo -e "${GREEN}  ✔ 自动修复了 ${FIXED_COUNT} 个 lint 问题${RESET}"
    FIXED+=("Ruff 自动修复了 ${FIXED_COUNT} 个 lint 问题")
  fi
  # 再次检查是否还有残余（unsafe 类问题无法自动修复）
  if ruff check "$TARGET" --output-format=concise 2>&1; then
    pass "Ruff lint 全部通过"
  else
    echo -e "${YELLOW}  提示：剩余问题需手动处理（如 unsafe 修复、逻辑错误）${RESET}"
    fail "Ruff 仍有无法自动修复的问题"
  fi
else
  if ruff check "$TARGET" --output-format=concise 2>&1; then
    pass "Ruff 未发现问题"
  else
    echo -e "${YELLOW}  提示：运行 './check.sh -x' 可自动修复部分问题${RESET}"
    fail "Ruff 发现代码规范问题"
  fi
fi

# 格式检查
print_step "     Ruff format — 格式一致性"
if $AUTOFIX; then
  ruff format "$TARGET" --quiet 2>&1 || true
  FIXED+=("Ruff format 已统一代码格式")
  pass "代码格式已自动统一"
else
  if ruff format "$TARGET" --check --quiet 2>&1; then
    pass "代码格式一致"
  else
    echo -e "${YELLOW}  提示：运行 './check.sh -x' 可自动修复格式${RESET}"
    fail "存在格式不一致（不影响运行，建议修复）"
  fi
fi

# ── 2. Bandit — 安全漏洞 ──────────────────────────────────────────────────────
print_step "2/5  Bandit — 安全漏洞扫描"
require_tool bandit bandit
# -ll: 只报告 medium/high; -q: 精简输出; 忽略测试目录
# 动态收集所有 .venv 路径，避免扫描第三方库产生大量误报
VENV_PATHS=$(find "$TARGET" -maxdepth 4 -type d \( -name ".venv" -o -name "venv" \) 2>/dev/null | tr '\n' ',' | sed 's/,$//')
BANDIT_EXCLUDE="${VENV_PATHS:+$VENV_PATHS,}tests,test,env,.env"
if bandit -r "$TARGET" -ll -q \
    --exclude "$BANDIT_EXCLUDE" 2>&1; then
  pass "Bandit 未发现安全漏洞"
else
  # 安全漏洞不能自动修复，需人工审查
  echo -e "${YELLOW}  ⚠ 安全漏洞需要人工审查，无法自动修复${RESET}"
  echo -e "${YELLOW}  提示：查看上方报告，重点关注 CWE 编号和漏洞位置${RESET}"
  fail "Bandit 发现安全漏洞（Medium/High 级别）—— 需人工修复"
fi

# ── 3. Safety — 依赖 CVE 扫描 ────────────────────────────────────────────────
print_step "3/5  Safety — 依赖库 CVE 漏洞"
if $SKIP_SAFETY; then
  skipped "Safety（已通过 -s 跳过）"
else
  require_tool safety safety
  # 优先扫描 requirements 文件，否则扫描当前环境
  REQS=$(find "$TARGET" -maxdepth 2 \
    \( -name "requirements*.txt" -o -name "requirements/*.txt" \) 2>/dev/null | head -1)

  run_safety_check() {
    local reqs_arg="$1"   # "" 表示扫当前环境，否则是 "-r <file>"
    local label="$2"
    local safety_out
    # shellcheck disable=SC2086
    safety_out=$(safety check $reqs_arg --short-report 2>&1 || true)

    if echo "$safety_out" | grep -qiE "No known security vulnerabilities"; then
      echo "$safety_out"
      pass "Safety 未发现依赖漏洞 ${label}"
    else
      echo "$safety_out"
      if $AUTOFIX; then
        # 提取有漏洞的包名（格式：-> package_name ）
        VULN_PKGS=$(echo "$safety_out" \
          | grep -oE -- '-> [a-zA-Z0-9_-]+' \
          | awk '{print $2}' \
          | sort -u \
          | tr '\n' ' ' || true)
        if [ -n "$VULN_PKGS" ]; then
          echo -e "${YELLOW}  ▶ 正在升级存在漏洞的包: ${VULN_PKGS}${RESET}"
          # shellcheck disable=SC2086
          if pip install --upgrade $VULN_PKGS -q 2>&1; then
            echo -e "${GREEN}  ✔ 已升级: ${VULN_PKGS}${RESET}"
            FIXED+=("Safety 自动升级了漏洞包: ${VULN_PKGS}")
            # 升级后如有 requirements.txt 则同步更新版本号
            if [ -n "$REQS" ]; then
              echo -e "${YELLOW}  提示：如需同步 ${REQS}，请运行: pip freeze > ${REQS}${RESET}"
            fi
            pass "Safety 漏洞包已自动升级"
          else
            echo -e "${RED}  升级失败，请手动运行: pip install --upgrade ${VULN_PKGS}${RESET}"
            fail "Safety 发现 CVE 漏洞，自动升级失败 ${label}"
          fi
        else
          echo -e "${YELLOW}  ⚠ 无法解析包名，请手动处理上方漏洞${RESET}"
          fail "Safety 发现 CVE 漏洞，需手动处理 ${label}"
        fi
      else
        echo -e "${YELLOW}  提示：运行 './check.sh -x' 可自动升级漏洞包${RESET}"
        fail "Safety 发现依赖库 CVE 漏洞，请升级相关包 ${label}"
      fi
    fi
  }

  if [ -n "$REQS" ]; then
    run_safety_check "-r ${REQS}" "(${REQS})"
  else
    run_safety_check "" "（当前环境）"
  fi
fi

# ── 4. Mypy — 类型检查 ────────────────────────────────────────────────────────
print_step "4/5  Mypy — 类型检查"
if $SKIP_MYPY; then
  skipped "Mypy（已通过 -t 跳过）"
else
  require_tool mypy mypy
  MYPY_FAIL=0
  # 每个插件是独立的包，必须在各自目录内单独扫描，
  # 否则多个 src/main.py 会产生 "Duplicate module named 'main'" 错误。
  PLUGIN_DIRS=$(find "$TARGET" -maxdepth 2 -name "pyproject.toml" \
    ! -path "*/.venv/*" 2>/dev/null \
    | xargs -I{} dirname {} \
    | sort)

  if [ -z "$PLUGIN_DIRS" ]; then
    # 根目录本身就是一个包，直接扫描
    if mypy "$TARGET" \
        --ignore-missing-imports \
        --explicit-package-bases \
        --no-error-summary \
        --pretty 2>&1; then
      pass "Mypy 类型检查通过"
    else
      MYPY_FAIL=1
    fi
  else
    while IFS= read -r plugin_dir; do
      src_dir="${plugin_dir}/src"
      scan_dir="${src_dir:-$plugin_dir}"
      [ -d "$scan_dir" ] || scan_dir="$plugin_dir"
      echo -e "${CYAN}   扫描: ${scan_dir}${RESET}"
      if ! mypy "$scan_dir" \
          --ignore-missing-imports \
          --explicit-package-bases \
          --disable-error-code annotation-unchecked \
          --no-error-summary \
          --pretty 2>&1; then
        MYPY_FAIL=1
      fi
    done <<< "$PLUGIN_DIRS"
  fi

  if [ "$MYPY_FAIL" -eq 0 ]; then
    pass "Mypy 类型检查通过"
  else
    fail "Mypy 发现类型错误"
  fi

fi

# ── 5. Radon — 复杂度 ─────────────────────────────────────────────────────────
print_step "5/5  Radon — 圈复杂度"
if $SKIP_RADON; then
  skipped "Radon（已通过 -r 跳过）"
else
  require_tool radon radon
  # 只显示 D 级（复杂度 ≥ 10）及以上的函数，这些是高风险区域
  RADON_OUT=$(radon cc "$TARGET" -s -n D 2>/dev/null || true)
  if [ -z "$RADON_OUT" ]; then
    pass "所有函数复杂度在可接受范围内（< 10）"
  else
    echo -e "${YELLOW}${RADON_OUT}${RESET}"
    fail "发现高复杂度函数（复杂度 ≥ 10），建议重构"
  fi
fi

# ── 汇总报告 ──────────────────────────────────────────────────────────────────
print_header "检测结果汇总"
echo -e "  ${GREEN}✔ 通过: ${PASS}${RESET}   ${RED}✘ 失败: ${FAIL}${RESET}   ${YELLOW}⊘ 跳过: ${SKIP}${RESET}"
echo ""

# 显示自动修复内容
if [ ${#FIXED[@]} -gt 0 ]; then
  echo -e "${GREEN}${BOLD}自动修复内容：${RESET}"
  for f in "${FIXED[@]}"; do
    echo -e "  ${GREEN}✔${RESET} $f"
  done
  echo ""
fi

# 显示仍需人工处理的问题
if [ ${#WARNINGS[@]} -gt 0 ]; then
  echo -e "${RED}${BOLD}仍需人工处理的问题：${RESET}"
  for w in "${WARNINGS[@]}"; do
    echo -e "  ${RED}•${RESET} $w"
  done
  echo ""
fi

if [ "$FAIL" -eq 0 ]; then
  echo -e "${GREEN}${BOLD}🎉 全部检测通过！可以安全推送到 GitHub。${RESET}"
  echo ""
  exit 0
else
  echo -e "${RED}${BOLD}⚠  存在 ${FAIL} 个问题，建议修复后再推送。${RESET}"
  if $AUTOFIX; then
    echo -e "${YELLOW}  注意：以上问题无法自动修复（安全漏洞/类型错误/复杂度），需人工处理。${RESET}"
  else
    echo -e "${YELLOW}  提示：运行 './check.sh -x' 可自动修复 lint 和格式问题。${RESET}"
  fi
  echo ""
  if ! $FORCE; then
    exit 1
  fi
fi
