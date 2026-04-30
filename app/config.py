from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    WHATSAPP_TOKEN: str
    WHATSAPP_VERIFY_TOKEN: str = "myverifytoken2026"
    ANTHROPIC_API_KEY: str
    DATABASE_URL: str
    REDIS_URL: str = "redis://redis:6379"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
