# catalog/ —— 插件目录覆盖层的人工数据（ADR-0123）

Polaris 插件页内置多家厂商的官方市场（共数千个插件 / 技能 / 连接器），上游内容是英文，且大多没有分类。
本目录维护**中文与分类的人工输入**。翻译与分类在本地完成，由编码代理逐批翻译，不调用任何付费 API，
GitHub 上也不保存任何 API Key。

| 文件 | 作用 | 谁改 |
|---|---|---|
| `taxonomy.yaml` | 四维分类词表（主题 / 部门 / 行业 / 日常生活），以及上游 category 的映射 | 人工，谨慎（ID 不可改名、不可复用） |
| `overrides/zh-CN.yaml` | 人工校对：覆盖某个条目的中文名称、摘要、说明和分类，优先级最高 | 人工，随时 |
| `featured.yaml` | 精选权重：决定插件页「推荐」排序 | 人工，随时 |
| `data/index.json` | 生成产物：守护进程拉取的覆盖层（中文 + 分类 + 精选） | 只由生成器写，禁止手改 |
| `data/machine.json` | 生成产物：机器翻译结果缓存，增量复用 | 只由生成器写，禁止手改 |

## 数据流

```
各厂商市场（GitHub）
  │  polaris/tools/catalog_overlay_gen.go -export：只导出新增或变更的条目，生成 batch-NNNN.json
  ▼
编码代理逐批翻译 + 分类，写出 result-NNNN.json
  │  -import：校验后并入 machine.json（机器结果缓存），再叠加 overrides 和 featured
  ▼
本仓库 main 分支 catalog/data/：index.json + machine.json
  │  人工确认后 git push
  ▼
Polaris 守护进程联网同步市场后拉取 raw.githubusercontent.com/polarisagi/polaris-plugins-official/main/catalog/data/index.json（ETag 条件请求）
```

操作步骤见 polaris 仓库 `local_playground/upgrade/plugin-catalog/06-local-translation.md`。
以后增量更新：`-export` 只会导出上游新增或变更的条目，通常只有几十条。

## 常见操作

- **改一个插件的中文**：在 `overrides/zh-CN.yaml` 里按条目 ID 加一段，然后在本地重新运行生成器（不需要翻译），提交 catalog/data/ 并推送 main。
  条目 ID 就是 Polaris 插件页条目的 ID，形如 `anthropic/claude-plugins-official/github`。
- **加精选**：在 `featured.yaml` 里加一行 `条目ID: 权重`。
- **加一个分类取值**：在 `taxonomy.yaml` 对应维度下加一行，en 和 zh 都要填。这只影响之后新翻译的条目；要让旧条目重新分类，
  在 machine.json 里删掉对应条目即可，下一次 `-export` 会把它重新导出。
- **Polaris 官方插件**：英文写在各插件的 `.codex-plugin/plugin.json`（description、interface.shortDescription、interface.longDescription），
  中文写在 `overrides/zh-CN.yaml`，两边内容要对应。
