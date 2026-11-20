"""Uniform API errors.

Every error response is ``{"code": str, "message": str, "detail": ...}``. The
``code`` is stable and the web client translates it; ``message`` is an English
fallback for API consumers.
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, detail: Any = None):
        super().__init__(message)
        self.status, self.code, self.message, self.detail = status, code, message, detail


def _body(code: str, message: str, detail: Any = None) -> dict[str, Any]:
    return {"code": code, "message": message, "detail": detail}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(_body(exc.code, exc.message, exc.detail), status_code=exc.status)

    from .analytics.binning import BinningError
    from .data.store import DataError
    from .rules.engine import RuleError

    @app.exception_handler(DataError)
    @app.exception_handler(BinningError)
    async def _data_error(_: Request, exc: DataError | BinningError) -> JSONResponse:
        return JSONResponse(jsonable_encoder(_body(exc.code, str(exc), exc.detail or None)), status_code=400)

    # A strategy that can't run as configured (missing watchlist, model not online): 422, the same
    # status the decision API returns, so backtests, the console and live calls agree.
    @app.exception_handler(RuleError)
    async def _rule_error(_: Request, exc: RuleError) -> JSONResponse:
        return JSONResponse(jsonable_encoder(_body(exc.code, str(exc), exc.detail or None)), status_code=422)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"field": ".".join(str(p) for p in e["loc"][1:]), "type": e["type"], "msg": e["msg"]}
            for e in exc.errors()
        ]
        return JSONResponse(
            jsonable_encoder(_body("validation_error", "Invalid request", errors)),
            status_code=422,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {401: "unauthenticated", 403: "forbidden", 404: "not_found"}.get(exc.status_code, "http_error")
        return JSONResponse(_body(code, str(exc.detail)), status_code=exc.status_code)
