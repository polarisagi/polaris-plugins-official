document.addEventListener("DOMContentLoaded", async () => {
  // 工具栏弹窗与独立设置页共用本页面：弹窗模式下固定宽度，避免被 Chrome 收缩
  if (new URLSearchParams(location.search).get("popup") === "1") {
    document.body.classList.add("popup");
  }

  const $ = (id) => document.getElementById(id);
  const tokenInput = $("tokenInput");
  const saveStatus = $("saveStatus");
  $("version").textContent = "v" + chrome.runtime.getManifest().version;

  let state = await chrome.storage.local.get(["token", "tokenSource", "pairError", "activeConnections", "lastAuthError"]);
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
    await chrome.storage.local.set({ token, tokenSource: "manual", lastAuthError: null });
    tokenInput.value = "";
    flash("✔ 已保存，正在连接本地中继…");
  });

  $("clearBtn").addEventListener("click", async () => {
    await chrome.storage.local.remove(["token", "tokenSource", "lastAuthError"]);
    flash("已清除令牌");
  });

  // 重新自动配对：丢弃当前（可能是手动的）令牌，向本地 Native Messaging 宿主重新获取
  $("repairBtn").addEventListener("click", async () => {
    flash("正在向本地宿主获取令牌…");
    const res = await chrome.runtime.sendMessage({ type: "repair" });
    if (res && res.ok) flash("✔ 已自动配对，正在连接本地中继…");
    else flash("自动配对失败：请先运行 bridge_setup（Polaris 里说「设置浏览器扩展」）", true);
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
    $("tokenSource").textContent = !token ? "无" : state.tokenSource === "auto" ? "自动配对" : "手动令牌";

    const el = $("connState");
    const hint = $("connHint");
    const errKind = state.lastAuthError && state.lastAuthError.kind;
    if (errKind === "relay_outdated") {
      el.className = "state bad";
      el.textContent = "中继需要更新";
      hint.textContent = "本地中继版本过旧，不支持新握手协议。请更新 browser-use / social 插件并重启 Polaris。";
    } else if (errKind === "relay_untrusted") {
      el.className = "state bad";
      el.textContent = "中继身份校验失败";
      hint.textContent = "对端未能证明自己持有令牌（令牌不一致，或该端口上不是 Polaris 中继）。可点「重新自动配对」。";
    } else if (!token) {
      el.className = "state bad";
      el.textContent = "未配对";
      hint.textContent = state.pairError
        ? "自动配对不可用：" + state.pairError + "。请在 Polaris 里说「设置浏览器扩展」（运行 bridge_setup），或在下方手动粘贴令牌。"
        : "正在尝试自动配对；也可在下方手动粘贴令牌。";
    } else if (conns.length > 0) {
      el.className = "state ok";
      el.textContent = "已连接";
      hint.textContent = "";
    } else if (state.lastAuthError) {
      el.className = "state bad";
      el.textContent = "令牌被拒绝";
      hint.textContent = "中继拒绝了当前令牌。自动配对的扩展会自动重取；手动令牌请点「重新自动配对」。";
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
