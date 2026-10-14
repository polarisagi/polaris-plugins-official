"""采集配方 Pydantic 模型定义。

为何定义为严格校验模型：
1. 站点配方是定义采集逻辑的核心契约，设置 extra='forbid' 避免拼写错误或未知键隐蔽失效；
2. 明确区分 XHR 拦截提取与 CSS DOM 提取，支持多级回退；
3. 统一站点限速与风控特征（block_signals）定义。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..ratelimit import Limits


class LoginCheck(BaseModel):
    """站点登录态探测配置。"""

    model_config = ConfigDict(extra="forbid")
    url: str = Field(description="验证登录态的目标页面 URL")
    logged_in_selector: str = Field(description="已登录时必出现的 DOM 元素选择器")


class SiteSpec(BaseModel):
    """站点基本信息。"""

    model_config = ConfigDict(extra="forbid")
    id: str = Field(description="站点唯一标识，如 zhihu、x")
    name: str = Field(description="站点展示名称")
    base_url: str = Field(description="站点基础域名 URL")
    login_check: LoginCheck | None = Field(default=None, description="登录态校验配置")


class BlockSignals(BaseModel):
    """目标站点的风控或验证码特征信号。"""

    model_config = ConfigDict(extra="forbid")
    status: list[int] = Field(
        default_factory=list, description="命中即代表被风控的 HTTP 状态码"
    )
    url_contains: list[str] = Field(
        default_factory=list, description="风控重定向或验证码页面 URL 特征片段"
    )
    text_contains: list[str] = Field(
        default_factory=list, description="风控页面包含的关键提示文案"
    )


class ScrollSpec(BaseModel):
    """滚动行为规范。"""

    model_config = ConfigDict(extra="forbid")
    direction: Literal["down", "up"] = "down"
    times: int = 1


class Step(BaseModel):
    """动作执行的单一原子步骤。"""

    model_config = ConfigDict(extra="forbid")
    goto: str | None = None
    wait_for: str | None = None
    timeout_s: float = 10.0
    scroll: ScrollSpec | None = None
    click: str | None = None
    sleep: tuple[float, float] | None = None


class ParamSpec(BaseModel):
    """动作支持的参数规格。"""

    model_config = ConfigDict(extra="forbid")
    type: Literal["string", "number", "boolean"] = "string"
    description: str = ""
    default: Any = None
    required: bool = False


class XhrExtract(BaseModel):
    """基于网络拦截（XHR/Fetch）的 JSON 提取规则。"""

    model_config = ConfigDict(extra="forbid")
    method: Literal["xhr"] = "xhr"
    url_glob: str = Field(description="匹配目标接口的 URL 通配模式")
    items: str = Field(description="响应 JSON 中列表数据的点路径，如 data.items")
    fields: dict[str, str] = Field(description="每个条目内部字段的点路径映射")


class CssExtract(BaseModel):
    """基于页面 DOM 的 CSS 选择器提取规则。"""

    model_config = ConfigDict(extra="forbid")
    method: Literal["css"] = "css"
    container: str = Field(description="条目容器的 CSS 选择器")
    fields: dict[str, str] = Field(description="字段提取规则，支持 css 或 css@attr")


class Action(BaseModel):
    """采集动作（如 hot、search、timeline）。"""

    model_config = ConfigDict(extra="forbid")
    description: str = ""
    params: dict[str, ParamSpec] = Field(default_factory=dict)
    steps: list[Step] = Field(default_factory=list)
    extract: XhrExtract | CssExtract
    extract_fallback: CssExtract | None = None


class Recipe(BaseModel):
    """完整站点配方规范。"""

    model_config = ConfigDict(extra="forbid")
    site: SiteSpec
    limits: Limits
    block_signals: BlockSignals = Field(default_factory=BlockSignals)
    actions: dict[str, Action]
    status: Literal["beta", "stable"] = "beta"
