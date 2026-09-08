from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://bookup:bookup@localhost:5432/bookup"
    cors_origins: list[str] = ["http://localhost:5173"]

    # Default only good enough for local development: override JWT_SECRET in
    # every deployed environment.
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # Cache de lecturas (ElastiCache for Redis en AWS). Vacío = cache apagado: la API
    # funciona igual, solo que cada lectura va a la base. Así corren los tests.
    redis_url: str = ""
    # Corto a propósito: si Redis no contesta, preferimos ir a la base antes que
    # bloquear el request. Ver el breaker en `app/cache.py`.
    redis_timeout_seconds: float = 0.5

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
