# 开发与维护指南

本页面向仓库维护者：仓库结构、`check.sh` 的用法与规则、怎么跑单测、新增工具 / 配方时的检查清单、清单目录 `.codex-plugin`、版本号与提交规范。

结论先行：**提交前在仓库根目录跑一遍 `./check.sh`；改了 `browser_use` 的浏览器连接代码，必须把同样的改动复制到 `social/src/utils/`，否则一致性检查会失败。**

## 1. 仓库结构

```text
polaris-plugins-official/
├── CLAUDE.md, README.md, README_zh.md, LICENSE
├── check.sh                       # 全量检测脚本（见第 2 节）
├── scripts/ext_id.py              # 由签名私钥（默认 ~/.config/polaris-plugins/browser/extension-signing-key.pem）计算扩展公钥与扩展 ID
├── .agents/plugins/marketplace.json   # Codex 市场索引
├── .github/workflows/release.yml  # 推送 v* tag 时生成 GitHub Release
├── docs/                          # 本目录
└── plugins/
    ├── browser_use/               # v2.1.0  polaris-browser-use
    │   ├── .codex-plugin/plugin.json, .mcp.json, pyproject.toml, uv.lock
    │   ├── skills/browser_use/SKILL.md
    │   ├── src/                   # main, tools_browser, browser_hub, bridge_relay, bridge_const, cfg, extract, snapshot_js
    │   └── tests/                 # test_browser_hub, test_bridge_relay, test_extract
    ├── browser_bridge/            # v1.0.0  polaris-browser-bridge（扩展唯一源码 + 一键设置 + Native Messaging 自动配对）
    │   ├── extension/             # Polaris Browser Bridge（MV3：manifest.json, sw.js, options.html/js）
    │   ├── src/                   # main, setup_ops, native_host, paths, bridge_const, ui/setup.html（MCP Apps 卡片）
    │   └── tests/                 # test_native_host, test_setup_ops, test_main
    ├── social/                    # v3.0.0  polaris-social
    │   ├── recipes/               # zhihu, x, weibo, xiaohongshu, _example（TOML）
    │   ├── scripts/live_smoke.py  # 真机冒烟（手工，不进 CI）
    │   ├── skills/social/         # SKILL.md + 各平台 *_skill.md；skills/templates/ 内容模板
    │   ├── src/                   # main, gate, ratelimit, tools_social, tools_harvest, scheduler, content_manager
    │   │   ├── harvest/           # recipe, loader, engine, normalize
    │   │   ├── adapters/          # 10 个平台的写适配器
    │   │   └── utils/             # browser_hub, bridge_relay, bridge_const, cfg, extract, snapshot_js 等（browser_use 的副本）
    │   └── tests/                 # gate, ratelimit, harvest, site_recipes, tools_social, legacy_reads + fixtures/
    ├── knowledge_base/            # v2.0.0  polaris-knowledge-base
    │   ├── src/                   # main（工具）, vault（核心，纯标准库）
    │   └── tests/                 # test_tools, test_vault
    ├── computer_use/              # v1.5.0  不在本组文档范围
    └── system_info/               # v1.0.0  不在本组文档范围
```

每个插件都有：`.codex-plugin/plugin.json`（清单）、`.mcp.json`（MCP 服务器启动配置）、`pyproject.toml` + `uv.lock`、`skills/<插件名>/SKILL.md`、`src/main.py`。全部要求 Python ≥ 3.14。

## 2. `check.sh`

```bash
./check.sh                    # 检测 plugins/* 下所有含 pyproject.toml 的插件
./check.sh -p plugins/social  # 只检测一个插件（会跳过跨插件一致性检查）
./check.sh -x                 # 自动修复（仅 ruff lint / format）
./check.sh -s -t -T -r        # 分别跳过 pip-audit / mypy / pytest / radon
./check.sh -f                 # 有失败项也以退出码 0 结束
```

| 参数 | 含义 |
|------|------|
| `-p <目录>` | 只检测指定插件目录 |
| `-x` | 自动修复（ruff lint + format）；依赖漏洞等需自己改 `pyproject.toml` / `uv.lock` |
| `-s` / `-t` / `-T` / `-r` | 跳过 pip-audit / mypy / pytest / radon |
| `-f` | 失败时仍返回 0 |
| `-h` | 帮助 |

### 检测矩阵（插件 × 步骤）

| 步骤 | 工具与规则 |
|------|-----------|
| Ruff | `ruff check`，输出 concise |
| Format | `ruff format --check` |
| Bandit | `-ll`（仅 Medium / High），排除 `.venv` 与 `tests` |
| Audit | `uv export`（`--frozen --no-hashes --no-dev`）后 `pip-audit --no-deps --disable-pip --strict`；无 `uv.lock` 则跳过；网络失败会提示可加 `-s` |
| Mypy | 在插件自己的依赖环境里对 `src/` 运行，`--ignore-missing-imports --explicit-package-bases` |
| Test | 在插件自己的环境里 `pytest -q <插件>/tests`；无 `tests/` 则跳过 |
| Radon | 圈复杂度，只报告 D 级及以上（复杂度 ≥ 21） |
| 跨插件一致性 | 共享模块副本的 SHA-256 对比（见下） |

### 固定版本的工具

所有工具都通过 `uvx <工具>@<版本>` 运行，不依赖 PATH，保证可复现。升级时只改脚本顶部这几个变量：

| 变量 | 版本 |
|------|------|
| `RUFF_VERSION` | 0.17.0 |
| `BANDIT_VERSION` | 1.9.4 |
| `RADON_VERSION` | 6.0.1 |
| `PIP_AUDIT_VERSION` | 2.10.1 |
| `MYPY_VERSION` | 2.4.0 |
| `PYTEST_VERSION` | 9.1.1 |

脚本不会改写仓库里的 `uv.lock`（有锁文件时 `--frozen`；没有锁文件时用完即删）。

### 共享文件的 SHA-256 一致性

脚本对 `plugins/` 下以下**六个**文件名逐一收集所有副本并比对 SHA-256，副本少于 2 份则跳过：

| 文件 | 副本位置 |
|------|----------|
| `browser_hub.py` | `plugins/browser_use/src/`、`plugins/social/src/utils/` |
| `bridge_relay.py` | 同上 |
| `bridge_const.py` | 同上 |
| `cfg.py` | 同上 |
| `extract.py` | 同上 |
| `snapshot_js.py` | 同上 |

规则：`browser_use` 是源头，`social/src/utils/` 里的是逐字节副本，**两边必须一致**。改完 `browser_use/src/` 里的文件后：

```bash
cd plugins
for f in browser_hub.py bridge_relay.py bridge_const.py cfg.py extract.py snapshot_js.py; do
  cp browser_use/src/$f social/src/utils/$f
done
cd .. && ./check.sh        # 末尾“跨插件一致性”应全部 ✔
```

这些文件使用 `from .cfg import ...` 之类的相对导入，所以在两个包里都能原样工作。注意：`-p` 单插件模式会跳过这项检查，提交前务必跑一次不带 `-p` 的完整检测。

## 3. 跑单元测试

测试全部离线（用夹具和临时目录），不需要 Chrome。

```bash
cd plugins/social            && uv run pytest -q                 # 全部
cd plugins/social            && uv run pytest tests/test_gate.py -q   # 单个文件
cd plugins/browser_use       && uv run pytest -q
cd plugins/knowledge_base    && uv run --with pytest pytest -q
./check.sh -p plugins/social -s -t -r    # 用与 CI 相同的固定版本只跑 lint + 测试，跳过联网审计
```

各插件的 `pyproject.toml` 已配置 `pythonpath = ["."]`（测试里用 `from src... import ...`），`social` 与 `browser_use` 另有 `asyncio_mode = "auto"`。

## 4. 检查清单

### 新增一个 MCP 工具

- [ ] 用 `@mcp.tool(annotations=ToolAnnotations(...))` 注册，**必须声明** `readOnlyHint`；读外部网站的加 `openWorldHint=True`；写类加 `destructiveHint=True`（内核判定管线免审批与否就看这个标注）。
- [ ] 参数用 Pydantic / `Annotated[..., Field(...)]` 写严格约束（范围、长度、枚举）；不要把一堆可选参数塞进一个“万能工具”。
- [ ] 返回统一结构：`{"ok": true, ...}` 或 `{"ok": false, "error": {"code", "message"}}`，错误码复用现有的，新增的写进对应文档。
- [ ] 涉及 shell / AppleScript / JS 拼接的参数，先 `json.dumps()` 转义，禁止裸 f-string 插值（CLAUDE.md 要求）；`browser_use` 的 JS 一律是常量函数体 + `page.evaluate(JS, arg)`。
- [ ] 读写外部站点的工具要接入限速（读：`tools_social` 里 `acquire`；写：`@rate_limited_write`，函数必须有名为 `platform` 的参数）。
- [ ] 运行期配置写到 `~/.config/polaris-plugins/...`，不要写进 `src/`。
- [ ] 补单测（离线）；更新插件 `README.md`、`SKILL.md` 和 `docs/` 对应页面；`./check.sh` 全绿。

### 新增 / 修改站点配方

- [ ] 按 [recipes.md](recipes.md) 第 6 节的步骤：配方文件、`ReadPlatform`、`DOMAIN_PLATFORMS`、夹具与断言。
- [ ] 默认 `status = "beta"`；`min_interval_s >= 4.0`；有 `block_signals`；每个动作有至少 3 个字段的 `extract_fallback`。
- [ ] **不要**设计“LLM 自动改配方并生效”的流程。

### 修改浏览器连接代码

- [ ] 改 `browser_use/src/` 里的源头文件 → 复制到 `social/src/utils/` → 跑完整 `./check.sh`。
- [ ] 保持隔离不变量：只操作自建窗口 / 标签、按 marker URL 定位、不读 cookie、不自动登录。
- [ ] 改了扩展（`browser_bridge/extension/`）或常量里的端口 / ID 时，同步 [browser-use.md](browser-use.md) 与 README。

## 5. 清单目录 `.codex-plugin`

每个插件的清单是 `.codex-plugin/plugin.json`（旧的 `.polaris-plugin/` 已在提交 `3fb4c30` 迁移走，内核不再读取，见 [migration.md](migration.md)）。内核按 ADR-0103 读取 `.codex-plugin/`、`.claude-plugin/` 或根目录 `plugin.json`。

主要字段（以现有清单为准）：`name`、`version`、`description`、`author`、`homepage`、`repository`、`license`（`AGPL-3.0`）、`keywords`、`mcpServers`（`"./.mcp.json"`）、`skills`（`"./skills/"`）、`interface`（`displayName`、`shortDescription`、`longDescription`、`category`、`capabilities`、`defaultPrompt` 等）。

| 插件 | 清单 `name` | `.mcp.json` 里的服务器名 |
|------|------------|--------------------------|
| browser_use | `polaris-browser-use` | `polaris-browser-use` |
| social | `polaris-social` | `polaris-social` |
| knowledge_base | `polaris-knowledge-base` | `polaris-knowledge-base` |

`.agents/plugins/marketplace.json` 是 Codex 市场索引（`git-subdir` 指向各插件目录）。新增插件要同时登记在这里。

## 6. 版本号

仓库没有成文的版本规范；现状与建议如下。

- **现状**：同一个版本号出现在多处，需要手工保持一致：`.codex-plugin/plugin.json` 的 `version`、`pyproject.toml` 的 `version`、插件 `README.md` 标题、`SKILL.md` 的 `version`、`src/main.py` 文档字符串。当前为 `browser_use` 2.1.0、`social` 3.0.0、`knowledge_base` 2.0.0。
- **建议**：按语义化版本——不兼容的工具改名 / 删除 / 参数语义变更升主版本（如 `social_poster` → `social` 的工具前缀变化，见 [migration.md](migration.md)），新增工具升次版本，修复升修订版本。
- **发布**：推送 `v*` 格式的 tag 触发 `.github/workflows/release.yml`，自动生成 Release Notes。仓库的 tag（`v1.0.0` … `v1.5.0`）是整仓库级别的，不是单个插件的。

## 7. 提交与署名

- **CLAUDE.md 没有规定提交署名（trailer）规则。** 现有历史里的提交作者是 MrLaoLiAI，没有 `Co-Authored-By` 之类的行。若由 AI 助手代为提交，请按所用工具/平台的要求添加署名行，并由维护者确认后再推送。
- **提交信息风格（从历史归纳）**：Conventional Commits，`类型(范围): 中文摘要`，必要时空一行后用列表写要点。类型见过 `feat`、`fix`、`refactor`、`docs`、`chore`。例如 `feat(social): 新增 social_* 读工具与读写共享限速`。
- 把一次逻辑改动拆成一个提交；涉及根 README / CLAUDE.md 的同步更新放在同一个提交里。
- 提交前：`./check.sh` 全绿（含完整的跨插件一致性检查）。

## 8. 维护这些文档

- 文档里出现的工具名、环境变量、路径、错误码都必须能在源码里找到；改了源码就同步改文档。
- 自检：核对所有相对链接的目标存在；对文档中出现的 `social_*` / `browser_*` / `kb_*` 等工具名，在 `plugins/*/src` 里 `grep`。
- 内核侧概念（管线 DSL、阈值、`vault_dirs`）以 Polaris 仓库为准；本目录只引用，不复制其实现细节。
