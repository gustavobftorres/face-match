import json

import pytest

from app.evaluation.__main__ import main
from app.evaluation.models import FaceScore, SearchResult


class SyntheticAdapter:
    def __init__(self, name, variant="default"):
        self.name = name
        self.variant = variant

    def search(self, gallery, scan):
        distance = 0.6 if scan.id == "boundary" else 0.5
        return SearchResult(True, tuple(FaceScore(ref.identity_id, -distance) for ref in gallery), score_semantics="negative_distance")


class LegacySyntheticAdapter:
    def __init__(self, name):
        self.name = name

    def search(self, gallery, scan):
        return SearchResult(True, tuple(FaceScore(ref.identity_id, 0.4) for ref in gallery))


def cli_files(tmp_path, baseline_extra="", top_extra=""):
    for name in ("a", "b", "cal", "boundary"):
        (tmp_path / name).write_bytes(name.encode())
    (tmp_path / "manifest.toml").write_text('''version = 1
media_root = "."
[[references]]
id = "a"
identity = "a"
path = "a"
split = "calibration"
[[references]]
id = "b"
identity = "b"
path = "b"
split = "test"
[[scans]]
id = "cal"
path = "cal"
split = "calibration"
expected_identities = ["a"]
[[scans]]
id = "boundary"
path = "boundary"
split = "test"
expected_identities = ["b"]
''')
    config = tmp_path / "evaluation.toml"
    config.write_text('manifest = "manifest.toml"\noutput_dir = "run"\n' + top_extra + '''
[baseline]
factory = "test_cli:SyntheticAdapter"
''' + baseline_extra + '''
[candidate]
factory = "test_cli:SyntheticAdapter"
policy = "production_distance"
''')
    return config


def test_cli_production_policy_and_provenance(tmp_path):
    from hashlib import sha256
    config = cli_files(tmp_path, 'policy = "production_distance"\nthreshold = 0.6\n[baseline.options]\nvariant = "deterministic-v2"\n')
    assert main(["--config", str(config)]) == 0
    thresholds = json.loads((tmp_path / "run/threshold.json").read_text())
    baseline = thresholds["baseline"]
    assert baseline["threshold"] == -0.6
    assert baseline["policy"] == "production_distance"
    assert baseline["comparator"] == ">"
    assert baseline["score_semantics"] == "negative_distance"
    assert baseline["calibrated_on"] is None
    provenance = json.loads((tmp_path / "run/run.json").read_text())["provenance"]
    assert provenance["python"] and provenance["platform"]
    assert "commit" in provenance and "dlib" in provenance["packages"]
    assert provenance["dataset"]["references"][0]["sha256"] == sha256(b"a").hexdigest()
    assert provenance["dataset"]["scans"][1]["sha256"] == sha256(b"boundary").hexdigest()
    assert provenance["decisions"]["baseline"] == {
        "policy": "production_distance", "threshold": 0.6,
        "threshold_source": "production_configuration", "comparator": ">",
        "score_semantics": "negative_distance", "calibrated_on": None,
    }
    assert provenance["adapters"]["baseline"]["identity"].endswith(":SyntheticAdapter")
    assert provenance["adapter_config"]["baseline"] == {
        "factory": "test_cli:SyntheticAdapter", "policy": "production_distance",
        "threshold": 0.6, "options": {"variant": "deterministic-v2"},
    }
    report = (tmp_path / "run/report.md").read_text()
    assert "production_distance" in report and "negative_distance" in report and ">" in report


@pytest.mark.parametrize("fields", ['policy = "typo"\n', 'policy = "production_distance"\nthreshold = -0.1\n', 'policy = "production_distance"\nthreshold = true\n', 'policy = "production_distance"\nthreshold = inf\n', 'policy = "calibrate_f1"\nthreshold = 0.6\n', 'polciy = "production_distance"\n', 'calibration = "test"\n'])
def test_cli_rejects_unknown_or_invalid_role_fields(tmp_path, fields):
    config = cli_files(tmp_path, fields)
    with pytest.raises(ValueError):
        main(["--config", str(config)])
    assert not (tmp_path / "run").exists()


def test_cli_defaults_preserve_legacy_calibration(tmp_path):
    config = cli_files(tmp_path)
    config.write_text(config.read_text().replace("test_cli:SyntheticAdapter", "test_cli:LegacySyntheticAdapter").replace('policy = "production_distance"', ''))
    main(["--config", str(config)])
    thresholds = json.loads((tmp_path / "run/threshold.json").read_text())
    assert {value["policy"] for value in thresholds.values()} == {"calibrate_f1"}
    assert {value["threshold"] for value in thresholds.values()} == {0.4}
    assert {value["comparator"] for value in thresholds.values()} == {">="}
    assert {value["score_semantics"] for value in thresholds.values()} == {"higher_is_better"}


def test_cli_omitted_factory_selects_adapter_for_policy():
    from app.evaluation.__main__ import _adapter
    from app.evaluation import DlibProductionAdapter, FaceSearchAdapter
    assert isinstance(_adapter({"policy": "production_distance"}, "baseline"), DlibProductionAdapter)
    assert type(_adapter({}, "candidate")) is FaceSearchAdapter


def test_cli_rejects_non_json_options_before_constructing_adapters(tmp_path, monkeypatch):
    import app.evaluation.__main__ as cli
    config = cli_files(tmp_path, 'policy = "production_distance"\n[baseline.options]\ndate = 2026-11-11\n')
    def forbidden(*args):
        raise AssertionError("adapter construction must follow metadata validation")
    monkeypatch.setattr(cli, "_adapter", forbidden)
    with pytest.raises(ValueError, match="JSON"):
        cli.main(["--config", str(config)])


def test_cli_rejects_unknown_top_level_fields(tmp_path):
    config = cli_files(tmp_path, top_extra='typo = "value"\n')
    with pytest.raises(ValueError, match="unknown"):
        main(["--config", str(config)])
