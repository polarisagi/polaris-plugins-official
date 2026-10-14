"""Polaris Browser Bridge 中继服务与 CDP 协议路由单测。

为何需要该模块：
1. 验证 BridgeRelay 的安全访问控制（Origin 校验与配对令牌鉴权）；
2. 验证 CDP 双向协议转换（Target.setAutoAttach、pw-tab-1 sessionId 剥离、事件分发与 detached 处理）；
3. 验证 HTTP /json/version 端点符合 Playwright / Chrome 标准。
"""

from __future__ import annotations

import asyncio
import http.client
import json
from typing import Any

import pytest
import websockets
from src.bridge_const import EXTENSION_ID
from src.bridge_relay import BridgeRelay
from websockets.asyncio.client import connect as ws_connect


@pytest.fixture
async def relay():
    """启动一个使用测试令牌的 BridgeRelay 实例。"""
    test_token = "0123456789abcdef0123456789abcdef"
    r = BridgeRelay(token=test_token)
    await r.start()
    yield r
    await r.close()


@pytest.mark.asyncio
async def test_relay_origin_check(relay: BridgeRelay):
    """测试非法 Origin 被 403 拒绝，正确 Origin 允许握手。"""
    # 1. 错误的 Origin
    bad_headers = {"Origin": "https://malicious.site"}
    with pytest.raises(Exception) as excinfo:
        await ws_connect(
            f"ws://127.0.0.1:{relay.ext_port}/bridge",
            additional_headers=bad_headers,
        )
    assert "403" in str(excinfo.value) or "Forbidden" in str(excinfo.value)

    # 2. 正确的 Origin 但路径错误
    good_origin = f"chrome-extension://{EXTENSION_ID}"
    with pytest.raises(Exception) as excinfo:
        await ws_connect(
            f"ws://127.0.0.1:{relay.ext_port}/wrong_path",
            additional_headers={"Origin": good_origin},
        )
    assert "404" in str(excinfo.value) or "Not Found" in str(excinfo.value)


@pytest.mark.asyncio
async def test_relay_token_auth(relay: BridgeRelay):
    """测试配对令牌错误时关闭连接 (4401)，正确时成功握手。"""
    good_origin = f"chrome-extension://{EXTENSION_ID}"

    # 1. 错误令牌
    async with ws_connect(
        f"ws://127.0.0.1:{relay.ext_port}/bridge",
        additional_headers={"Origin": good_origin},
    ) as ws:
        await ws.send(
            json.dumps(
                {
                    "type": "hello",
                    "token": "wrong_token",
                    "ext_version": "1.0.0",
                    "ua": "TestUA/1.0",
                }
            )
        )
        with pytest.raises(websockets.exceptions.ConnectionClosed) as excinfo:
            await ws.recv()
        assert excinfo.value.rcvd.code == 4401

    assert not relay.has_extension()

    # 2. 正确令牌
    async with ws_connect(
        f"ws://127.0.0.1:{relay.ext_port}/bridge",
        additional_headers={"Origin": good_origin},
    ) as ws:
        await ws.send(
            json.dumps(
                {
                    "type": "hello",
                    "token": relay.token,
                    "ext_version": "1.0.0",
                    "ua": "TestUA/1.0",
                }
            )
        )
        resp_raw = await ws.recv()
        resp = json.loads(resp_raw)
        assert resp.get("type") == "hello_ok"
        assert resp.get("client") == "browser_use"
        assert relay.has_extension()


@pytest.mark.asyncio
async def test_relay_json_version(relay: BridgeRelay):
    """测试 /json/version HTTP 响应符合 Chrome CDP 标准。"""

    def fetch_version() -> tuple[int, dict[str, str], dict[str, Any]]:
        conn = http.client.HTTPConnection("127.0.0.1", relay.cdp_port, timeout=2.0)
        try:
            conn.request("GET", "/json/version")
            resp = conn.getresponse()
            headers = dict(resp.getheaders())
            data = json.loads(resp.read().decode("utf-8"))
            return resp.status, headers, data
        finally:
            conn.close()

    status, headers, data = await asyncio.to_thread(fetch_version)
    assert status == 200
    assert headers.get("Content-Type") == "application/json"
    assert "Browser" in data
    assert data.get("Protocol-Version") == "1.3"
    assert (
        data.get("webSocketDebuggerUrl")
        == f"ws://127.0.0.1:{relay.cdp_port}{relay.cdp_path}"
    )


async def _handle_mock_ext_msg(ext_ws: Any, msg: dict[str, Any]) -> None:
    """处理假扩展接收到的命令并进行 Mock 应答。"""
    if msg.get("type") == "ping":
        await ext_ws.send(json.dumps({"type": "pong"}))
        return
    req_id = msg.get("id")
    method = msg.get("method")
    params = msg.get("params", {})

    if method == "createTab":
        await ext_ws.send(
            json.dumps(
                {
                    "id": req_id,
                    "result": {
                        "tabId": 888,
                        "targetInfo": {
                            "targetId": "target-888",
                            "type": "page",
                            "title": "New Tab",
                            "url": params.get("url", "about:blank"),
                            "attached": True,
                        },
                    },
                }
            )
        )
    elif method == "cdp":
        cdp_method = params.get("method")
        res_data: dict[str, Any] = (
            {"frameId": "frame-1", "loaderId": "loader-1"}
            if cdp_method == "Page.navigate"
            else {"result": {"type": "string", "value": "iframe_ok"}}
        )
        await ext_ws.send(json.dumps({"id": req_id, "result": res_data}))


async def _run_ext_responder(ext_ws: Any) -> None:
    try:
        async for raw in ext_ws:
            await _handle_mock_ext_msg(ext_ws, json.loads(raw))
    except (websockets.exceptions.ConnectionClosed, asyncio.CancelledError):
        pass


async def _verify_auto_attach(pw_ws: Any) -> None:
    """验证 Target.setAutoAttach 与事件。"""
    await pw_ws.send(
        json.dumps(
            {"id": 2, "method": "Target.setAutoAttach", "params": {"autoAttach": True}}
        )
    )
    msg_attached = json.loads(await pw_ws.recv())
    assert msg_attached.get("method") == "Target.attachedToTarget"
    assert msg_attached["params"]["sessionId"] == "pw-tab-1"
    assert msg_attached["params"]["targetInfo"]["targetId"] == "target-888"

    resp2 = json.loads(await pw_ws.recv())
    assert resp2["id"] == 2
    assert resp2["result"] == {}


async def _verify_cdp_routing(pw_ws: Any) -> None:
    """验证命令带 sessionId 转发剥离与子会话转发。"""
    await pw_ws.send(
        json.dumps(
            {
                "id": 3,
                "method": "Page.navigate",
                "params": {"url": "https://example.com"},
                "sessionId": "pw-tab-1",
            }
        )
    )
    resp3 = json.loads(await pw_ws.recv())
    assert resp3["id"] == 3
    assert resp3["sessionId"] == "pw-tab-1"
    assert resp3["result"]["frameId"] == "frame-1"

    await pw_ws.send(
        json.dumps(
            {
                "id": 4,
                "method": "Runtime.evaluate",
                "params": {"expression": "location.href"},
                "sessionId": "sub-frame-session-99",
            }
        )
    )
    resp4 = json.loads(await pw_ws.recv())
    assert resp4["id"] == 4
    assert resp4["sessionId"] == "sub-frame-session-99"
    assert resp4["result"]["result"]["value"] == "iframe_ok"


async def _verify_events_and_detached(
    ext_ws: Any, pw_ws: Any, relay: BridgeRelay
) -> None:
    """验证扩展上报事件与分离通知。"""
    await ext_ws.send(
        json.dumps(
            {
                "type": "cdp_event",
                "method": "Page.loadEventFired",
                "params": {"timestamp": 12345.67},
            }
        )
    )
    ev_msg = json.loads(await pw_ws.recv())
    assert ev_msg.get("method") == "Page.loadEventFired"
    assert ev_msg.get("sessionId") == "pw-tab-1"
    assert ev_msg["params"]["timestamp"] == 12345.67

    await ext_ws.send(json.dumps({"type": "detached"}))
    detach_msg = json.loads(await pw_ws.recv())
    assert detach_msg.get("method") == "Target.detachedFromTarget"
    assert detach_msg["params"]["sessionId"] == "pw-tab-1"
    assert relay.current_tab_id is None


@pytest.mark.asyncio
async def test_relay_cdp_routing_lifecycle(relay: BridgeRelay):
    """测试 CDP 双向协议转换完整生命周期。"""
    good_origin = f"chrome-extension://{EXTENSION_ID}"

    ext_ws = await ws_connect(
        f"ws://127.0.0.1:{relay.ext_port}/bridge",
        additional_headers={"Origin": good_origin},
    )
    await ext_ws.send(
        json.dumps(
            {
                "type": "hello",
                "token": relay.token,
                "ext_version": "1.0.0",
                "ua": "Mozilla/5.0 Chrome/130.0.0.0",
            }
        )
    )
    hello_resp = json.loads(await ext_ws.recv())
    assert hello_resp["type"] == "hello_ok"

    pw_ws = await ws_connect(f"ws://127.0.0.1:{relay.cdp_port}{relay.cdp_path}")
    responder_task = asyncio.create_task(_run_ext_responder(ext_ws))

    try:
        await pw_ws.send(json.dumps({"id": 1, "method": "Browser.getVersion"}))
        resp1 = json.loads(await pw_ws.recv())
        assert resp1["id"] == 1
        assert "Chrome/130" in resp1["result"]["product"]

        await _verify_auto_attach(pw_ws)
        await _verify_cdp_routing(pw_ws)
        await _verify_events_and_detached(ext_ws, pw_ws, relay)

    finally:
        responder_task.cancel()
        await ext_ws.close()
        await pw_ws.close()
