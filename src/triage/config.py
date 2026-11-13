"""Configuration lue dans l'environnement et le fichier .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    log_level: str = "info"
    api_key: str = "change-me"
    audit_api_key: str = "change-me-audit"  # clé distincte pour consulter le journal

    base_model_id: str = "Qwen/Qwen3-1.7B-Base"
    served_model_id: str = "triage-chsa"
    vllm_base_url: str = "http://localhost:8001/v1"

    audit_log_path: str = "outputs/audit/interactions.jsonl"


settings = Settings()
