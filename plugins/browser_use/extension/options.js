document.addEventListener("DOMContentLoaded", async () => {
  const tokenInput = document.getElementById("tokenInput");
  const saveBtn = document.getElementById("saveBtn");
  const saveStatus = document.getElementById("saveStatus");
  const connectionsList = document.getElementById("connectionsList");

  // 加载已保存的令牌
  const data = await chrome.storage.local.get(["token", "activeConnections"]);
  if (data.token) {
    tokenInput.value = data.token;
  }
  renderConnections(data.activeConnections || []);

  // 监听存储变动刷新中继状态
  chrome.storage.onChanged.addListener((changes) => {
    if (changes.activeConnections) {
      renderConnections(changes.activeConnections.newValue || []);
    }
  });

  saveBtn.addEventListener("click", async () => {
    const token = tokenInput.value.trim();
    await chrome.storage.local.set({ token });
    saveStatus.textContent = "✔ 配对令牌已保存，扩展正在重新连接本地中继...";
    setTimeout(() => {
      saveStatus.textContent = "";
    }, 4000);
  });

  function renderConnections(list) {
    if (!list || list.length === 0) {
      connectionsList.innerHTML = "<span>当前未检测到活跃的本地中继（请确认 Polaris 或插件服务已启动）。</span>";
      return;
    }

    let html = "<ul>";
    for (const c of list) {
      html += `<li><strong>${c.client}</strong> (端口 <code>127.0.0.1:${c.port}</code>) — 活动标签: ${c.tabs}</li>`;
    }
    html += "</ul>";
    connectionsList.innerHTML = html;
  }
});
