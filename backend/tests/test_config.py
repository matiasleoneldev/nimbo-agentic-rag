from pathlib import Path

import pytest

from nimbo.config import REPO_ROOT, load_settings


def test_config_resolves_paths_from_any_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    settings = load_settings()

    assert settings.manifest_path == REPO_ROOT / "nimbo-help-center" / "manifest.json"
    assert settings.help_center_dir == REPO_ROOT / "nimbo-help-center"
    assert settings.labels["countries"]["AR"] == "Argentina"
    assert settings.max_exchanges == 6
    assert settings.max_searches == 3
    assert settings.conversation_ttl_seconds == 900
