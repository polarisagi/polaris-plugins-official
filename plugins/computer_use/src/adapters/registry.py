"""
Adapter registry — maps app bundle IDs to their adapter classes.

To add a new app-specific adapter:
  1. Create adapters/<category>/<appname>.py with a class extending BaseAdapter
  2. Import it here and add its bundle ID to _REGISTRY

Apps NOT listed here automatically use BaseAdapter (generic behaviour).
"""
from adapters.base import BaseAdapter
from adapters.chat.wechat import WeChatAdapter

_REGISTRY: dict[str, type[BaseAdapter]] = {
    "com.tencent.xinWeChat": WeChatAdapter,
    "com.tencent.qq":        WeChatAdapter,  # QQ has the same dropdown architecture
}


def get_adapter(profile: dict) -> BaseAdapter:
    """Return the appropriate adapter instance for the given app profile."""
    bundle_id = profile.get("bundle_id", "")
    cls = _REGISTRY.get(bundle_id, BaseAdapter)
    return cls()
