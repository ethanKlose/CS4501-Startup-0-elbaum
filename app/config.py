import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Read lazily from env so tests can override before create_app()."""

    @property
    def production(self) -> bool:
        return os.environ.get("APP_ENV", "development").lower() == "production"

    def validate(self):
        if self.production and (self.secret_key in {"dev-insecure-secret", "change-me-in-prod"} or len(self.secret_key) < 32):
            raise RuntimeError("Production requires a unique SECRET_KEY of at least 32 characters.")
        if self.production and not os.environ.get("PUBLIC_BASE_URL", "").startswith("https://"):
            raise RuntimeError("Production requires an HTTPS PUBLIC_BASE_URL.")

    @property
    def timezone(self) -> str:
        return os.environ.get("TIMEZONE", "America/New_York")

    @property
    def secret_key(self) -> str:
        return os.environ.get("SECRET_KEY", "dev-insecure-secret")

    @property
    def database_url(self) -> str:
        return os.environ.get("DATABASE_URL", "sqlite:///./platejoy.db")

    @property
    def openai_api_key(self) -> str:
        return os.environ.get("OPENAI_API_KEY", "")

    @property
    def openai_model(self) -> str:
        return os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    @property
    def anthropic_api_key(self) -> str:
        return os.environ.get("ANTHROPIC_API_KEY", "")

    @property
    def anthropic_model(self) -> str:
        return os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")


settings = Settings()
