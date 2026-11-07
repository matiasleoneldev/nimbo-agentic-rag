"""Runtime settings: `backend/app.yaml` plus environment variables."""

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
CONFIG_FILE = BACKEND_DIR / "app.yaml"
ENV_FILE = BACKEND_DIR / ".env"


@dataclass(frozen=True)
class Settings:
    manifest_path: Path
    help_center_dir: Path
    chat_model: str
    chat_reasoning_effort: str | None
    embedding_model: str
    vector_size: int
    retrieval_k: int
    max_searches: int
    table: str
    max_exchanges: int
    conversation_ttl_seconds: int
    # labels[group][identifier] -> display label, e.g. labels["countries"]["AR"] == "Argentina"
    labels: dict[str, dict[str, str]]


def load_settings(config_file: Path = CONFIG_FILE) -> Settings:
    raw = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    # Relative paths in app.yaml are relative to the repo root, never to the cwd.
    root = config_file.resolve().parent.parent
    return Settings(
        manifest_path=root / raw["paths"]["manifest"],
        help_center_dir=root / raw["paths"]["help_center_dir"],
        chat_model=raw["models"]["chat"],
        chat_reasoning_effort=raw["models"].get("chat_reasoning_effort"),
        embedding_model=raw["models"]["embeddings"],
        vector_size=int(raw["models"]["vector_size"]),
        retrieval_k=int(raw["retrieval"]["k"]),
        max_searches=int(raw["retrieval"]["max_searches"]),
        table=raw["retrieval"]["table"],
        max_exchanges=int(raw["conversations"]["max_exchanges"]),
        conversation_ttl_seconds=int(raw["conversations"]["ttl_seconds"]),
        labels=raw["labels"],
    )


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Environment variable {name} is not set (see backend/.env.example).")
    return value
