"""FastAPI application."""

from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse

from . import __version__, model_jobs  # noqa: F401  (registers job handlers)
from .config import get_settings
from .errors import install_error_handlers
from .jobs import Worker
from .routes import analytics, audit_logs, auth, datasets, indicators, models, users

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    worker = Worker() if get_settings().run_worker else None
    if worker:
        worker.start()
    yield
    if worker:
        worker.stop()


def create_app() -> FastAPI:
    get_settings()  # fail fast on invalid configuration
    app = FastAPI(
        lifespan=lifespan,
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
    for module in (auth, users, audit_logs, analytics, datasets, indicators, models):
        api.include_router(module.router)

    @api.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    app.include_router(api)
    return app


app = create_app()
