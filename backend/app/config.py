from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "HargaPas API"
    environment: str = "development"
    database_url: str = "sqlite:///./data/hargapas.db"
    cors_origins: str = "http://localhost:3000"
    internal_job_token: str = ""
    jina_reader_base_url: str = "https://r.jina.ai/http://"
    facebook_cookie: str = ""
    shopee_cookie: str = ""
    scrape_timeout_seconds: int = 30
    scrape_queries: str = "RTX 3060,RTX 4060,Core i5 laptop,Ryzen 5 laptop"
    stale_after_hours: int = 72
    tokopedia_pages: int = 2
    tokopedia_query_variants: int = 5
    tokopedia_request_delay_seconds: float = 3.5
    tokopedia_max_records: int = 500

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def query_list(self) -> list[str]:
        return [query.strip() for query in self.scrape_queries.split(",") if query.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
