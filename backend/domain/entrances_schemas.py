from typing import Annotated, Any, Optional

from pydantic import BaseModel, ConfigDict, FiniteFloat, StringConstraints


class Inspect(BaseModel):
    # 允许额外字段（reason / idempotency_key / base_version 等），避免命名差异导致 422。
    model_config = ConfigDict(extra='allow')
    entrance: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
    ramp: bool
    reason: Optional[str] = None
    idempotency_key: Optional[str] = None


class CloseEntrance(BaseModel):
    model_config = ConfigDict(extra='allow')
    entrance: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=160)]] = None
    code: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=160)]] = None
    entrance_code: Optional[str] = None
    reason: Optional[str] = None
    edition: Optional[str] = None
    new_edition: Optional[str] = None
    idempotency_key: Optional[str] = None
