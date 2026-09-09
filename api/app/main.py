from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import cache, storage
from .config import settings
from .controllers import (
    auth_controller,
    author_controller,
    catalog_controller,
    genre_controller,
    library_controller,
    physical_book_controller,
    reservation_controller,
    user_controller,
)
from .services.errors import ConflictError, ForbiddenError, NotFoundError, UnauthorizedError

app = FastAPI(title="BookUp API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def limit_request_size(request: Request, call_next):
    """Rechaza con 413 un cuerpo más grande que `MAX_REQUEST_BYTES`.

    Ni FastAPI ni uvicorn traen un tope propio, así que sin esto un POST de 1 GB se
    bufferea entero en memoria antes de que Pydantic pueda rechazarlo por longitud: el
    proceso se queda sin RAM validando algo que igual iba a dar 422.

    Se mira el `Content-Length` y no el cuerpo: cortar antes de leerlo es justamente el
    punto. Un cliente que no manda el header (`Transfer-Encoding: chunked`) esquiva este
    control; el tope duro de ese caso lo pone el proxy de adelante (API Gateway corta en
    10 MB, y el ALB tiene su propio límite).
    """
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > settings.max_request_bytes:
        return JSONResponse(
            status_code=413,
            content={
                "detail": (
                    f"El cuerpo del request no puede superar "
                    f"{settings.max_request_bytes // 1024} KB."
                )
            },
        )
    return await call_next(request)


@app.exception_handler(NotFoundError)
def handle_not_found(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ConflictError)
def handle_conflict(request: Request, exc: ConflictError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(UnauthorizedError)
def handle_unauthorized(request: Request, exc: UnauthorizedError) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={"detail": str(exc)},
        headers={"WWW-Authenticate": "Bearer"},
    )


@app.exception_handler(ForbiddenError)
def handle_forbidden(request: Request, exc: ForbiddenError) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": str(exc)})


app.include_router(auth_controller.router)
app.include_router(catalog_controller.router)
app.include_router(author_controller.router)
app.include_router(genre_controller.router)
app.include_router(physical_book_controller.router)
app.include_router(library_controller.router)
app.include_router(reservation_controller.router)
app.include_router(user_controller.router)


@app.get("/health")
def health():
    # `cache` y `storage` son informativos: la API sirve todo igual con Redis caído o
    # sin bucket, así que un `down` acá no baja el status general ni saca la instancia
    # del target group.
    return {"status": "ok", "cache": cache.health(), "storage": storage.health()}
