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
    # Off in tests (see conftest.py's _isolated_data_dir) -- the updater's
    # refresh() does a real `git clone` against GitHub, which every test
    # spinning up the app's lifespan would otherwise trigger (no meta.json
    # yet in a fresh tmp_path data_dir means _needs_refresh() is always
    # True), making the suite slow, flaky, and dependent on network access
    # it has no business needing.
    disable_remote_database_updater: bool = False
    # Set by the container's run script (IR_RF_HUB_ALEMBIC_INI) -- alembic.ini
    # isn't inside the ir_rf_hub package, so `pip install .` never ships it
    # alongside the installed code (which can end up anywhere, e.g.
    # site-packages/). None here means "not containerized", handled by
    # main.py's fallback.
    alembic_ini: Path | None = None

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
