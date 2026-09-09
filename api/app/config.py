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

    # Portadas de libros en almacenamiento de objetos (S3 en AWS, MinIO en local).
    # Sin `s3_bucket` la feature queda apagada: los endpoints de portada dan 503 y el
    # resto de la API anda igual. Así corren los tests. Ver `app/storage.py`.
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    # Endpoint interno (MinIO/LocalStack). Vacío = S3 real.
    s3_endpoint_url: str = ""
    # El endpoint tal como lo ve el browser: SigV4 firma el Host, así que una URL firmada
    # contra el nombre de servicio de Docker no funcionaría fuera del compose.
    s3_public_endpoint_url: str = ""
    # CDN delante del bucket (CloudFront). Si está, las lecturas salen por acá.
    s3_public_base_url: str = ""
    s3_cover_prefix: str = "covers"
    s3_presign_expire_seconds: int = 900
    # Techo del archivo de portada. Se valida al firmar y lo repite el frontend.
    cover_max_bytes: int = 5 * 1024 * 1024

    # Vacías en AWS: ahí las credenciales salen del rol de la tarea (ECS) o de la
    # función (Lambda), que es la cadena default de boto3.
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
