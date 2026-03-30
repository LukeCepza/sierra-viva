from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://sierra:sierra@localhost:5432/sierraviva"
    firms_api_key: str = ""
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # FIRMS polling: radius in km around each crag to check for fires
    firms_radius_km: int = 10
    # How many days back to fetch fire data
    firms_days_back: int = 2

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
