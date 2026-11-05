"""API 응답 모델의 바탕(ARCHITECTURE 2절 API 층 'pydantic 응답 모델' · TASKS P1-09).

- 라우트마다 지금 응답 모양 그대로의 pydantic 모델을 둬요(키 · 타입 · 상태에 따라 나오는 키는 선택 필드). 라우트는
  `response_model_exclude_unset=True`라 받은 dict에 없던 키는 내보내지 않아요(없던 `null`이 생기지 않음).
- 상태에 따라 나오는 키는 `opt()`(기본값 없음으로 보이고 · 있으면 적은 타입 · `null`이 올 수 있으면 `| None`).
- 숫자 · 글 · 참거짓은 엄격한 타입(`Int` · `Num` · `Str` · `Bool`)이라 값을 바꾸지 않아요(정수가 실수로 · 참이 1로 되지 않음).
  `Num`은 정수와 실수를 그대로 둬요.
- **실행 때는 모르는 키를 남기고(`extra="allow"`) · 시험 때만 엄격하게(`forbid`)**: pytest(`tests/conftest.py`)가 응답 모델
  모듈을 import하기 전에 `forbid_unknown_keys()`를 불러요. 모델은 이 바탕의 설정을 만들어질 때 물려받아요.
- OpenAPI(`types.gen.ts`를 만드는 원본)에는 `additionalProperties`와 필드 제목을 적지 않아요(실행 · 시험 어느 쪽에서 만들어도 같게).
- 돈이 움직이는 라우트(주문 · 매도 · 멈추기 · `MoneyRoute`)는 응답 모양 검사가 실패해도 500으로 바꾸지 않아요: 키 위치만
  기록하고(값은 남기지 않음 · S2) 원래 응답을 그대로 보내요. 일은 이미 끝났으니 화면이 결과를 받아야 해요.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import ResponseValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr
from starlette.requests import Request
from starlette.responses import Response

log = logging.getLogger("quant-mvp")

Int = StrictInt
Num = StrictInt | StrictFloat
Str = StrictStr
Bool = StrictBool

SHAPE_MISMATCH = "api response shape mismatch"  # 기록 글 머리(시험이 이 기록을 찾아요)


def _schema_without_extra(schema: dict[str, Any], cls: type) -> None:
    """OpenAPI 꼴: `additionalProperties`(실행 · 시험 설정에 따라 다름)와 필드마다 붙는 제목(이름을 다시 쓴 것)은 빼요."""
    schema.pop("additionalProperties", None)
    for prop in schema.get("properties", {}).values():
        prop.pop("title", None)


def opt() -> Any:
    """상태에 따라 나오는 키(없으면 응답에 없음 · `exclude_unset`). 있을 때의 타입은 필드에 적은 그대로예요."""
    return Field(default=None)


class ApiModel(BaseModel):
    """모든 응답 모델의 바탕(실행 때 모르는 키는 남김)."""

    model_config = ConfigDict(extra="allow", json_schema_extra=_schema_without_extra)


def forbid_unknown_keys() -> None:
    """시험만: 이 뒤에 만들어지는 응답 모델은 모르는 키를 거절해요(응답 모델 모듈을 import하기 전에 불러요)."""
    ApiModel.model_config["extra"] = "forbid"


class MoneyRoute(APIRoute):
    """돈이 움직이는 라우트: 응답 모양 검사 실패를 500으로 바꾸지 않고 기록한 뒤 원래 응답을 보내요."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()
        path = self.path

        async def guarded(request: Request) -> Response:
            try:
                return await handler(request)
            except ResponseValidationError as exc:
                where = sorted({".".join(str(p) for p in e.get("loc", ())) for e in exc.errors()})[:10]
                log.error("%s %s %s at %s", SHAPE_MISMATCH, request.method, path, where)
                return JSONResponse(jsonable_encoder(exc.body))

        return guarded
