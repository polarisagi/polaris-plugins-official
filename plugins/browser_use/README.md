# Polaris Browser Use MCP (v2.1.0)

🌎 [English](README.md) | 🇨🇳 [中文](README_zh.md)

> Full documentation: [docs/browser-use.md](../../docs/browser-use.md) (Chinese)

The official Polaris general-purpose browser automation plugin (open pages, read body text, snapshots, interaction, and browser connection).
It reuses your everyday signed-in Chrome session and supports modern, token-efficient DOM snapshot interaction.

> For search, trending lists, feed reading, and posting on known social platforms (Zhihu / X / Weibo / Xiaohongshu, etc.), use the `social_*` tools of the **polaris-social** plugin; this plugin contains no platform knowledge, site recipes, or rate limits.

---

## Key Features

- **Three backend architectures**:
  1. **Extension mode (recommended)**: works with the Polaris Browser Bridge extension (MV3), with no permission prompts, and supports fully automatic unattended scheduled collection.
  2. **CDP Toggle mode**: connects instantly through the remote-debugging switch at `chrome://inspect` in Chrome 155+, directly reusing the platforms the user is already signed in to.
  3. **Managed mode**: launches the system Chrome with a dedicated profile (`~/.config/polaris-plugins/browser/profiles/`), supporting endpoint reuse and standalone operation.
- **Chrome 136+ compatibility background**: since Chrome 136, Google has disabled the `--remote-debugging-port` command-line flag for the default user directory. This plugin takes a novel approach, combining `DevToolsActivePort` dynamic discovery with extension bridging, to attach securely with zero configuration.
- **Strict privacy isolation**: Polaris operates **only inside a separate window it created itself**, and is strictly forbidden from reading or interfering with your other everyday tabs.
- **Token-efficient design**:
  - `browser_read`: intelligent article extraction, condensed Markdown, plain text, and link lists, with transparent character-level pagination.
  - `browser_snapshot`: parameterized, refined semantic encoding (`e12 button "登录"`), rather than dumping raw HTML.

---

## Install the Extension (recommended, one-time, enables prompt-free unattended operation)

To completely eliminate the prompt in everyday Chrome that asks the user to click "Allow" on every connection, we recommend installing the official lightweight MV3 companion extension **Polaris Browser Bridge** (pure JS, with no external build dependencies and no sensitive permissions):

1. **One-click setup**: the extension and automatic pairing are provided by the companion plugin **polaris-browser-bridge** (this plugin already depends on it in its manifest). Tell Polaris "set up the browser extension" or call `bridge_setup`; it prepares the extension directory `~/.config/polaris-plugins/browser/extension/` and registers the Chrome auto-pairing host.
2. **Load the extension and pair automatically**: call `bridge_open_chrome_extensions` (macOS) to open `chrome://extensions`, turn on "Developer mode" → "Load unpacked", and select the directory above. The extension fetches the token automatically through Native Messaging, so **there is no need to copy and paste the token**. See [browser_bridge/README.md](../browser_bridge/README.md) for details.
3. **Verify it works**:
   - Call `browser_status` again; `backend` will show `extension`.
   - **Security note**: the attached tab shows Chrome's mandatory official security banner at the top, "Polaris Browser Bridge started debugging this browser", which is released and disappears automatically after 10 minutes of inactivity; all operations are performed in a separate window and never touch any of your existing tabs.

---

## Steps to Enable the Everyday Chrome Switch (CDP Toggle fallback mode)

1. Open the everyday Chrome browser you normally use;
2. Type into the address bar and press Enter: `chrome://inspect`;
3. Make sure **"Discover network targets"** at the top of the page is turned on;
4. When Polaris attaches for the first time, Chrome shows an "Allow remote debugging" prompt at the top; click **"Allow"**.

> **Tip**: if you want scheduled tasks to run fully unattended without any more prompts, we strongly recommend installing the Polaris Browser Bridge extension described above.

---

## Runtime Environment and Installation Advice

- **Local desktop environment (macOS / Windows / Linux)**: recommended to install and use daily; it makes the most of reusing signed-in social platforms and obtaining personalized information.
- **Cloud VPS / headless server environment**: **installing this plugin is not recommended**. On a headless server, use the kernel's built-in HTTP data-plane tools (`feed_fetch`, `web_fetch`, `web_search`) directly, which need no browser process or graphical-interface dependencies.

---

## Runtime Configuration Directory and Environment Variables

- **Configuration root directory**:
  - macOS / Linux: `~/.config/polaris-plugins/browser/`
  - Windows: `%APPDATA%\polaris-plugins\browser\`
- **Main environment variables**:
  - `POLARIS_BROWSER_BACKEND`: `auto` (default) | `extension` | `cdp` | `managed`
  - `POLARIS_BROWSER_DRIVER`: `patchright` (default) | `playwright`
  - `POLARIS_BROWSER_PROFILE`: profile directory name in managed mode (default `default`)
  - `POLARIS_BROWSER_HEADLESS`: whether to run headless (default `0`)
  - `POLARIS_BROWSER_IDLE_RELEASE_MIN`: idle release time in minutes (cdp defaults to `0`, meaning never released; extension defaults to `10`)

---

## Exposed Tools

| Tool | Type | Description |
|---|---|---|
| `browser_open` | Interactive | Opens a URL, either creating a new dedicated tab or reusing the working page |
| `browser_read` | Interactive | Token-efficient multi-mode (article/markdown/text/links) reading and pagination |
| `browser_snapshot`| Interactive | Extracts and labels the interactive elements (e<N>) of the current viewport or the full page |
| `browser_act` | Interactive | Performs precise clicks, typing, key presses, or back navigation on snapshot elements |
| `browser_scroll` | Interactive | Scrolls the page smoothly and returns the position |
| `browser_extract` | Interactive | Batch-extracts structured lists based on CSS selectors |
| `browser_tabs` | Interactive | Lists, switches, and closes the dedicated tabs |
| `browser_status` | Status | Shows the backend type, connection health, and the signed-in site cache |

> `POLARIS_BROWSER_CDP_URL`: explicitly specifies the CDP endpoint (for example when you have no permission to read `DevToolsActivePort` in Chrome's data directory); if it is not set and the port file is unreadable, use the Polaris Browser Bridge extension instead.
