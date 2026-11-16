from pathlib import Path


def test_config_import_with_container_file_layout(tmp_path, monkeypatch):
    """Execute the module with the /app layout used by Docker COPY."""
    source = Path(__file__).resolve().parents[2] / 'app/core/config.py'
    monkeypatch.chdir(tmp_path)
    namespace = {'__file__': '/app/app/core/config.py', '__name__': 'container_config_smoke'}
    exec(compile(source.read_text(), str(source), 'exec'), namespace)
    assert namespace['BACKEND_ROOT'] == Path('/app')
    assert namespace['REPO_ROOT'] == Path('/app')
    assert namespace['settings'].FACE_MATCH_DB_PATH == '/app/face_match_embeddings.db'


def test_config_resolves_monorepo_root():
    from app.core.config import BACKEND_ROOT, REPO_ROOT
    assert BACKEND_ROOT.name == 'backend'
    assert REPO_ROOT / 'apps' / 'backend' == BACKEND_ROOT
