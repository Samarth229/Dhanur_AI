import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from meher_agent.config import PROJECT_ROOT, load_settings


def test_settings_load():
    settings = load_settings()
    assert settings.llm.temperature == 0.1
    assert settings.llm.max_model_calls == 4
    assert settings.reply.max_chars == 1200
    assert settings.eval.runs == 3
    assert settings.eval.inr_per_usd == 100


def test_paths_resolve_inside_project():
    settings = load_settings()
    for path in (settings.paths.data_dir, settings.paths.evals_dir, settings.paths.reports_dir):
        assert path.is_absolute()
        assert path.is_relative_to(PROJECT_ROOT)


def test_data_paths_point_to_existing_dirs():
    settings = load_settings()
    assert settings.paths.data_dir.is_dir()
    assert settings.paths.evals_dir.is_dir()
