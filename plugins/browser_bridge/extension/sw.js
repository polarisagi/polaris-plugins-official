/**
 * Polaris Browser Bridge — Service Worker (MV3)
 *
 * 职责：
 * 1. 自动发现本地 18790-18799 端口上的 Polaris 中继并建立 WebSocket 连接；
 * 2. 接收中继转发的 createTab / cdp / closeTab 命令，调用 chrome.debugger 与 chrome.tabs；
 * 3. 严格隔离：仅允许操作本扩展自建的标签页，严禁触碰用户的日常标签；
 * 4. 监听调试器与标签事件并回传给中继。
 */

const START_PORT = 18790;
const END_PORT = 18799;

// Native Messaging 宿主名：必须与 bridge_const.NATIVE_HOST_NAME 一致
const NATIVE_HOST = "online.polarisagi.bridge";
// 握手协议版本：2 = 双向 HMAC 证明（令牌不在线路上传输）
const HANDSHAKE_VERSION = 2;

// port -> { ws, windowId, ownedTabs: Set<number>, client: string }
const connections = new Map();

// tabId -> port
const tabToPort = new Map();

// port -> 尚未完成握手的 WebSocket。同一端口只允许一条在途连接：
// 否则重复握手会让中继踢掉旧连接，旧连接关闭时又分离了刚建好的标签调试器
const pendingSockets = new Map();

const EXT_VERSION = chrome.runtime.getManifest().version;

// 日志：同时写本地控制台并回传给所有已握手的中继（中继落盘到
// ~/.config/polaris-plugins/browser/bridge_ext.log），便于无界面排障
function log(level, ...args) {
  const text = args
    .map((a) => (typeof a === "string" ? a : (() => { try { return JSON.stringify(a); } catch { return String(a); } })()))
    .join(" ");
  (level === "error" ? console.error : console.log)(`[bridge] ${text}`);
  for (const conn of connections.values()) {
    if (conn.ws.readyState === WebSocket.OPEN) {
      try {
        conn.ws.send(JSON.stringify({ type: "log", level, msg: text, ts: Date.now() }));
      } catch {}
    }
  }
}

// 无可用连接时短间隔重试；service worker 存活期间生效，休眠后由 alarms 兜底唤醒
let reconnectTimer = null;
function scheduleReconnect(delayMs = 2000) {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    const hasOpen = [...connections.values()].some((c) => c.ws.readyState === WebSocket.OPEN);
    if (!hasOpen) {
      discoverAndConnect();
      scheduleReconnect(Math.min(delayMs * 2, 15000));
    }
  }, delayMs);
}

// ── 配对令牌：优先经 Native Messaging 自动获取，失败回退手动粘贴 ─────────────

const enc = new TextEncoder();
let pairInflight = null;
let lastPairAttempt = 0;
const PAIR_RETRY_MS = 20000;

function sendNative(message) {
  return new Promise((resolve, reject) => {
    try {
      chrome.runtime.sendNativeMessage(NATIVE_HOST, message, (resp) => {
        const err = chrome.runtime.lastError;
        if (err) reject(new Error(err.message));
        else resolve(resp);
      });
    } catch (e) {
      reject(e);
    }
  });
}

// 向本地宿主取令牌并存入 storage（来源标记为 auto）。同一时刻只允许一次在途请求，并限频，
// 避免宿主未注册时每次重连都拉起子进程。force=true 忽略限频（用户点击或令牌被拒时）
async function autoPair({ force = false } = {}) {
  if (pairInflight) return pairInflight;
  if (!force && Date.now() - lastPairAttempt < PAIR_RETRY_MS) return "";
  lastPairAttempt = Date.now();
  pairInflight = (async () => {
    try {
      const resp = await sendNative({ type: "get_pairing" });
      if (resp && resp.ok && /^[0-9a-f]{64}$/i.test(String(resp.token || ""))) {
        const cur = await chrome.storage.local.get(["token"]);
        const patch = { tokenSource: "auto", pairError: null, hostVersion: String(resp.version || "") };
        // 令牌没变就不重写 token，避免触发 onChanged 导致无谓重连
        if (cur.token !== resp.token) patch.token = resp.token;
        await chrome.storage.local.set(patch);
        log("info", "已通过 Native Messaging 自动配对");
        return resp.token;
      }
      const reason = (resp && resp.error) || "宿主应答无效";
      await chrome.storage.local.set({ pairError: String(reason) });
      log("error", `自动配对失败: ${reason}`);
    } catch (e) {
      // 最常见：宿主未注册（尚未运行 bridge_setup）
      await chrome.storage.local.set({ pairError: String(e.message || e) });
      log("error", `自动配对不可用: ${e.message || e}`);
    }
    return "";
  })().finally(() => { pairInflight = null; });
  return pairInflight;
}

// 取当前可用令牌：已有则直接用，没有则尝试自动配对
async function resolveToken() {
  const data = await chrome.storage.local.get(["token"]);
  if (data.token) return data.token;
  return (await autoPair()) || "";
}

function toHex(buf) {
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}
function fromHex(hex) {
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(hex.substr(i * 2, 2), 16);
  return out;
}
function hmacKey(token) {
  return crypto.subtle.importKey("raw", enc.encode(token), { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"]);
}
async function hmacHex(token, message) {
  return toHex(await crypto.subtle.sign("HMAC", await hmacKey(token), enc.encode(message)));
}
// 用 subtle.verify 做常量时间比较
async function hmacVerify(token, message, hex) {
  if (!/^[0-9a-f]{64}$/.test(hex || "")) return false;
  return crypto.subtle.verify("HMAC", await hmacKey(token), fromHex(hex), enc.encode(message));
}
function randomHex(bytes) {
  return toHex(crypto.getRandomValues(new Uint8Array(bytes)));
}

// 令牌被拒/中继不可信时的统一处理：落盘原因；自动配对来源则重新向宿主取令牌
async function handleAuthFailure(kind, port, reason) {
  await chrome.storage.local.set({ lastAuthError: { kind, port, reason: reason || "", ts: Date.now() } });
  const { tokenSource } = await chrome.storage.local.get(["tokenSource"]);
  if (tokenSource === "auto") {
    await autoPair({ force: false });
  }
}

// 工具栏图标角标：已连接 ✓（绿）、令牌被拒 !（红）、其余清空
async function updateBadge(connected) {
  const { lastAuthError, token } = await chrome.storage.local.get(["lastAuthError", "token"]);
  if (connected) {
    await chrome.action.setBadgeBackgroundColor({ color: "#16a34a" });
    await chrome.action.setBadgeText({ text: "✓" });
  } else if (!token || lastAuthError) {
    await chrome.action.setBadgeBackgroundColor({ color: "#dc2626" });
    await chrome.action.setBadgeText({ text: "!" });
  } else {
    await chrome.action.setBadgeText({ text: "" });
  }
}

// 记录连接状态供 options 页面展示
async function updateOptionsStatus() {
  const list = [];
  for (const [port, conn] of connections.entries()) {
    list.push({
      port,
      client: conn.client || "connecting",
      tabs: conn.ownedTabs.size
    });
  }
  await chrome.storage.local.set({ activeConnections: list });
  await updateBadge(list.length > 0);
}

// 连接单个端口的中继
async function tryConnectPort(port) {
  if (connections.has(port)) {
    const existing = connections.get(port);
    if (existing.ws.readyState === WebSocket.OPEN || existing.ws.readyState === WebSocket.CONNECTING) {
      return;
    }
  }

  const pending = pendingSockets.get(port);
  if (pending && (pending.readyState === WebSocket.OPEN || pending.readyState === WebSocket.CONNECTING)) {
    return;
  }
  // 先占位再 await，防止并发调用在读取令牌期间重复建连
  pendingSockets.set(port, { readyState: WebSocket.CONNECTING });

  const token = await resolveToken();
  if (!token) {
    // 无令牌：自动配对与手动粘贴都未就绪，不连接（状态在设置页与角标提示）
    pendingSockets.delete(port);
    return;
  }
  const url = `ws://127.0.0.1:${port}/bridge`;
  let ws;
  try {
    ws = new WebSocket(url);
  } catch (err) {
    pendingSockets.delete(port);
    return;
  }
  pendingSockets.set(port, ws);

  const connState = {
    ws,
    windowId: null,
    ownedTabs: new Set(),
    client: "",
    nonce: ""
  };

  ws.onopen = () => {
    // 握手第一步：只发随机数，不发令牌
    connState.nonce = randomHex(16);
    ws.send(JSON.stringify({
      type: "hello_init",
      nonce: connState.nonce,
      proto: HANDSHAKE_VERSION,
      ext_version: EXT_VERSION,
      ua: navigator.userAgent
    }));
  };

  ws.onmessage = async (event) => {
    let msg;
    try {
      msg = JSON.parse(event.data);
    } catch (e) {
      return;
    }

    if (msg.type === "challenge") {
      // 先验证中继确实持有令牌，再发送自己的证明，防止冒充中继的本地进程套取凭据
      const ok = await hmacVerify(token, `relay:${connState.nonce}`, String(msg.proof || ""));
      if (!ok) {
        log("error", `中继身份校验失败 port=${port}（令牌不一致或对端不是 Polaris 中继）`);
        await handleAuthFailure("relay_untrusted", port, "relay proof mismatch");
        ws.close(4000, "relay proof mismatch");
        return;
      }
      const nonce2 = String(msg.nonce2 || "");
      ws.send(JSON.stringify({
        type: "hello",
        proof: await hmacHex(token, `ext:${nonce2}:${connState.nonce}`),
        ext_version: EXT_VERSION,
        ua: navigator.userAgent
      }));
      return;
    }

    if (msg.type === "hello_ok") {
      connState.client = msg.client || "polaris";
      if (pendingSockets.get(port) === ws) pendingSockets.delete(port);
      connections.set(port, connState);
      await chrome.storage.local.set({ lastAuthError: null });
      await updateOptionsStatus();
      log("info", `已与中继握手 port=${port} client=${connState.client} ext=${EXT_VERSION}`);
      return;
    }

    if (msg.type === "ping") {
      ws.send(JSON.stringify({ type: "pong" }));
      return;
    }

    // 处理中继发送的 RPC 命令
    if (typeof msg.id !== "undefined" && msg.method) {
      handleRelayCommand(port, connState, msg);
    }
  };

  ws.onclose = async (ev) => {
    if (pendingSockets.get(port) === ws) pendingSockets.delete(port);
    // 4401：中继拒绝令牌（或握手失败），先落盘再刷新状态，保证角标与设置页一致
    if (ev && ev.code === 4401) {
      // 旧版中继只认明文 hello，会回 "Expected hello"：提示用户更新插件而不是误报令牌错误
      const outdated = ev.reason === "Expected hello";
      if (outdated) log("error", `中继版本过旧（不支持握手协议 2）port=${port}，请更新 browser-use / social 插件`);
      await handleAuthFailure(outdated ? "relay_outdated" : "token_rejected", port, ev.reason || "");
    }
    // 只清理本连接自己的记录：同端口可能已被新连接替换（如令牌变更后重连）
    if (connections.get(port) === connState) {
      connections.delete(port);
      for (const tabId of connState.ownedTabs) {
        if (tabToPort.get(tabId) === port) {
          tabToPort.delete(tabId);
          // 连接断开时安全分离调试器，但不关闭标签，避免用户未保存数据丢失
          chrome.debugger.detach({ tabId }).catch(() => {});
        }
      }
    }
    await updateOptionsStatus();
    scheduleReconnect();
  };

  ws.onerror = () => {
    ws.close();
  };
}

// 调度所有候选端口探测
async function discoverAndConnect() {
  for (let p = START_PORT; p <= END_PORT; p++) {
    tryConnectPort(p);
  }
}

// 标签页状态与窗口清理检查
async function isWindowValid(windowId) {
  if (!windowId) return false;
  try {
    await chrome.windows.get(windowId);
    return true;
  } catch {
    return false;
  }
}

// 处理中继下发的命令
async function handleRelayCommand(port, connState, msg) {
  const { id, method, params } = msg;
  const t0 = performance.now();
  const ms = () => Math.round(performance.now() - t0);

  try {
    if (method === "reloadExtension") {
      log("info", "收到中继重载指令，扩展即将从磁盘重新加载");
      connState.ws.send(JSON.stringify({ id, result: { ok: true, version: EXT_VERSION } }));
      setTimeout(() => chrome.runtime.reload(), 200);
      return;
    }

    if (method === "createTab") {
      const targetUrl = (params && params.url) || "about:blank";
      let tab;
      if (await isWindowValid(connState.windowId)) {
        tab = await chrome.tabs.create({ windowId: connState.windowId, url: targetUrl, active: false });
      } else {
        // 第一次创建独立窗口，focused: false 避免夺取用户当前打字焦点
        log("info", `createTab: 新建独立窗口 url=${targetUrl}`);
        const win = await chrome.windows.create({ url: targetUrl, focused: false, type: "normal" });
        connState.windowId = win.id;
        tab = win.tabs[0];
        log("info", `createTab: 窗口已建 windowId=${win.id} (+${ms()}ms)`);
      }
      const tabId = tab.id;
      connState.ownedTabs.add(tabId);
      tabToPort.set(tabId, port);

      await chrome.debugger.attach({ tabId }, "1.3");

      // 必须使用 Chrome 真实的 targetId：Playwright 以 targetId 作为主框架会话键，
      // 且依赖「主框架 id == targetId」；伪造 id 会导致 goto 报 Frame has been detached
      let targetInfo;
      try {
        const res = await chrome.debugger.sendCommand({ tabId }, "Target.getTargetInfo");
        targetInfo = { ...res.targetInfo, attached: true };
      } catch (e) {
        log("error", `createTab: 读取 targetInfo 失败，回退为占位信息: ${e.message || e}`);
        targetInfo = {
          targetId: `tab-${tabId}`,
          type: "page",
          title: tab.title || "",
          url: tab.url || targetUrl,
          attached: true,
          browserContextId: "default"
        };
      }
      log("info", `createTab: 已附着 tabId=${tabId} targetId=${targetInfo.targetId} (+${ms()}ms)`);

      connState.ws.send(JSON.stringify({ id, result: { tabId, targetInfo } }));
      await updateOptionsStatus();
      return;
    }

    if (method === "cdp") {
      const { tabId, method: cdpMethod, params: cdpParams, sessionId } = params;
      // 严格权限校验：只允许操作自有标签
      if (!connState.ownedTabs.has(tabId)) {
        connState.ws.send(JSON.stringify({
          id,
          error: { message: `Tab ${tabId} is not owned by this connection` }
        }));
        return;
      }

      const target = { tabId };
      if (sessionId) {
        target.sessionId = sessionId;
      }

      const res = await chrome.debugger.sendCommand(target, cdpMethod, cdpParams || {});
      connState.ws.send(JSON.stringify({
        id,
        result: res || {}
      }));
      return;
    }

    if (method === "closeTab") {
      const { tabId } = params;
      if (!connState.ownedTabs.has(tabId)) {
        connState.ws.send(JSON.stringify({
          id,
          error: { message: `Tab ${tabId} is not owned by this connection` }
        }));
        return;
      }

      connState.ownedTabs.delete(tabId);
      tabToPort.delete(tabId);
      try {
        await chrome.debugger.detach({ tabId });
      } catch {}
      try {
        await chrome.tabs.remove(tabId);
      } catch {}

      connState.ws.send(JSON.stringify({
        id,
        result: { ok: true }
      }));
      await updateOptionsStatus();
      return;
    }

    if (method === "listTabs") {
      const tabs = [];
      for (const tabId of connState.ownedTabs) {
        try {
          const t = await chrome.tabs.get(tabId);
          tabs.push({
            tabId,
            url: t.url,
            title: t.title
          });
        } catch {}
      }
      connState.ws.send(JSON.stringify({
        id,
        result: { tabs }
      }));
      return;
    }

    connState.ws.send(JSON.stringify({
      id,
      error: { message: `Unknown method: ${method}` }
    }));
  } catch (err) {
    const cdpMethod = method === "cdp" && params ? params.method : "";
    log("error", `命令失败 ${method}${cdpMethod ? " " + cdpMethod : ""} (+${ms()}ms): ${err.message || err}`);
    connState.ws.send(JSON.stringify({
      id,
      error: { message: err.message || String(err) }
    }));
  }
}

// 监听调试器 CDP 事件并回传
chrome.debugger.onEvent.addListener((source, method, params) => {
  const port = tabToPort.get(source.tabId);
  if (!port) return;

  const connState = connections.get(port);
  if (!connState || connState.ws.readyState !== WebSocket.OPEN) return;

  connState.ws.send(JSON.stringify({
    type: "cdp_event",
    tabId: source.tabId,
    sessionId: source.sessionId || null,
    method,
    params: params || {}
  }));
});

// 监听调试器分离（如用户点击了顶部提示条的取消）
chrome.debugger.onDetach.addListener((source, reason) => {
  const port = tabToPort.get(source.tabId);
  if (!port) return;

  const connState = connections.get(port);
  if (!connState) return;

  connState.ownedTabs.delete(source.tabId);
  tabToPort.delete(source.tabId);

  if (connState.ws.readyState === WebSocket.OPEN) {
    connState.ws.send(JSON.stringify({
      type: "detached",
      tabId: source.tabId,
      reason
    }));
  }
  updateOptionsStatus();
});

// 监听标签页被用户主动关闭
chrome.tabs.onRemoved.addListener((tabId) => {
  const port = tabToPort.get(tabId);
  if (!port) return;

  const connState = connections.get(port);
  if (!connState) return;

  connState.ownedTabs.delete(tabId);
  tabToPort.delete(tabId);

  if (connState.ws.readyState === WebSocket.OPEN) {
    connState.ws.send(JSON.stringify({
      type: "detached",
      tabId,
      reason: "tab_closed"
    }));
  }
  updateOptionsStatus();
});

// 设置页消息：重新自动配对（清掉手动令牌，改用 Native Messaging）
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg && msg.type === "repair") {
    (async () => {
      await chrome.storage.local.remove(["token", "tokenSource", "lastAuthError"]);
      const token = await autoPair({ force: true });
      sendResponse({ ok: !!token });
    })();
    return true; // 异步应答
  }
  return false;
});

// 令牌变化后立即断开旧连接并用新令牌重连
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes.token) {
    for (const conn of connections.values()) {
      try { conn.ws.close(); } catch {}
    }
    connections.clear();
    for (const ws of pendingSockets.values()) {
      try { if (ws.close) ws.close(); } catch {}
    }
    pendingSockets.clear();
    discoverAndConnect();
  }
});

// 首次安装且尚未配对时自动打开设置页
chrome.runtime.onInstalled.addListener(async (details) => {
  if (details.reason === "install") {
    // 先尝试自动配对；宿主未注册时再打开设置页让用户看到原因/手动粘贴
    const token = await autoPair({ force: true });
    if (!token) chrome.runtime.openOptionsPage();
  }
});

// 定时保活与自动重连（Chrome 120+ 允许最短 30 秒）
chrome.alarms.create("bridge_discovery", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "bridge_discovery") {
    discoverAndConnect();
  }
});

// 初始化：service worker 重启后内存中的连接已全部失效，先清掉存储里残留的连接状态
updateOptionsStatus().finally(() => {
  discoverAndConnect();
  scheduleReconnect();
});
