# Polaris Browser Bridge Setup Plugin (v1.1.0)

🌎 [English](README.md) | 🇨🇳 [中文](README_zh.md)

MCP server name `polaris-browser-bridge`. It is the **sole source and setup entry for the Polaris Browser Bridge Chrome extension**:
it syncs the extension to a stable directory in one click, registers the Chrome Native Messaging host to **pair the token automatically**, shows the status, and rotates the token.
`polaris-browser-use` and `polaris-social` depend on this plugin in their manifests.

> This plugin's process **does not run the relay**; the relay lives in the process of the plugin that uses the browser (browser-use / social). The connection state is determined from
> `~/.config/polaris-plugins/browser/bridge_last_handshake.json`, which the relay writes.

## First-Time Setup (about 1 minute)

1. On the Polaris **plugins page**, click the "**Settings**" button of this plugin (or of a plugin that depends on it, browser-use / social) to open the setup card directly; you can also tell Polaris "**set up the browser extension**" (or call `bridge_setup`).
2. Click "Open Chrome extensions page" (or call `bridge_open_chrome_extensions`; on macOS it opens `chrome://extensions` and reveals the extension directory in Finder).
3. On the Chrome extensions page: turn on "Developer mode" in the top right → "Load unpacked" (or drag the folder onto the page) → select
   `~/.config/polaris-plugins/browser/extension/`.
4. Wait for the status light to turn green (the extension probes the local relay every 30 seconds; a plugin process must be using the browser). **There is no need to paste a token.**

After a plugin upgrade, simply run `bridge_setup` again to sync the new extension version to the same directory, with the path unchanged; then click "Reload" once in `chrome://extensions`
(or see the developer reload below).

## Polaris Plugins Page Integration

The manifest `.codex-plugin/plugin.json` declares in a private namespace:

```json
"extensions": { "ai.polarisagi": { "setupTool": "bridge_setup", "statusTool": "bridge_status" } }
```

- "Settings" button: Polaris runs `bridge_setup` directly (bypassing the model, consuming no tokens) and opens the setup card as a message.
- Status: Polaris calls `bridge_status` and reads `structuredContent.ready` / `message`. `ready` means the **one-time setup is complete**:
  this machine is prepared (token, extension directory, auto-pairing host), the new extension version has completed a handshake successfully, and the version running in Chrome matches the stable directory;
  it does not mean it is connected right now (the relay only runs in the process of a plugin that uses the browser). When it is not ready, the browser-use / social cards that depend on this plugin show "Setup required".
- The manifest snapshot is recorded at install time: a Polaris installed before the upgrade needs to upgrade this plugin before the "Settings" button appears.

## Tools

| Tool | Description |
|---|---|
| `bridge_setup` | One click: ensure the token → sync the extension to the stable directory → register the Native Messaging host; declares the setup card `ui://polaris-browser-bridge/setup.html` |
| `bridge_open_chrome_extensions` | macOS: `open -a "Google Chrome" chrome://extensions` + `open -R <extension-dir>/manifest.json` (argv list, bypassing the shell); other systems return manual instructions |
| `bridge_status` | Whether the token exists and its permissions, whether the host is registered, whether the extension directory is ready and its version, and whether the extension is currently connected. **Never returns the token in plaintext** |
| `bridge_rotate_token` | Regenerates the token (atomic write, 0600); the relay rereads it at the next handshake/heartbeat and drops the old connection, after which the auto-paired extension fetches the new token |

The setup card is a single-file HTML (MCP Apps, `text/html;profile=mcp-app`) with three buttons, three-step instructions, and a status light refreshed every 2 seconds, adapted to light and dark themes.

## How Auto-Pairing Works

```
扩展 sw.js ──chrome.runtime.sendNativeMessage──▶ 宿主 (online.polarisagi.bridge)
        ◀── {"ok":true,"token":…,"relay_ports":[18790..18799],"version":…}
```

- Host manifest: on macOS `~/Library/Application Support/Google/Chrome/NativeMessagingHosts/online.polarisagi.bridge.json`,
  on Linux `~/.config/google-chrome/NativeMessagingHosts/`, and on Windows it is written to `HKCU\Software\Google\Chrome\NativeMessagingHosts\online.polarisagi.bridge` (**Windows has not been verified on real hardware**).
- `allowed_origins` contains only the extension ID `chrome-extension://ccdonkdehfibjcejkfjoicdklfdffjeh/`, so no other extension can launch the host.
- The host executable is `~/.config/polaris-plugins/browser/native-host/run_host.sh` (0700), which uses the **absolute path** of the `sys.executable` of the plugin environment in which `bridge_setup` was run to execute the `native_host.py` in the same directory (standard library only). Chrome starts the host with very little PATH, so it does not rely on PATH.
  If uv later rebuilds the environment and the interpreter path becomes invalid, simply run `bridge_setup` again.
- Token file `~/.config/polaris-plugins/browser/bridge_token` (32-byte hex, 0600, created atomically).

### Handshake: Mutual HMAC, the Token Never Goes on the Wire

```
扩展 → 中继  hello_init {nonce}
中继 → 扩展  challenge  {proof = HMAC(token, "relay:"+nonce), nonce2}
扩展 校验 proof 通过后 →  hello {proof = HMAC(token, "ext:"+nonce2+":"+nonce)}
中继 校验后 → hello_ok
```

The extension first confirms that the peer holds the token before sending its own proof, which avoids handing the credential to a local process impersonating the relay. An old-version extension (plaintext `hello` + token) is rejected by the relay with
`4426`, with an upgrade prompt in the log / handshake status; when a new-version extension meets an old relay (which replies `Expected hello`), it shows "Relay needs an update" on the settings page.

## Troubleshooting

| Symptom | Resolution |
|---|---|
| The extension settings page shows "Auto-pairing unavailable: Specified native messaging host not found" | The host is not registered: run `bridge_setup`, then click "Re-pair automatically" on the settings page |
| "Native host has exited" | The interpreter path in `native-host/run_host.sh` is invalid: run `bridge_setup` again |
| "Relay needs an update" | Update the browser-use / social plugins and restart Polaris |
| "Relay identity check failed" | The token does not match, or the port is not a Polaris relay; click "Re-pair automatically" or run `bridge_rotate_token` |
| The status light stays yellow | The extension is ready but no plugin process is running the relay: have Polaris open any web page to trigger a browser tool once; see `bridge_ext.log` for logs |
| Windows / other browsers | Auto-pairing supports Chrome only; in other cases paste the token manually on the extension settings page |

## For Developers: Modify the Extension and Reload

The extension's sole source is in `plugins/browser_bridge/extension/`:

```bash
# 1. 改完 extension/ 下的代码后，同步到稳定目录（等价于调用 bridge_setup 的同步步骤）
cd plugins/browser_bridge && uv run python -c "from src import setup_ops, paths; print(setup_ops.sync_extension(paths.real_paths()))"
# 2. 让已配对的扩展从磁盘重载（需要有已连接的扩展）；日志见 ~/.config/polaris-plugins/browser/bridge_ext.log
cd ../social && uv run python scripts/bridge_reload.py
```

Run the tests: `cd plugins/browser_bridge && uv run pytest -q tests`.

## Signing Private Key `extension-signing-key.pem`

The `key` field in `extension/manifest.json` is the public key, which determines the extension ID (`ccdonkdehfibjcejkfjoicdklfdffjeh`). The corresponding private key is **not in the repository**:
it is kept at `~/.config/polaris-plugins/browser/extension-signing-key.pem` (0600; `*.pem` is ignored by `.gitignore`).
Losing it does not affect extensions that already run, but you will no longer be able to prove ownership of the same extension ID later (for example to publish to a store); back it up carefully, and never commit or package it.
`scripts/ext_id.py [path-to-pem]` can recompute the public key and the extension ID from the private key.

## Runtime Files

All located in `~/.config/polaris-plugins/browser/` (on Windows `%APPDATA%\polaris-plugins\browser\`):
`bridge_token`, `extension/`, `native-host/`, `bridge_last_handshake.json`, `bridge_ext_seen`, `bridge_ext.log`.
Chrome gets just one extra file, the host manifest (see above).
