from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Core
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    SESSION_SECRET: str = "change-me"

    # Admin login (voor /admin/login)
    ADMIN_USER: str = "admin"
    ADMIN_PASS: str = "change-me"

    # Simple token auth (bijv. exports / simpele admin acties)
    ADMIN_TOKEN: str = "change-me"

    # Paths (in container)
    TENANTS_DIR: str = "/app/tenants"
    TENANT_ASSETS_DIR: str = "/app/tenant-assets"
    UPLOAD_DIR: str = "/app/uploads"

    # DB/Redis (docker compose service-namen)
    DATABASE_URL: str = "postgresql+psycopg://kluspilot:kluspilot@db:5432/kluspilot"
    REDIS_URL: str = "redis://redis:6379/0"

    # SMTP (optional)
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASS: str = ""
    NOTIFY_FROM: str = ""


settings = Settings()