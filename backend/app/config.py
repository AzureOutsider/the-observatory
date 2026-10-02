from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Runtime configuration for the local Observatory process."""

    database_url: str
    knowledge_path: Path
    review_path: Path
    tag_overrides_path: Path
    cors_origins: tuple[str, ...]
    request_timeout_seconds: float
    market_request_timeout_seconds: float
    news_cache_ttl_seconds: int
    news_retention_days: int


def load_settings() -> Settings:
    database_url = os.getenv("FINANCE_DATABASE_URL")
    if not database_url:
        default_db_path = Path(__file__).resolve().parents[1] / "data" / "finance.db"
        db_path = Path(os.getenv("FINANCE_DB_PATH", str(default_db_path)))
        database_url = f"sqlite:///{db_path}"

    origins = tuple(
        origin.strip()
        for origin in os.getenv(
            "FINANCE_CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    )
    # Default knowledge/review files live inside the project so a fresh clone works
    # without any personal paths. Point FINANCE_KNOWLEDGE_PATH / FINANCE_REVIEW_PATH
    # at your own files to override them.
    default_data_dir = Path(__file__).resolve().parents[1] / "data"
    return Settings(
        database_url=database_url,
        knowledge_path=Path(
            os.getenv(
                "FINANCE_KNOWLEDGE_PATH",
                str(default_data_dir / "knowledge.md"),
            )
        ),
        review_path=Path(
            os.getenv(
                "FINANCE_REVIEW_PATH",
                str(default_data_dir / "reviews" / "每日复盘.md"),
            )
        ),
        tag_overrides_path=Path(
            os.getenv(
                "FINANCE_TAG_OVERRIDES_PATH",
                str(default_data_dir / "tag_overrides.json"),
            )
        ),
        cors_origins=origins,
        request_timeout_seconds=float(os.getenv("FINANCE_REQUEST_TIMEOUT_SECONDS", "10")),
        market_request_timeout_seconds=float(
            os.getenv("FINANCE_MARKET_REQUEST_TIMEOUT_SECONDS", "4")
        ),
        news_cache_ttl_seconds=int(os.getenv("FINANCE_NEWS_CACHE_TTL_SECONDS", "600")),
        news_retention_days=int(os.getenv("FINANCE_NEWS_RETENTION_DAYS", "7")),
    )


settings = load_settings()
