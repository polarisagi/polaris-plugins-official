"""
computer_batch: 在单次 MCP 调用中顺序执行多个动作，减少 round-trip 延迟。
"""


def handle_computer_batch(args):
    """
    批量顺序执行多个 computer 动作。

    参数:
      actions: list[dict]，每个 dict 格式与单次 computer 调用的 arguments 完全相同，
               必须包含 "action" 字段。
      stop_on_error: bool，默认 True，某个动作失败时停止后续。

    示例:
      {
        "action": "computer_batch",
        "actions": [
          {"action": "left_click", "coordinate": [500, 300]},
          {"action": "wait", "duration_ms": 500},
          {"action": "type", "text": "hello world"},
          {"action": "key", "text": "enter"}
        ]
      }
    """
    # 延迟导入避免循环依赖
    import sys
    import os

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from main import handle_computer

    actions = args.get("actions", [])
    stop_on_error = bool(args.get("stop_on_error", True))

    if not isinstance(actions, list) or not actions:
        raise Exception("computer_batch requires non-empty 'actions' list")

    results = []
    for i, action_args in enumerate(actions):
        if not isinstance(action_args, dict) or "action" not in action_args:
            results.append(f"[{i}] SKIP: invalid action dict (missing 'action' field)")
            if stop_on_error:
                break
            continue
        try:
            result = handle_computer(action_args)
            summary = next(
                (r.get("text", "ok") for r in result if r.get("type") == "text"), "ok"
            )
            results.append(f"[{i}] {action_args['action']}: {summary[:100]}")
        except Exception as e:
            results.append(f"[{i}] {action_args['action']}: ERROR — {e}")
            if stop_on_error:
                break

    return [{"type": "text", "text": "\n".join(results)}]
