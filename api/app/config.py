from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://bookup:bookup@localhost:5432/bookup"
    cors_origins: list[str] = ["http://localhost:5173"]

    # Default only good enough for local development: override JWT_SECRET in
    # every deployed environment.
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
