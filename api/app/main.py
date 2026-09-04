from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .controllers import (
    catalog_controller,
    library_controller,
    reservation_controller,
    user_controller,
)
from .services.errors import ConflictError, NotFoundError

app = FastAPI(title="BookUp API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(NotFoundError)
def handle_not_found(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ConflictError)
def handle_conflict(request: Request, exc: ConflictError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


app.include_router(catalog_controller.router)
app.include_router(library_controller.router)
app.include_router(reservation_controller.router)
app.include_router(user_controller.router)


@app.get("/health")
def health():
    return {"status": "ok"}
