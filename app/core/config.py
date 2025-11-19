from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str

    # If DEV and you hit SSL cert issues on Windows, set DB_SSL_VERIFY=false in .env
    DB_SSL_VERIFY: bool = True

    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    SUPER_ADMIN_EMAIL: str | None = None
    SUPER_ADMIN_PASSWORD: str | None = None
    SUPER_ADMIN_NAME: str | None = "Super Admin"

    ENV: str = "dev"  # "dev" or "prod"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
