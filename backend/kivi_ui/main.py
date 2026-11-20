"""FastAPI application."""

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse

from . import __version__
from .config import get_settings
from .errors import install_error_handlers
from .routes import analytics, audit_logs, auth, users

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def create_app() -> FastAPI:
    get_settings()  # fail fast on invalid configuration
    app = FastAPI(
        title="kivi-ui API",
        version=__version__,
        description="Risk data, indicator, model and strategy management, powered by kivi.",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    install_error_handlers(app)

    @app.middleware("http")
    async def require_ajax_header(request: Request, call_next):
        # Cookie sessions plus a custom header that cross-site forms cannot send.
        if (
            request.method in UNSAFE_METHODS
            and request.url.path.startswith("/api/")
            and "x-requested-with" not in request.headers
        ):
            return JSONResponse(
                {"code": "csrf_header_missing", "message": "Missing X-Requested-With header", "detail": None},
                status_code=403,
            )
        return await call_next(request)

    api = APIRouter(prefix="/api/v1")
    for module in (auth, users, audit_logs, analytics):
        api.include_router(module.router)

    @api.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    app.include_router(api)
    return app


app = create_app()
