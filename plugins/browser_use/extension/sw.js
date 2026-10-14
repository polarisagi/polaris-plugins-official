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

// port -> { ws, windowId, ownedTabs: Set<number>, client: string }
const connections = new Map();

// tabId -> port
const tabToPort = new Map();

// 获取配对令牌
async function getStoredToken() {
  const data = await chrome.storage.local.get(["token"]);
  return data.token || "";
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
}

// 连接单个端口的中继
async function tryConnectPort(port) {
  if (connections.has(port)) {
    const existing = connections.get(port);
    if (existing.ws.readyState === WebSocket.OPEN || existing.ws.readyState === WebSocket.CONNECTING) {
      return;
    }
  }

  const token = await getStoredToken();
  const url = `ws://127.0.0.1:${port}/bridge`;
  let ws;
  try {
    ws = new WebSocket(url);
  } catch (err) {
    return;
  }

  const connState = {
    ws,
    windowId: null,
    ownedTabs: new Set(),
    client: ""
  };

  ws.onopen = () => {
    // 握手
    ws.send(JSON.stringify({
      type: "hello",
      token: token,
      ext_version: "1.0.0",
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

    if (msg.type === "hello_ok") {
      connState.client = msg.client || "polaris";
      connections.set(port, connState);
      await updateOptionsStatus();
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

  ws.onclose = () => {
    connections.delete(port);
    for (const [tabId, p] of tabToPort.entries()) {
      if (p === port) {
        tabToPort.delete(tabId);
        // 连接断开时安全分离调试器，但不关闭标签，避免用户未保存数据丢失
        chrome.debugger.detach({ tabId }).catch(() => {});
      }
    }
    updateOptionsStatus();
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

  try {
    if (method === "createTab") {
      const targetUrl = (params && params.url) || "about:blank";
      let windowId = connState.windowId;

      const valid = await isWindowValid(windowId);
      if (!valid) {
        // 第一次创建独立窗口，focused: false 避免夺取用户当前打字焦点
        const win = await chrome.windows.create({
          url: targetUrl,
          focused: false,
          type: "normal"
        });
        connState.windowId = win.id;
        windowId = win.id;
        const tab = win.tabs[0];
        const tabId = tab.id;

        connState.ownedTabs.add(tabId);
        tabToPort.set(tabId, port);

        await chrome.debugger.attach({ tabId }, "1.3");

        const targetInfo = {
          targetId: `tab-${tabId}`,
          type: "page",
          title: tab.title || "",
          url: tab.url || targetUrl,
          attached: true,
          browserContextId: "default"
        };

        connState.ws.send(JSON.stringify({
          id,
          result: { tabId, targetInfo }
        }));
      } else {
        const tab = await chrome.tabs.create({
          windowId,
          url: targetUrl,
          active: false
        });
        const tabId = tab.id;

        connState.ownedTabs.add(tabId);
        tabToPort.set(tabId, port);

        await chrome.debugger.attach({ tabId }, "1.3");

        const targetInfo = {
          targetId: `tab-${tabId}`,
          type: "page",
          title: tab.title || "",
          url: tab.url || targetUrl,
          attached: true,
          browserContextId: "default"
        };

        connState.ws.send(JSON.stringify({
          id,
          result: { tabId, targetInfo }
        }));
      }
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

// 定时保活与自动重连
chrome.alarms.create("bridge_discovery", { periodInMinutes: 1 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "bridge_discovery") {
    discoverAndConnect();
  }
});

// 初始化启动探测
discoverAndConnect();
