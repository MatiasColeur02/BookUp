from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    cors_origins: list[str] = ["http://localhost:5173"]

    # Quién emite los tokens (`COGNITO_ROADMAP.md` §4). `local`: la API misma, con
    # `POST /auth/login` y HS256 (desarrollo y tests, sin AWS). `cognito`: el User Pool, y la
    # API solo valida el access token contra su JWKS.
    auth_mode: Literal["local", "cognito"] = "local"
    # Solo con `auth_mode=cognito`. El issuer y la URL del JWKS se derivan de estos (ver las
    # properties de abajo): una variable menos que puede quedar desalineada.
    cognito_region: str = "us-east-1"
    cognito_user_pool_id: str = ""
    cognito_app_client_id: str = ""

    # Solo con `auth_mode=local`. Default only good enough for local development:
    # override JWT_SECRET in every deployed environment.
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # Cache de lecturas (ElastiCache for Redis en AWS). Vacío = cache apagado: la API
    # funciona igual, solo que cada lectura va a la base. Así corren los tests.
    redis_url: str = ""
    # Corto a propósito: si Redis no contesta, preferimos ir a la base antes que
    # bloquear el request. Ver el breaker en `app/cache.py`.
    redis_timeout_seconds: float = 0.5

    # Rate limiting de los endpoints públicos (`app/ratelimit.py`), sobre el mismo
    # Redis que el cache. Sin `redis_url` queda apagado, igual que el cache. Un límite
    # en 0 apaga ese contador puntual.
    rate_limit_window_seconds: int = 300
    rate_limit_login_per_ip: int = 20
    rate_limit_login_per_email: int = 10
    rate_limit_signup_per_ip: int = 5

    # Techo del cuerpo de un request (`app/main.py`). El único archivo grande que
    # maneja la API son las portadas, y esas van directo a S3 sin pasar por acá: lo que
    # entra por este camino es JSON, y 1 MB es holgado para el más grande.
    max_request_bytes: int = 1024 * 1024

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

    # DynamoDB: la fuente de verdad de todo (`app/persistence/`). Sin `dynamo_table` no hay
    # tabla a la que conectarse y `get_dynamo()` falla con un mensaje claro.
    dynamo_table: str = ""
    # Vacío = DynamoDB real (AWS), igual que `s3_endpoint_url`. En local, DynamoDB Local.
    dynamo_endpoint_url: str = ""
    aws_region: str = "us-east-1"

    # Índice de búsqueda del catálogo (OpenSearch), que sirve `GET /books`, `/books/search` y
    # `/books/cities`. Vacío = apagado: esos tres endpoints responden 503 y el resto de la
    # API anda igual (`app/persistence/search.py`).
    opensearch_url: str = ""
    opensearch_index: str = "bookup-books"
    # Corto a propósito, como el de Redis: un OpenSearch lento tiene que degradar la búsqueda
    # a un 503 rápido, no colgar los workers de la API.
    opensearch_timeout_seconds: float = 3.0

    # Vacías en AWS: ahí las credenciales salen del rol de la tarea (ECS) o de la
    # función (Lambda), que es la cadena default de boto3.
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    # Lambda sí define las tres en el entorno (credenciales temporales del rol): sin el token,
    # pasar solo la key y el secreto da `UnrecognizedClientException`.
    aws_session_token: str = ""

    # `hide_input_in_errors`: un error de validación no imprime el resto de la config, que
    # trae secretos (`JWT_SECRET`, las credenciales de AWS) y terminaría en los logs.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    @model_validator(mode="after")
    def _check_cognito(self) -> "Settings":
        # Mejor no arrancar que rechazar cada request con un 401 sin explicación.
        if self.auth_mode == "cognito":
            missing = [
                name.upper()
                for name in ("cognito_user_pool_id", "cognito_app_client_id")
                if not getattr(self, name)
            ]
            if missing:
                raise ValueError(f"AUTH_MODE=cognito requires {', '.join(missing)}")
        return self

    @property
    def cognito_issuer(self) -> str:
        return f"https://cognito-idp.{self.cognito_region}.amazonaws.com/{self.cognito_user_pool_id}"

    @property
    def cognito_jwks_url(self) -> str:
        return f"{self.cognito_issuer}/.well-known/jwks.json"


settings = Settings()
