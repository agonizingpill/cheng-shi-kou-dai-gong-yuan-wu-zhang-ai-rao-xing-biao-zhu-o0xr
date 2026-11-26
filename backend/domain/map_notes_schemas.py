from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, FiniteFloat, StringConstraints


class PublishMap(BaseModel):
    # 全部可选且允许额外键：不同命名（detour_code / base_version / idempotency_key…）
    # 由 service 归一化，缺 detour 时给中文 409 而不是框架 422。
    model_config = ConfigDict(extra='allow')
    code: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=160)]] = None
    detour: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=160)]] = None
    edition: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=160)]] = None
