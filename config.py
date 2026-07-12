import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

DEFAULT_LOCAL_DB_PATH = os.path.join(BASE_DIR, "instance", "prescreen.db")
WRITEABLE_DB_PATH = os.path.join("/tmp", "prescreen.db")


def get_database_uri() -> str:
    env_db = os.environ.get("DATABASE_URL")
    if env_db:
        return env_db

    db_dir = os.path.dirname(DEFAULT_LOCAL_DB_PATH)
    if os.access(db_dir, os.W_OK):
        return f"sqlite:///{DEFAULT_LOCAL_DB_PATH}"
    return f"sqlite:////{WRITEABLE_DB_PATH}"


class Config:
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-only-change-me")
    SQLALCHEMY_DATABASE_URI = get_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
    ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "change_this_too")
    MAX_CONTENT_LENGTH = 12 * 1024 * 1024  # 12 MB upload limit for income documents
