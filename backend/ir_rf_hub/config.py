"""Runtime configuration, sourced from environment variables set by the
s6-overlay run script (which in turn reads them from bashio/config.yaml
options). Falls back to sane local-dev defaults so the backend can be run
directly with `uvicorn ir_rf_hub.main:app` outside of a container.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="IR_RF_HUB_")

    log_level: str = "info"
    data_dir: Path = Path("./data")

    @property
    def db_path(self) -> Path:
        return self.data_dir / "ir_rf_hub.db"

    @property
    def database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.db_path}"

    @property
    def secret_key_path(self) -> Path:
        return self.data_dir / "secret.key"


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
