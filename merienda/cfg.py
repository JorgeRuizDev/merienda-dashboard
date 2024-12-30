from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


class Cfg(BaseSettings):
    tapo_username: str
    tapo_password: str
    tapo_ip: str
    price_per_kw_eur: float = 0.1125
    total_capacity_wh: float = 10_500
    polling_rate_s: float = 0.33
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__, "../../.env").resolve().absolute())
    )


_global_cfg: Cfg | None = None


def get_cfg() -> Cfg:
    global _global_cfg
    if _global_cfg is None:
        _global_cfg = Cfg()  # type: ignore
    return _global_cfg
    return _global_cfg
