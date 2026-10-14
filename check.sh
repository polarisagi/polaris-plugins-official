#!/usr/bin/env bash
# =============================================================================
# check.sh — polaris 官方插件仓库全量检测脚本
#
# 对 plugins/*/pyproject.toml 对应的每个插件分别执行：
#   Ruff lint / Ruff format / Bandit / pip-audit / Mypy / Pytest / Radon
# 最后输出「插件 × 步骤」汇总表，并做跨插件共享模块一致性检查。
#
# 所有工具一律通过 `uvx <tool>@<固定版本>` 运行（不依赖 PATH 上的同名工具，
# 保证结果可复现）；Mypy / Pytest 通过 `uv run --project <插件>` 在插件自身
# 依赖环境里运行。需要先安装 uv：https://docs.astral.sh/uv/
# =============================================================================

set -uo pipefail   # 故意不加 -e：单个工具失败只记为该步骤 fail，不中断整体

# ── 固定的工具版本（升级时统一改这里）────────────────────────────────────────
RUFF_VERSION="0.17.0"
BANDIT_VERSION="1.9.4"
RADON_VERSION="6.0.1"
PIP_AUDIT_VERSION="2.10.1"
MYPY_VERSION="2.4.0"
PYTEST_VERSION="9.1.1"

# ── 路径：无论从哪里调用都以脚本所在目录为基准 ───────────────────────────────
ORIG_PWD="$PWD"
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
cd "$SCRIPT_DIR" || exit 1

# ── 颜色 ──────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

# ── 默认参数 ──────────────────────────────────────────────────────────────────
TARGET=""
AUTOFIX=false
SKIP_AUDIT=false
SKIP_MYPY=false
SKIP_RADON=false
SKIP_TESTS=false
FORCE=false

FIXED=()        # 自动修复记录
WARNINGS=()     # 失败项（插件/步骤）
RESULTS=()      # "插件|步骤|状态"
PASS=0
FAIL=0
SKIP=0

STEPS=("ruff" "format" "bandit" "audit" "mypy" "test" "radon")
STEP_LABELS=("Ruff" "Format" "Bandit" "Audit" "Mypy" "Test" "Radon")

TMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/polaris-check.XXXXXX")
trap 'rm -rf "$TMP_DIR"' EXIT

# ── 参数 ──────────────────────────────────────────────────────────────────────
usage() {
  echo "用法: $0 [-p <插件目录>] [-x] [-s] [-t] [-T] [-r] [-f] [-h]"
  echo "  -p  只检测指定插件目录（如 plugins/browser_use；默认：自动发现 plugins/*）"
  echo "  -x  自动修复模式（仅 ruff lint/格式；依赖漏洞需自行改 pyproject.toml/uv.lock）"
  echo "  -s  跳过 pip-audit 依赖漏洞扫描（网络受限/较慢时使用）"
  echo "  -t  跳过 mypy 类型检查"
  echo "  -T  跳过 pytest 测试"
  echo "  -r  跳过 radon 复杂度检测"
  echo "  -f  存在失败时也以退出码 0 结束"
  echo "  -h  显示帮助"
  echo ""
  echo "工具均通过 uvx 固定版本运行: ruff ${RUFF_VERSION}, bandit ${BANDIT_VERSION},"
  echo "  radon ${RADON_VERSION}, pip-audit ${PIP_AUDIT_VERSION}, mypy ${MYPY_VERSION}, pytest ${PYTEST_VERSION}"
  exit 0
}

while getopts "p:xstTrfh" opt; do
  case $opt in
    p) TARGET="$OPTARG" ;;
    x) AUTOFIX=true ;;
    s) SKIP_AUDIT=true ;;
    t) SKIP_MYPY=true ;;
    T) SKIP_TESTS=true ;;
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

# record <插件> <步骤> <PASS|FAIL|SKIP> [说明]
record() {
  local plugin="$1" step="$2" status="$3" note="${4:-}"
  RESULTS+=("${plugin}|${step}|${status}")
  case "$status" in
    PASS) echo -e "  ${GREEN}✔ ${plugin}${RESET} ${note}"; PASS=$((PASS + 1)) ;;
    FAIL) echo -e "  ${RED}✘ ${plugin}${RESET} ${note}"; FAIL=$((FAIL + 1))
          WARNINGS+=("${plugin} / ${step}${note:+ — ${note}}") ;;
    SKIP) echo -e "  ${YELLOW}⊘ ${plugin}${RESET} ${note}"; SKIP=$((SKIP + 1)) ;;
  esac
}

# lookup <插件> <步骤> → 状态
lookup() {
  local r
  for r in ${RESULTS[@]+"${RESULTS[@]}"}; do
    if [ "${r%|*}" = "$1|$2" ]; then
      echo "${r##*|}"
      return
    fi
  done
  echo "-"
}

# 缩进输出文件内容
show_output() {
  sed 's/^/    /' "$1"
}

plugin_name() {
  basename "$1"
}

# 在插件依赖环境中运行命令；绝不改写仓库里的 uv.lock：
#   有 uv.lock → --frozen 直接按锁文件装（锁文件过期也不会被改写）
#   无 uv.lock → 运行后删除 uv 临时生成的锁文件
# 用法: uv_run <插件目录> <with 依赖> <命令...>
uv_run() {
  local dir="$1" with="$2" rc
  shift 2
  if [ -f "$dir/uv.lock" ]; then
    uv run --frozen --project "$dir" --quiet --with "$with" "$@"
    return $?
  fi
  uv run --project "$dir" --quiet --with "$with" "$@"
  rc=$?
  rm -f "$dir/uv.lock"
  return $rc
}

# ── 前置：uv ─────────────────────────────────────────────────────────────────
if ! command -v uv &>/dev/null || ! command -v uvx &>/dev/null; then
  echo -e "${RED}✘ 未找到 uv / uvx。本脚本依赖 uv 运行所有检测工具。${RESET}"
  echo "  安装: curl -LsSf https://astral.sh/uv/install.sh | sh"
  echo "  或:   brew install uv"
  exit 1
fi

# ── 发现插件 ─────────────────────────────────────────────────────────────────
PLUGIN_DIRS=()
if [ -n "$TARGET" ]; then
  if [ -d "$ORIG_PWD/$TARGET" ]; then
    TARGET_ABS=$(cd "$ORIG_PWD/$TARGET" && pwd)
  elif [ -d "$SCRIPT_DIR/$TARGET" ]; then
    TARGET_ABS=$(cd "$SCRIPT_DIR/$TARGET" && pwd)
  elif [ -d "$TARGET" ]; then
    TARGET_ABS=$(cd "$TARGET" && pwd)
  else
    echo -e "${RED}✘ -p 指定的目录不存在: ${TARGET}${RESET}"
    exit 1
  fi
  if [ -f "$TARGET_ABS/pyproject.toml" ]; then
    PLUGIN_DIRS+=("$TARGET_ABS")
  else
    while IFS= read -r f; do
      [ -n "$f" ] && PLUGIN_DIRS+=("$(dirname "$f")")
    done < <(find "$TARGET_ABS" -maxdepth 3 -name pyproject.toml ! -path "*/.venv/*" | sort)
  fi
else
  while IFS= read -r f; do
    [ -n "$f" ] && PLUGIN_DIRS+=("$(dirname "$f")")
  done < <(find "$SCRIPT_DIR/plugins" -maxdepth 2 -name pyproject.toml ! -path "*/.venv/*" | sort)
fi

if [ "${#PLUGIN_DIRS[@]}" -eq 0 ]; then
  echo -e "${RED}✘ 未发现任何含 pyproject.toml 的插件${RESET}"
  exit 1
fi

# ── 开始 ──────────────────────────────────────────────────────────────────────
print_header "polaris 插件检测 — $(date '+%Y-%m-%d %H:%M:%S')"
echo -e "  仓库目录: ${BOLD}${SCRIPT_DIR}${RESET}"
echo -e "  插件 (${#PLUGIN_DIRS[@]}): ${BOLD}$(for d in "${PLUGIN_DIRS[@]}"; do plugin_name "$d"; done | tr '\n' ' ')${RESET}"
echo -e "  工具: ruff ${RUFF_VERSION} / bandit ${BANDIT_VERSION} / pip-audit ${PIP_AUDIT_VERSION} / mypy ${MYPY_VERSION} / pytest ${PYTEST_VERSION} / radon ${RADON_VERSION}"
if $AUTOFIX; then
  echo -e "  模式: ${YELLOW}${BOLD}自动修复已开启 (-x)${RESET}"
fi

# ── 1. Ruff lint ─────────────────────────────────────────────────────────────
print_step "1/8  Ruff — 代码规范 & 潜在错误"
for d in "${PLUGIN_DIRS[@]}"; do
  name=$(plugin_name "$d")
  out="$TMP_DIR/ruff.$name.out"
  if $AUTOFIX; then
    uvx --quiet "ruff@${RUFF_VERSION}" check "$d" --fix --output-format=concise >"$out" 2>&1
    n=$(grep -oE 'Fixed [0-9]+' "$out" | grep -oE '[0-9]+' | head -1)
    if [ "${n:-0}" -gt 0 ]; then
      FIXED+=("${name}: Ruff 自动修复了 ${n} 个 lint 问题")
    fi
  fi
  if uvx --quiet "ruff@${RUFF_VERSION}" check "$d" --output-format=concise >"$out" 2>&1; then
    record "$name" ruff PASS
  else
    show_output "$out"
    record "$name" ruff FAIL "Ruff 发现问题"
  fi
done
$AUTOFIX || echo -e "${YELLOW}  提示：运行 './check.sh -x' 可自动修复部分问题${RESET}"

# ── 2. Ruff format ───────────────────────────────────────────────────────────
print_step "2/8  Ruff format — 格式一致性"
for d in "${PLUGIN_DIRS[@]}"; do
  name=$(plugin_name "$d")
  out="$TMP_DIR/fmt.$name.out"
  if $AUTOFIX; then
    uvx --quiet "ruff@${RUFF_VERSION}" format "$d" >"$out" 2>&1
    FIXED+=("${name}: Ruff format 已统一代码格式")
  fi
  if uvx --quiet "ruff@${RUFF_VERSION}" format "$d" --check >"$out" 2>&1; then
    record "$name" format PASS
  else
    show_output "$out"
    record "$name" format FAIL "存在格式不一致"
  fi
done

# ── 3. Bandit ────────────────────────────────────────────────────────────────
print_step "3/8  Bandit — 安全漏洞扫描（-ll：仅 Medium/High）"
for d in "${PLUGIN_DIRS[@]}"; do
  name=$(plugin_name "$d")
  out="$TMP_DIR/bandit.$name.out"
  if uvx --quiet "bandit@${BANDIT_VERSION}" -r "$d" -ll -q \
      --exclude "${d}/.venv,${d}/tests" >"$out" 2>&1; then
    record "$name" bandit PASS
  else
    show_output "$out"
    record "$name" bandit FAIL "Bandit 发现 Medium/High 安全问题，需人工审查"
  fi
done

# ── 4. pip-audit ─────────────────────────────────────────────────────────────
print_step "4/8  pip-audit — 依赖库 CVE 漏洞（基于各插件 uv.lock）"
if $SKIP_AUDIT; then
  for d in "${PLUGIN_DIRS[@]}"; do record "$(plugin_name "$d")" audit SKIP "已通过 -s 跳过"; done
else
  for d in "${PLUGIN_DIRS[@]}"; do
    name=$(plugin_name "$d")
    out="$TMP_DIR/audit.$name.out"
    req="$TMP_DIR/audit.$name.requirements.txt"
    if [ ! -f "$d/uv.lock" ]; then
      record "$name" audit SKIP "无 uv.lock，无法审计（请先 uv lock）"
      continue
    fi
    if ! uv export --project "$d" --frozen --no-hashes --no-dev --no-emit-project \
        -o "$req" >"$out" 2>&1; then
      show_output "$out"
      record "$name" audit FAIL "uv export 失败"
      continue
    fi
    if uvx --quiet "pip-audit@${PIP_AUDIT_VERSION}" -r "$req" --no-deps --disable-pip \
        --strict >"$out" 2>&1; then
      record "$name" audit PASS
    else
      show_output "$out"
      if grep -qiE 'connection|network|timed out|resolve|temporary failure|ssl' "$out"; then
        record "$name" audit FAIL "pip-audit 网络失败（网络受限时可加 -s 跳过）"
      else
        record "$name" audit FAIL "发现依赖漏洞：请升级 pyproject.toml / uv.lock（脚本不自动升级）"
      fi
    fi
  done
fi

# ── 5. Mypy ──────────────────────────────────────────────────────────────────
print_step "5/8  Mypy — 类型检查（在各插件自身依赖环境内运行）"
if $SKIP_MYPY; then
  for d in "${PLUGIN_DIRS[@]}"; do record "$(plugin_name "$d")" mypy SKIP "已通过 -t 跳过"; done
else
  for d in "${PLUGIN_DIRS[@]}"; do
    name=$(plugin_name "$d")
    out="$TMP_DIR/mypy.$name.out"
    if [ ! -d "$d/src" ]; then
      record "$name" mypy SKIP "无 src/ 目录"
      continue
    fi
    if uv_run "$d" "mypy==${MYPY_VERSION}" mypy "$d/src" \
        --ignore-missing-imports --explicit-package-bases \
        --disable-error-code annotation-unchecked \
        --no-error-summary --pretty >"$out" 2>&1; then
      record "$name" mypy PASS
    else
      show_output "$out"
      record "$name" mypy FAIL "Mypy 发现类型错误"
    fi
  done
fi

# ── 6. Pytest ────────────────────────────────────────────────────────────────
print_step "6/8  Pytest — 单元测试"
if $SKIP_TESTS; then
  for d in "${PLUGIN_DIRS[@]}"; do record "$(plugin_name "$d")" test SKIP "已通过 -T 跳过"; done
else
  for d in "${PLUGIN_DIRS[@]}"; do
    name=$(plugin_name "$d")
    out="$TMP_DIR/test.$name.out"
    if [ ! -d "$d/tests" ]; then
      record "$name" test SKIP "无 tests/ 目录"
      continue
    fi
    if uv_run "$d" "pytest==${PYTEST_VERSION}" pytest -q "$d/tests" >"$out" 2>&1; then
      tail -n 1 "$out" | sed 's/^/    /'
      record "$name" test PASS
    else
      show_output "$out"
      record "$name" test FAIL "测试未通过"
    fi
  done
fi

# ── 7. Radon ─────────────────────────────────────────────────────────────────
print_step "7/8  Radon — 圈复杂度（仅报告 D 级及以上，即复杂度 ≥ 21）"
if $SKIP_RADON; then
  for d in "${PLUGIN_DIRS[@]}"; do record "$(plugin_name "$d")" radon SKIP "已通过 -r 跳过"; done
else
  for d in "${PLUGIN_DIRS[@]}"; do
    name=$(plugin_name "$d")
    out="$TMP_DIR/radon.$name.out"
    if ! uvx --quiet "radon@${RADON_VERSION}" cc "$d" -s -n D -e "*/.venv/*" >"$out" 2>&1; then
      show_output "$out"
      record "$name" radon FAIL "radon 执行失败"
    elif [ -s "$out" ]; then
      show_output "$out"
      record "$name" radon FAIL "存在 D 级及以上（复杂度 ≥ 21）的函数，建议重构"
    else
      record "$name" radon PASS
    fi
  done
fi

# ── 8. 跨插件共享模块一致性 ──────────────────────────────────────────────────
print_step "8/8  跨插件一致性 — 共享模块副本 SHA-256 对比"
CONSISTENCY_ROW="(跨插件)"
if [ -n "$TARGET" ]; then
  echo -e "  ${YELLOW}⊘ 指定了 -p，跳过跨插件一致性检查${RESET}"
  SKIP=$((SKIP + 1))
  CONSISTENCY_STATUS="SKIP"
else
  CONSISTENCY_STATUS="PASS"
  for fname in browser_hub.py bridge_relay.py bridge_const.py cfg.py extract.py snapshot_js.py; do
    copies=()
    while IFS= read -r f; do
      [ -n "$f" ] && copies+=("$f")
    done < <(find "$SCRIPT_DIR/plugins" -name "$fname" ! -path "*/.venv/*" ! -path "*/node_modules/*" | sort)
    if [ "${#copies[@]}" -lt 2 ]; then
      echo -e "  ${YELLOW}⊘ ${fname}: 仅 ${#copies[@]} 份，跳过${RESET}"
      continue
    fi
    first_hash=""
    first_file=""
    ok=true
    for f in "${copies[@]}"; do
      h=$(shasum -a 256 "$f" | awk '{print $1}')
      if [ -z "$first_hash" ]; then
        first_hash="$h"; first_file="$f"
      elif [ "$h" != "$first_hash" ]; then
        ok=false
        echo -e "  ${RED}✘ ${fname}: ${f#"$SCRIPT_DIR"/} 与 ${first_file#"$SCRIPT_DIR"/} 不一致${RESET}"
      fi
    done
    if $ok; then
      echo -e "  ${GREEN}✔ ${fname}: ${#copies[@]} 份副本一致${RESET}"
    else
      CONSISTENCY_STATUS="FAIL"
      WARNINGS+=("跨插件一致性 / ${fname} 副本不一致，请同步")
    fi
  done
  case "$CONSISTENCY_STATUS" in
    PASS) PASS=$((PASS + 1)) ;;
    FAIL) FAIL=$((FAIL + 1)) ;;
  esac
fi

# ── 汇总 ─────────────────────────────────────────────────────────────────────
print_header "检测结果汇总（插件 × 步骤）"

cell() {
  case "$1" in
    PASS) printf "${GREEN}%-8s${RESET}" "pass" ;;
    FAIL) printf "${RED}%-8s${RESET}" "FAIL" ;;
    SKIP) printf "${YELLOW}%-8s${RESET}" "skip" ;;
    *)    printf "%-8s" "-" ;;
  esac
}

printf "  %-18s" "插件"
for l in "${STEP_LABELS[@]}"; do printf "%-8s" "$l"; done
echo ""
for d in "${PLUGIN_DIRS[@]}"; do
  name=$(plugin_name "$d")
  printf "  %-18s" "$name"
  for s in "${STEPS[@]}"; do cell "$(lookup "$name" "$s")"; done
  echo ""
done
printf "  %-18s" "$CONSISTENCY_ROW"
cell "$CONSISTENCY_STATUS"
echo -e "  (browser_hub / bridge_relay / bridge_const / cfg / extract / snapshot_js)"

echo ""
echo -e "  ${GREEN}✔ 通过: ${PASS}${RESET}   ${RED}✘ 失败: ${FAIL}${RESET}   ${YELLOW}⊘ 跳过: ${SKIP}${RESET}"
echo ""

if [ ${#FIXED[@]} -gt 0 ]; then
  echo -e "${GREEN}${BOLD}自动修复内容：${RESET}"
  for f in "${FIXED[@]}"; do
    echo -e "  ${GREEN}✔${RESET} $f"
  done
  echo ""
fi

if [ ${#WARNINGS[@]} -gt 0 ]; then
  echo -e "${RED}${BOLD}仍需人工处理的问题：${RESET}"
  for w in "${WARNINGS[@]}"; do
    echo -e "  ${RED}•${RESET} $w"
  done
  echo ""
fi

if [ "$FAIL" -eq 0 ]; then
  echo -e "${GREEN}${BOLD}全部检测通过，可以安全推送。${RESET}"
  echo ""
  exit 0
else
  echo -e "${RED}${BOLD}存在 ${FAIL} 个失败项，建议修复后再推送。${RESET}"
  if $AUTOFIX; then
    echo -e "${YELLOW}  注意：剩余问题（安全/类型/复杂度/依赖漏洞/测试）无法自动修复，需人工处理。${RESET}"
  else
    echo -e "${YELLOW}  提示：运行 './check.sh -x' 可自动修复 lint 和格式问题。${RESET}"
  fi
  echo ""
  if ! $FORCE; then
    exit 1
  fi
fi
