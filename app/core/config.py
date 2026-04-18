import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from pydantic import computed_field, model_validator

class Settings(BaseSettings):
    # ------------------------------------------------------------
    # DATABASE CONFIGURATION
    # ------------------------------------------------------------
    DATABASE_URL: Optional[str] = None
    DATABASE_URL_DEVELOPMENT: Optional[str] = None
    DATABASE_URL_PRODUCTION: Optional[str] = None
    DATABASE_URL_TEST: Optional[str] = None
    DATABASE_URL_LOCAL: Optional[str] = None
    LOCAL_DATABASE_URL: Optional[str] = None
    TEST_DATABASE_URL: Optional[str] = None
    DB_SSL_VERIFY: bool = True
    DB_CA_CERT_PATH: Optional[str] = None
    db_ca_cert_path: Optional[str] = None

    # ------------------------------------------------------------
    # CORE APP SETTINGS
    # ------------------------------------------------------------
    SECRET_KEY: str  # No default! Forces you to provide one.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    
    # Change default to something neutral or remove it
    ENV: str = "production"  # Standard practice: Default to safest mode (Prod)

    @computed_field
    @property
    def DEBUG(self) -> bool:
        # Now it only returns True if you EXPLICITLY set ENV=development in .env
        return self.ENV.lower() == "development"

    @model_validator(mode='after')
    def resolve_database_url(self):
        env = (self.ENV or "development").lower()

        if env in {"development", "dev", "local"}:
            selected = (
                self.DATABASE_URL_DEVELOPMENT
                or self.DATABASE_URL_LOCAL
                or self.LOCAL_DATABASE_URL
                or self.DATABASE_URL
            )
        elif env in {"production", "prod"}:
            selected = self.DATABASE_URL_PRODUCTION or self.DATABASE_URL
        elif env in {"test", "testing"}:
            selected = (
                self.DATABASE_URL_TEST
                or self.TEST_DATABASE_URL
                or self.DATABASE_URL_DEVELOPMENT
                or self.DATABASE_URL
            )
        else:
            selected = self.DATABASE_URL

        if not selected:
            raise ValueError(
                "DATABASE URL is missing. Set DATABASE_URL or an environment-specific URL "
                "(DATABASE_URL_DEVELOPMENT / DATABASE_URL_PRODUCTION / DATABASE_URL_TEST)."
            )

        self.DATABASE_URL = selected

        # Backward compatibility: support legacy lowercase setting name.
        if self.DB_CA_CERT_PATH and not self.db_ca_cert_path:
            self.db_ca_cert_path = self.DB_CA_CERT_PATH
        elif self.db_ca_cert_path and not self.DB_CA_CERT_PATH:
            self.DB_CA_CERT_PATH = self.db_ca_cert_path

        return self

    # ------------------------------------------------------------
    # SECURITY / CAPTCHA (Cloudflare Turnstile)
    # ------------------------------------------------------------
    # 1. We start with None or a placeholder
    TURNSTILE_SECRET_KEY: Optional[str] = None

    # 2. We use a validator to enforce logic based on ENV
    @model_validator(mode='after')
    def configure_turnstile(self):
        # Cloudflare Dummy Secret (Always Passes)
        TEST_SECRET = "1x0000000000000000000000000000000AA"
        
        # LOGIC:
        # If ENV is 'dev', we can default to the Test Secret if no real key is provided.
        if self.ENV.lower() == "development":
            if not self.TURNSTILE_SECRET_KEY:
                print("⚠️ [Config] Using Dummy Turnstile Key for Dev Mode.")
                self.TURNSTILE_SECRET_KEY = TEST_SECRET
        
        # If ENV is 'prod', we MUST have a real key.
        elif self.ENV.lower() == "production":
            if not self.TURNSTILE_SECRET_KEY or self.TURNSTILE_SECRET_KEY == TEST_SECRET:
                raise ValueError(
                    "❌ CRITICAL: You are in PRODUCTION mode but 'TURNSTILE_SECRET_KEY' is missing or set to the dummy key. "
                    "Please add your real Cloudflare Secret Key to .env"
                )
        
        # Debug Print (Moved here to show the FINAL key being used)
        masked_key = self.TURNSTILE_SECRET_KEY[:5] + "..." if self.TURNSTILE_SECRET_KEY else "None"
        print(f"DEBUG: Current ENV={self.ENV}")

        return self

    # ------------------------------------------------------------
    # FIRST ADMIN CONFIGURATION
    # ------------------------------------------------------------
    ADMIN_EMAIL: Optional[str] = None
    ADMIN_PASSWORD: Optional[str] = None
    ADMIN_NAME: Optional[str] = "Admin"
    
    # ------------------------------------------------------------
    # EMAIL (SMTP) SETTINGS
    # ------------------------------------------------------------
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 2525
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    EMAILS_FROM_EMAIL: str = "no-reply@gbu.ac.in"
    EMAILS_FROM_NAME: str = "GBU No Dues"

    # ------------------------------------------------------------
    # REDIS
    # ------------------------------------------------------------
    REDIS_URL: str = "redis://localhost:6379/0"

    # ------------------------------------------------------------
    # DATADOG APM
    # ------------------------------------------------------------
    DD_TRACE_ENABLED: bool = False
    DD_SERVICE: str = "gbu-no-dues-backend"
    DD_ENV: Optional[str] = None
    DD_VERSION: Optional[str] = None

    # ------------------------------------------------------------
    # FRONTEND / CORS CONFIGURATION
    # ------------------------------------------------------------
    FRONTEND_URL: Optional[str] = None
    FRONTEND_REGEX: Optional[str] = None
    # ------------------------------------------------------------
    # EXTERNAL SERVICES
    # ------------------------------------------------------------
    SUPABASE_URL: Optional[str] = None
    SUPABASE_KEY: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False
    )

settings = Settings()