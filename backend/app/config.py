from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    public_host: str
    public_origin: str
    cookie_secure: bool = True
    session_ttl_hours: int = 12
    max_upload_mb: int = 50
    bulk_max_files: int = 1000
    bulk_max_total_mb: int = 500
    zip_max_expanded_mb: int = 500

    database_url: str
    redis_url: str

    ollama_url: str = "http://ollama:11434"
    embedding_model: str = "all-minilm"
    embedding_dimensions: int = 384
    chat_model: str = "qwen3:4b"
    chat_import_chunk_chars: int = 14000
    chat_import_max_candidates_per_chunk: int = 12
    github_app_id: str | None = None
    github_app_private_key_path: str = "/run/secrets/github-app.pem"
    connector_scheduler_interval_seconds: int = 60
    github_max_items_per_sync: int = 300
    github_max_file_kb: int = 512
    capture_max_chars: int = 500000
    oauth_access_token_minutes: int = 15
    oauth_refresh_token_days: int = 30
    oauth_authorization_code_minutes: int = 5
    oauth_cimd_timeout_seconds: int = 5
    oauth_cimd_max_kb: int = 256
    oauth_dcr_enabled: bool = True
    dr_monitor_interval_seconds: int = 300
    dr_max_backup_age_hours: int = 36
    dr_restore_test_interval_hours: int = 24
    dr_restore_test_max_age_hours: int = 36
    dr_restore_test_enabled: bool = True
    dr_offsite_remote: str | None = None
    dr_offsite_config_path: str = "/run/secrets/rclone.conf"
    dr_offsite_interval_hours: int = 6
    dr_min_backup_free_gb: int = 10

    minio_endpoint: str = "minio:9000"
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str = "memorybank"
    minio_secure: bool = False

    model_config = SettingsConfigDict(case_sensitive=False)


@lru_cache
def settings() -> Settings:
    return Settings()
