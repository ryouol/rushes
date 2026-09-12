from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

GEMINI_MODEL = "gemini-3.1-pro-preview"


def supported_gemini_model(model: str) -> str:
    if model not in {GEMINI_MODEL, "gemini-3.6-flash"}:
        raise ValueError(
            f"This analyzer supports {GEMINI_MODEL} with bounded output and low thinking"
        )
    return model


def gemini_thinking_level(model: str) -> str:
    return "low" if supported_gemini_model(model) == GEMINI_MODEL else "minimal"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RUSHES_", env_file=".env", extra="ignore", hide_input_in_errors=True
    )

    database_url: SecretStr
    admin_database_url: SecretStr | None = None
    secret: SecretStr = Field(min_length=32)
    storage_root: Path = Path(".local/storage")
    output_root: Path = Path(".local/exports")
    source_roots: list[Path] = []
    origin: str = "http://localhost:3741"
    contact_email: str = ""
    contact_phone: str = ""
    contact_address: str = ""
    legal_entity: str = ""
    ga_measurement_id: str = ""
    google_client_id: str = Field(default="", max_length=256)
    google_client_secret: SecretStr | None = None
    client_ip_header: Literal["true-client-ip", "x-rushes-ingress-client-ip"] | None = None
    temporal_address: str = "127.0.0.1:7233"
    host_workflow_service: bool = False
    temporal_database_url: SecretStr | None = None
    temporal_visibility_database_url: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    gemini_model: str = GEMINI_MODEL
    transcription_model: str = "tiny"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    compute_backend: Literal["local", "modal"] = "local"
    modal_environment: str = Field(default="rushes-production", pattern=r"^[a-z0-9-]{1,64}$")
    provider_monthly_allowance_microusd: int | None = Field(default=None, ge=0)
    min_free_bytes: int = Field(default=2 * 1024**3, ge=0)
    max_upload_bytes: int = Field(default=20 * 1024**3, gt=0)
    upload_timeout_seconds: int = Field(default=7200, ge=1, le=86400)
    max_source_seconds: int = Field(default=24 * 3600, gt=0)
    media_threads: int = Field(default=2, ge=1, le=16)
    local_credits: int = Field(default=600, ge=0)
    max_analysis_credits: int = Field(default=120, ge=1)
    credits_per_minute: int = Field(default=1, ge=1)
    analysis_window_seconds: int = Field(default=20, ge=10, le=120)

    _supported_model = field_validator("gemini_model")(supported_gemini_model)

    @property
    def public_web_config(self) -> dict[str, str]:
        return {
            name: getattr(self, name)
            for name in (
                "origin",
                "contact_email",
                "contact_phone",
                "contact_address",
                "legal_entity",
                "ga_measurement_id",
            )
        }

    @property
    def google_configured(self) -> bool:
        return bool(
            self.google_client_id
            and self.google_client_secret
            and self.google_client_secret.get_secret_value()
        )

    @field_validator("origin")
    @classmethod
    def application_origin(cls, value: str) -> str:
        url = AnyHttpUrl(value)
        if (
            url.username
            or url.password
            or url.path not in {None, "/"}
            or url.query is not None
            or url.fragment is not None
        ):
            raise ValueError(
                "RUSHES_ORIGIN must be an origin without credentials, path, query or fragment"
            )
        if url.scheme != "https" and url.host not in {"localhost", "127.0.0.1"}:
            raise ValueError("Public RUSHES_ORIGIN must use HTTPS; HTTP is limited to loopback")
        return str(url).removesuffix("/")

    def require_admin_database_url(self) -> SecretStr:
        if self.admin_database_url is None:
            raise ValueError("Migration commands require RUSHES_ADMIN_DATABASE_URL")
        return self.admin_database_url

    @field_validator("storage_root", "output_root")
    @classmethod
    def absolute_path(cls, path: Path) -> Path:
        return path.expanduser().resolve()

    @field_validator("source_roots")
    @classmethod
    def explicit_source_roots(cls, roots: list[Path]) -> list[Path]:
        if any(not root.is_absolute() for root in roots):
            raise ValueError("Source roots must be explicit absolute paths")
        return [root.resolve() for root in roots]

    @model_validator(mode="after")
    def distinct_roots(self):
        if self.compute_backend == "modal" and (
            self.embedding_model != "BAAI/bge-small-en-v1.5" or self.transcription_model != "tiny"
        ):
            raise ValueError(
                "Modal compute currently supports tiny speech and BAAI/bge-small-en-v1.5 embeddings"
            )
        roots = [self.storage_root, self.output_root, *self.source_roots]
        for i, left in enumerate(roots):
            for right in roots[i + 1 :]:
                if left.is_relative_to(right) or right.is_relative_to(left):
                    raise ValueError("Storage, output, and source roots must not overlap")
        return self


@lru_cache
def settings() -> Settings:
    return Settings()
