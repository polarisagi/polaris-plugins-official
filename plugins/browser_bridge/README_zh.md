# Polaris Browser Bridge 设置插件 (v1.1.0)

🌎 [English](README.md) | 🇨🇳 [中文](README_zh.md)

MCP 服务器名 `polaris-browser-bridge`。它是 **Polaris Browser Bridge Chrome 扩展的唯一源码与设置入口**：
一键同步扩展到稳定目录、注册 Chrome Native Messaging 宿主以**自动配对令牌**、查看状态、轮换令牌。
`polaris-browser-use` 与 `polaris-social` 在清单中依赖本插件。

> 本插件进程**不运行中继**；中继在使用浏览器的插件进程（browser-use / social）里。连接状态通过中继写入的
> `~/.config/polaris-plugins/browser/bridge_last_handshake.json` 判断。

## 首次设置（约 1 分钟）

1. 在 Polaris **插件页**点本插件（或依赖它的 browser-use / social）的「**设置**」按钮，直接打开设置卡片；也可以对 Polaris 说「**设置浏览器扩展**」（或调用 `bridge_setup`）。
2. 点「打开 Chrome 扩展页」（或调用 `bridge_open_chrome_extensions`，macOS 会打开 `chrome://extensions` 并在 Finder 中定位扩展目录）。
3. 在 Chrome 扩展页：开启右上角「开发者模式」→「加载已解压的扩展程序」（或把文件夹拖入页面）→ 选择
   `~/.config/polaris-plugins/browser/extension/`。
4. 加载后扩展立即经 Native Messaging 自动配对并向本机报到，状态变为「设置已完成」。**无需粘贴令牌。**
   浏览器连接（中继）只在 browser-use / social 等插件使用浏览器时建立，空闲时不连接属正常。

插件重装或升级后，插件进程启动时会自动把新版扩展同步到同一目录并刷新宿主（曾设置过才会刷新），无需再点设置；
扩展版本变化时在 `chrome://extensions` 点一下「重新加载」（或见下文开发者重载）。

## Polaris 插件页集成

清单 `.codex-plugin/plugin.json` 在私有命名空间声明：

```json
"extensions": { "ai.polarisagi": { "setupTool": "bridge_setup", "statusTool": "bridge_status" } }
```

- 「设置」：Polaris 插件详情页的「设置」页直接嵌入设置卡片并显示逐项状态（不经模型、不计 token、不新建会话）。
- 状态：Polaris 调用 `bridge_status`，读取 `structuredContent.ready` / `message` / `checks`（逐项清单 `{key,label,ok,detail}`，`ok=null` 仅供参考）。`ready` 表示**一次性设置已完成**：
  本机已准备（令牌、扩展目录、自动配对宿主）、Chrome 中运行的扩展版本与稳定目录一致（证据取扩展报到与中继握手中较新者）、扩展令牌与本机一致；
  不代表此刻已连接（中继只在使用浏览器的插件进程中运行）。未就绪时，依赖本插件的 browser-use / social 卡片会提示「需要完成设置」。
- 清单快照在安装时记录：升级前已安装的 Polaris 需升级本插件才会出现「设置」按钮。

## 工具

| 工具 | 说明 |
|---|---|
| `bridge_setup` | 一键：确保令牌 → 同步扩展到稳定目录 → 注册 Native Messaging 宿主；声明了设置卡片 `ui://polaris-browser-bridge/setup.html` |
| `bridge_open_chrome_extensions` | macOS：`open -a "Google Chrome" chrome://extensions` + `open -R <extension-dir>/manifest.json`（argv 列表，不经 shell）；其他系统返回手动说明 |
| `bridge_status` | 令牌是否存在/权限、宿主是否注册、扩展目录是否就绪与版本、扩展当前是否连接。**不返回令牌明文** |
| `bridge_rotate_token` | 重新生成令牌（原子写、0600）；中继在下次握手/心跳时重读并断开旧连接，自动配对的扩展随后取新令牌 |

设置卡片是单文件 HTML（MCP Apps，`text/html;profile=mcp-app`），含三个按钮、三步说明和每 2 秒刷新的状态灯，适配深浅色。

## 自动配对如何工作

```
扩展 sw.js ──chrome.runtime.sendNativeMessage──▶ 宿主 (online.polarisagi.bridge)
        ◀── {"ok":true,"token":…,"relay_ports":[18790..18799],"version":…}
扩展 sw.js ──{"type":"hello","ext_version","token_fp"}──▶ 宿主   # 启动时与每 5 分钟报到
        ◀── {"ok":true,"token_fp":…}                              # 指纹不同 → 扩展重新配对
```

- 报到由宿主写入 `bridge_ext_presence.json`（时间、扩展版本、令牌是否一致），不依赖中继即可判断扩展已加载。
  令牌只以 SHA-256 前 16 位指纹比对，明文不出现在报到往返中。

- 宿主清单：macOS `~/Library/Application Support/Google/Chrome/NativeMessagingHosts/online.polarisagi.bridge.json`，
  Linux `~/.config/google-chrome/NativeMessagingHosts/`，Windows 写 `HKCU\Software\Google\Chrome\NativeMessagingHosts\online.polarisagi.bridge`（**Windows 未经真机验证**）。
- `allowed_origins` 只含扩展 ID `chrome-extension://ccdonkdehfibjcejkfjoicdklfdffjeh/`，其他扩展无法启动宿主。
- 宿主可执行文件是 `~/.config/polaris-plugins/browser/native-host/run_host.sh`（0700），以插件环境的**基础解释器**
  （`sys._base_executable`，不是插件 `.venv`）绝对路径执行同目录的 `native_host.py`（仅标准库）。Chrome 启动宿主时 PATH 很少，所以不依赖 PATH；
  不用 `.venv` 是因为它随插件重装而删除。`bridge_status` 会检查解释器是否存在、宿主脚本是否与插件内版本一致。
- 令牌文件 `~/.config/polaris-plugins/browser/bridge_token`（32 字节 hex，0600，原子创建）。

### 握手：双向 HMAC，令牌不上线路

```
扩展 → 中继  hello_init {nonce}
中继 → 扩展  challenge  {proof = HMAC(token, "relay:"+nonce), nonce2}
扩展 校验 proof 通过后 →  hello {proof = HMAC(token, "ext:"+nonce2+":"+nonce)}
中继 校验后 → hello_ok
```

扩展先确认对端持有令牌，才发出自己的证明，避免把凭据交给冒充中继的本地进程。旧版扩展（明文 `hello`+token）会被中继以
`4426` 拒绝并在日志/握手状态里提示升级；新版扩展遇到旧中继（回 `Expected hello`）会在设置页显示「中继需要更新」。

## 故障排查

| 现象 | 处理 |
|---|---|
| 扩展设置页显示「自动配对不可用：Specified native messaging host not found」 | 宿主未注册：运行 `bridge_setup`，然后在设置页点「重新自动配对」 |
| 「Native host has exited」 | `native-host/run_host.sh` 里的解释器路径失效：重新运行 `bridge_setup` |
| 「中继需要更新」 | 更新 browser-use / social 插件并重启 Polaris |
| 「中继身份校验失败」 | 令牌不一致或该端口上不是 Polaris 中继；点「重新自动配对」或运行 `bridge_rotate_token` |
| 状态灯一直黄色 | 扩展已就绪但没有插件进程在跑中继：让 Polaris 打开任意网页触发一次浏览器工具；日志见 `bridge_ext.log` |
| Windows / 其他浏览器 | 自动配对仅支持 Chrome；其他情况在扩展设置页手动粘贴令牌 |

## 开发者：修改扩展并重载

扩展唯一源码在 `plugins/browser_bridge/extension/`：

```bash
# 1. 改完 extension/ 下的代码后，同步到稳定目录（等价于调用 bridge_setup 的同步步骤）
cd plugins/browser_bridge && uv run python -c "from src import setup_ops, paths; print(setup_ops.sync_extension(paths.real_paths()))"
# 2. 让已配对的扩展从磁盘重载（需要有已连接的扩展）；日志见 ~/.config/polaris-plugins/browser/bridge_ext.log
cd ../social && uv run python scripts/bridge_reload.py
```

运行测试：`cd plugins/browser_bridge && uv run pytest -q tests`。

## 签名私钥 `extension-signing-key.pem`

`extension/manifest.json` 里的 `key` 字段是公钥，决定扩展 ID（`ccdonkdehfibjcejkfjoicdklfdffjeh`）。对应私钥**不在仓库里**：
保管在 `~/.config/polaris-plugins/browser/extension-signing-key.pem`（0600，`.gitignore` 已忽略 `*.pem`）。
丢失它不影响已有扩展运行，但以后无法再证明同一个扩展 ID 的所有权（例如上架商店）；请妥善备份，切勿提交或打包。
`scripts/ext_id.py [path-to-pem]` 可由私钥重新计算公钥和扩展 ID。

## 运行时文件

均位于 `~/.config/polaris-plugins/browser/`（Windows 为 `%APPDATA%\polaris-plugins\browser\`）：
`bridge_token`、`extension/`、`native-host/`、`bridge_last_handshake.json`、`bridge_ext_seen`、`bridge_ext.log`。
Chrome 侧只多一个宿主清单文件（见上）。
