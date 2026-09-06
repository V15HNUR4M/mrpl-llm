from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "MRPL AI Workbench"
    API_V1_STR: str = "/api/v1"
    
    # Security
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 days
    BCRYPT_ROUNDS: int = 12
    
    # Database
    SQLITE_URL: str = "sqlite+aiosqlite:///./data/mrpl.db"
    
    # Model Gateway Configuration
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    DEFAULT_CHAT_MODEL: str = "qwen2.5:latest"
    DEFAULT_EMBEDDING_MODEL: str = "nomic-embed-text"
    
    # Admin User for init
    FIRST_SUPERUSER: str = "admin"
    FIRST_SUPERUSER_PASSWORD: str = "admin123"

    # RAG Settings
    UPLOAD_DIR: str = "./data/uploads"
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10MB default
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50
    VECTOR_DB_PATH: str = "./data/chroma"
    ATTACHMENT_DIR: str = "./data/attachments"

    class Config:
        case_sensitive = True

settings = Settings()
