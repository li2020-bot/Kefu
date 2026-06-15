"""Application configuration via Pydantic Settings with env var fallback."""

import os

try:
    from pydantic_settings import BaseSettings

    class Settings(BaseSettings):
        model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

        # LLM
        llm_api_key: str = ""
        llm_base_url: str = "https://api.minimax.chat/v1"
        llm_model: str = "minimax/MiniMax-M2.7-highspeed"
        llm_model_fast: str = "minimax/MiniMax-M2.7-highspeed"
        embedding_model: str = "BAAI/bge-small-zh-v1.5"
        reranker_model: str = "BAAI/bge-reranker-v2-m3"

        # PostgreSQL
        postgres_host: str = "localhost"
        postgres_port: int = 5432
        postgres_db: str = "kefu"
        postgres_user: str = "kefu"
        postgres_password: str = ""  # Set via POSTGRES_PASSWORD env var

        @property
        def postgres_url(self) -> str:
            return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

        @property
        def postgres_sync_url(self) -> str:
            return f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

        # Redis
        redis_url: str = "redis://localhost:6379/0"

        # OpenSearch
        opensearch_host: str = "localhost"
        opensearch_port: int = 9200

        # MCP
        mcp_crm_url: str = "http://localhost:8001/mcp"
        mcp_order_url: str = "http://localhost:8002/mcp"
        mcp_ticket_url: str = "http://localhost:8003/mcp"

        # Observability
        otel_exporter_otlp_endpoint: str = "http://localhost:4318"
        prometheus_port: int = 9090

        # Security
        secret_key: str = "change-me"
        jwt_algorithm: str = "HS256"
        jwt_expire_minutes: int = 1440

        # Application
        debug: bool = True
        log_level: str = "INFO"
        api_port: int = 8000
        cors_origins: str = "*"

        # RAG
        chunk_size: int = 800
        chunk_overlap: int = 150
        retrieval_top_k: int = 5
        hybrid_fusion_k: int = 60

        # Intent classification
        intent_confidence_threshold: float = 0.50

        # Agent
        max_conversation_turns: int = 50
        handoff_unsatisfied_threshold: int = 2
        handoff_timeout_minutes: int = 30

    settings = Settings()

except ImportError:

    class Settings:
        """Fallback settings from environment variables."""

        def _env(self, key: str, default=None, type_func=None):
            val = os.getenv(key.upper(), default)
            if type_func and val is not None:
                try:
                    return type_func(val)
                except (ValueError, TypeError):
                    return default
            return val

        @property
        def llm_api_key(self): return self._env("LLM_API_KEY", "")
        @property
        def llm_base_url(self): return self._env("LLM_BASE_URL", "")
        @property
        def llm_model(self): return self._env("LLM_MODEL", "openai/gpt-4o")
        @property
        def llm_model_fast(self): return self._env("LLM_MODEL_FAST", "openai/gpt-4o-mini")
        @property
        def embedding_model(self): return self._env("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
        @property
        def reranker_model(self): return self._env("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")

        @property
        def postgres_host(self): return self._env("POSTGRES_HOST", "localhost")
        @property
        def postgres_port(self): return self._env("POSTGRES_PORT", 5432, int)
        @property
        def postgres_db(self): return self._env("POSTGRES_DB", "kefu")
        @property
        def postgres_user(self): return self._env("POSTGRES_USER", "kefu")
        @property
        def postgres_password(self): return self._env("POSTGRES_PASSWORD", "kefu123")

        @property
        def postgres_url(self):
            return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

        @property
        def postgres_sync_url(self):
            return f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

        @property
        def redis_url(self): return self._env("REDIS_URL", "redis://localhost:6379/0")
        @property
        def opensearch_host(self): return self._env("OPENSEARCH_HOST", "localhost")
        @property
        def opensearch_port(self): return self._env("OPENSEARCH_PORT", 9200, int)
        @property
        def mcp_crm_url(self): return self._env("MCP_CRM_URL", "http://localhost:8001/mcp")
        @property
        def mcp_order_url(self): return self._env("MCP_ORDER_URL", "http://localhost:8002/mcp")
        @property
        def mcp_ticket_url(self): return self._env("MCP_TICKET_URL", "http://localhost:8003/mcp")
        @property
        def otel_exporter_otlp_endpoint(self): return self._env("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
        @property
        def prometheus_port(self): return self._env("PROMETHEUS_PORT", 9090, int)
        @property
        def secret_key(self): return self._env("SECRET_KEY", "change-me")
        @property
        def jwt_algorithm(self): return self._env("JWT_ALGORITHM", "HS256")
        @property
        def jwt_expire_minutes(self): return self._env("JWT_EXPIRE_MINUTES", 1440, int)
        @property
        def debug(self): return self._env("DEBUG", True, lambda x: str(x).lower() == "true")
        @property
        def log_level(self): return self._env("LOG_LEVEL", "INFO")
        @property
        def api_port(self): return self._env("API_PORT", 8000, int)
        @property
        def cors_origins(self): return self._env("CORS_ORIGINS", "*")
        @property
        def chunk_size(self): return self._env("CHUNK_SIZE", 800, int)
        @property
        def chunk_overlap(self): return self._env("CHUNK_OVERLAP", 150, int)
        @property
        def retrieval_top_k(self): return self._env("RETRIEVAL_TOP_K", 5, int)
        @property
        def hybrid_fusion_k(self): return self._env("HYBRID_FUSION_K", 60, int)
        @property
        def intent_confidence_threshold(self): return self._env("INTENT_CONFIDENCE_THRESHOLD", 0.50, float)
        @property
        def max_conversation_turns(self): return self._env("MAX_CONVERSATION_TURNS", 50, int)
        @property
        def handoff_unsatisfied_threshold(self): return self._env("HANDOFF_UNSATISFIED_THRESHOLD", 2, int)
        @property
        def handoff_timeout_minutes(self): return self._env("HANDOFF_TIMEOUT_MINUTES", 30, int)

    settings = Settings()
