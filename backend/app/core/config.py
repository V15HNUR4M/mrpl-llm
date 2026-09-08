from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator
from typing import Optional, Dict, Any, List

class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=True, extra="ignore")

    PROJECT_NAME: str = "MRPL AI Workbench"
    API_V1_STR: str = "/api/v1"
    
    # Environment mode: development, testing, production
    ENVIRONMENT: str = "development"
    ENABLE_OPENAPI: Optional[bool] = None
    ENABLE_TEST_ENDPOINTS: Optional[bool] = None
    
    # Security
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 days
    BCRYPT_ROUNDS: int = 12
    ENABLE_PUBLIC_REGISTRATION: bool = False
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:80",
        "http://127.0.0.1:80",
    ]
    
    # Database
    SQLITE_URL: str = "sqlite+aiosqlite:///./data/mrpl.db"
    
    # Model Gateway Configuration
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    DEFAULT_CHAT_MODEL: str = "llama3.2:latest"
    DEFAULT_EMBEDDING_MODEL: str = "nomic-embed-text"
    EMBEDDING_PROVIDER: str = "ollama"
    
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

    @model_validator(mode="after")
    def validate_production_configuration(self) -> "Settings":
        env = (self.ENVIRONMENT or "development").lower().strip()
        
        # Determine defaults for OpenAPI and test endpoints if not explicitly provided
        if self.ENABLE_OPENAPI is None:
            self.ENABLE_OPENAPI = (env != "production")
        if self.ENABLE_TEST_ENDPOINTS is None:
            self.ENABLE_TEST_ENDPOINTS = (env != "production")
            
        if env == "production":
            # 1. SECRET_KEY validation
            if not self.SECRET_KEY or len(self.SECRET_KEY.strip()) < 32:
                raise ValueError(
                    "Production configuration error: SECRET_KEY must be a cryptographically secure string "
                    "with a minimum length of 32 characters."
                )
            
            insecure_keys = {
                "test-secret-key-12345",
                "secret",
                "changeme",
                "insecure",
                "admin",
                "password",
                "default-secret-key-do-not-use-in-production"
            }
            if self.SECRET_KEY.strip().lower() in insecure_keys:
                raise ValueError(
                    "Production configuration error: SECRET_KEY is set to an insecure or test default value. "
                    "A secure production key must be provided via the SECRET_KEY environment variable."
                )
            
            # 2. Superuser bootstrap password validation
            insecure_passwords = {"admin123", "password", "admin", "12345678", "secret", "root"}
            if self.FIRST_SUPERUSER_PASSWORD.strip().lower() in insecure_passwords or len(self.FIRST_SUPERUSER_PASSWORD) < 10:
                raise ValueError(
                    "Production configuration error: Insecure FIRST_SUPERUSER_PASSWORD detected. "
                    "Production deployments must provide a strong initial administrator password "
                    "(at least 10 characters, non-default) via FIRST_SUPERUSER_PASSWORD."
                )
                
        return self

    def safe_dict(self) -> Dict[str, Any]:
        """Returns configuration dictionary safe for logging with secret values redacted."""
        data = self.model_dump()
        sensitive_keys = {"SECRET_KEY", "FIRST_SUPERUSER_PASSWORD"}
        for k in sensitive_keys:
            if k in data and data[k]:
                data[k] = "***REDACTED***"
        return data

settings = Settings()

