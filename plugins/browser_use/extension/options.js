document.addEventListener("DOMContentLoaded", async () => {
  // 工具栏弹窗与独立设置页共用本页面：弹窗模式下固定宽度，避免被 Chrome 收缩
  if (new URLSearchParams(location.search).get("popup") === "1") {
    document.body.classList.add("popup");
  }

  const $ = (id) => document.getElementById(id);
  const tokenInput = $("tokenInput");
  const saveStatus = $("saveStatus");
  $("version").textContent = "v" + chrome.runtime.getManifest().version;

  let state = await chrome.storage.local.get(["token", "activeConnections", "lastAuthError"]);
  render();

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== "local") return;
    for (const [k, v] of Object.entries(changes)) state[k] = v.newValue;
    render();
  });

  $("saveBtn").addEventListener("click", async () => {
    const token = tokenInput.value.trim();
    if (!/^[0-9a-f]{64}$/i.test(token)) {
      flash("令牌格式不正确（应为 64 位十六进制字符）", true);
      return;
    }
    // service worker 监听 token 变化后会立即用新令牌重连
    await chrome.storage.local.set({ token, lastAuthError: null });
    tokenInput.value = "";
    flash("✔ 已保存，正在连接本地中继…");
  });

  $("clearBtn").addEventListener("click", async () => {
    await chrome.storage.local.remove(["token", "lastAuthError"]);
    flash("已清除令牌");
  });

  function flash(text, isErr = false) {
    saveStatus.classList.toggle("err", isErr);
    saveStatus.textContent = text;
    setTimeout(() => { saveStatus.textContent = ""; }, 4000);
  }

  function mask(t) {
    return t.length > 12 ? `${t.slice(0, 6)}••••••${t.slice(-4)}` : "••••";
  }

  function render() {
    const token = state.token || "";
    const conns = state.activeConnections || [];

    $("savedRow").hidden = !token;
    $("savedToken").textContent = token ? mask(token) : "";

    const el = $("connState");
    const hint = $("connHint");
    if (!token) {
      el.className = "state bad";
      el.textContent = "未配对";
      hint.textContent = "请粘贴 Polaris 生成的配对令牌（保存在 ~/.config/polaris-plugins/browser/bridge_token）。";
    } else if (conns.length > 0) {
      el.className = "state ok";
      el.textContent = "已连接";
      hint.textContent = "";
    } else if (state.lastAuthError) {
      el.className = "state bad";
      el.textContent = "令牌被拒绝";
      hint.textContent = "中继拒绝了当前令牌，请重新粘贴 bridge_token 文件中的令牌。";
    } else {
      el.className = "state off";
      el.textContent = "未连接";
      hint.textContent = "令牌已保存。Polaris 或插件需要浏览器时会自动启动中继，扩展随即连接。";
    }

    // 用 DOM API 渲染，避免把中继上报的字段当 HTML 注入
    const box = $("connectionsList");
    box.replaceChildren();
    if (conns.length === 0) return;
    const ul = document.createElement("ul");
    for (const c of conns) {
      const li = document.createElement("li");
      const strong = document.createElement("strong");
      strong.textContent = String(c.client || "");
      const code = document.createElement("code");
      code.textContent = `127.0.0.1:${Number(c.port) || ""}`;
      li.append(strong, " · ", code, ` · 活动标签 ${Number(c.tabs) || 0}`);
      ul.append(li);
    }
    box.append(ul);
  }
});
