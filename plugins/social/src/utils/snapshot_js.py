"""DOM 快照提取的 JavaScript 常量定义。

为何定义为独立模块常量：
1. 注入防御：禁止在运行时动态拼装 JavaScript 字符串，完全使用常量函数体；
2. 参数化传参：所有控制参数（scope、max_items）统一经由 Playwright 的 page.evaluate(JS, arg) 传入。
"""

from __future__ import annotations

# 快照提取脚本：为交互元素打上 data-polaris-ref="e<N>" 属性并输出精简语义文本
SNAPSHOT_JS = """
(arg) => {
    const scope = arg.scope || "viewport";
    const maxItems = arg.max_items || 80;

    const selectors = [
        "a[href]",
        "button",
        "input",
        "textarea",
        "select",
        "[role='button']",
        "[role='link']",
        "[role='menuitem']",
        "[role='tab']",
        "[role='checkbox']",
        "[role='radio']",
        "[role='searchbox']",
        "[tabindex='0']",
        "summary"
    ];

    const elements = Array.from(document.querySelectorAll(selectors.join(",")));
    const viewW = window.innerWidth;
    const viewH = window.innerHeight;

    const visibleElements = [];

    for (const el of elements) {
        const style = window.getComputedStyle(el);
        if (style.display === "none" || style.visibility === "hidden" || style.opacity === "0") {
            continue;
        }

        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) {
            continue;
        }

        if (scope === "viewport") {
            if (rect.bottom < 0 || rect.right < 0 || rect.top > viewH || rect.left > viewW) {
                continue;
            }
        }

        visibleElements.push(el);
    }

    const total = visibleElements.length;
    const slice = visibleElements.slice(0, maxItems);
    const lines = [];

    slice.forEach((el, index) => {
        const refId = "e" + (index + 1);
        el.setAttribute("data-polaris-ref", refId);

        let role = el.getAttribute("role") || el.tagName.toLowerCase();
        if (el.tagName === "INPUT") {
            role = (el.getAttribute("type") || "text") + "_input";
        }

        let text = (el.innerText || "").trim().replace(/\\s+/g, " ");
        if (!text) {
            text = el.getAttribute("aria-label") ||
                   el.getAttribute("placeholder") ||
                   el.getAttribute("title") ||
                   el.getAttribute("value") ||
                   el.getAttribute("alt") || "";
        }
        text = text.trim();
        if (text.length > 60) {
            text = text.substring(0, 57) + "...";
        }

        if (text) {
            lines.push(`${refId} ${role} "${text}"`);
        } else {
            lines.push(`${refId} ${role}`);
        }
    });

    lines.push(`共 ${total} 个，已显示 ${slice.length} 个`);
    return {
        snapshot: lines.join("\\n"),
        total: total,
        displayed: slice.length
    };
}
"""

# 滚动位置探测脚本
SCROLL_INFO_JS = """
() => {
    const scrollY = window.scrollY || document.documentElement.scrollTop;
    const scrollHeight = document.documentElement.scrollHeight;
    const clientHeight = document.documentElement.clientHeight;
    const atBottom = (scrollY + clientHeight) >= (scrollHeight - 10);
    return {
        scroll_y: Math.round(scrollY),
        at_bottom: atBottom
    };
}
"""

# 通用 CSS 结构化提取常量脚本
EXTRACT_JS = """
(arg) => {
    const containerSel = arg.container;
    const fields = arg.fields || {};
    const maxItems = arg.max_items || 50;

    let containers = [];
    try {
        containers = Array.from(document.querySelectorAll(containerSel));
    } catch (e) {
        return { error: "invalid_selector", message: e.message };
    }

    const items = [];
    const limit = Math.min(containers.length, maxItems);

    for (let i = 0; i < limit; i++) {
        const el = containers[i];
        const item = {};

        for (const [key, spec] of Object.entries(fields)) {
            let selector = spec;
            let attr = null;

            if (spec.includes("@")) {
                const parts = spec.split("@");
                selector = parts[0].trim();
                attr = parts[1].trim();
            }

            let target = el;
            if (selector) {
                try {
                    target = el.querySelector(selector);
                } catch (e) {
                    target = null;
                }
            }

            if (!target) {
                item[key] = null;
                continue;
            }

            if (attr) {
                if (attr === "href" || attr === "src") {
                    item[key] = target[attr] || target.getAttribute(attr);
                } else {
                    item[key] = target.getAttribute(attr);
                }
            } else {
                item[key] = (target.innerText || "").trim();
            }
        }
        items.push(item);
    }

    return { items: items, count: items.length };
}
"""
