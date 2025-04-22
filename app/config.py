from pathlib import Path
from pydantic_settings import BaseSettings


class Config(BaseSettings):
    db_url: str
    data_dir: Path = 'data'
    debug: bool = False
    
    api_id: int
    api_hash: str
    bot_token: str
    admin_group_id: int

    host: str = '127.0.0.1'
    port: int = 8000
    external_url: str


config = Config(_env_file='.env')
SESSION_FILE = config.data_dir / 'bot.session'
IMAGES_DIR = config.data_dir / 'images'

__all__ = ['config', 'SESSION_FILE', 'IMAGES_DIR']
