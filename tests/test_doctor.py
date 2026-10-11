"""Conservative version matching must not select offsets for a newer build."""

import importlib.util
import json
from pathlib import Path


spec = importlib.util.spec_from_file_location("wechat_doctor", Path(__file__).parents[1] / "scripts/doctor.py")
doctor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(doctor)


def write_config(tmp_path, filename="4_1_12_53_mac.json"):
    path = tmp_path / filename
    path.write_text(json.dumps({name: "0x1000" for name in doctor.CORE_OFFSETS}))
    return path


def test_new_wechat_version_does_not_match_older_offsets(tmp_path):
    result = doctor.inspect_config(write_config(tmp_path), "4.1.15", "270134")
    assert not result["candidate_for_installed_version"]
    assert not result["version_matches"]
    assert not result["offsets_verified_in_binary"]


def test_known_build_must_match_even_with_same_version(tmp_path):
    path = write_config(tmp_path)
    assert doctor.inspect_config(path, "4.1.12", "269365")["candidate_for_installed_version"]
    assert not doctor.inspect_config(path, "4.1.12", "269366")["candidate_for_installed_version"]
    assert not doctor.inspect_config(path, "4.1.12.53", "269366")["candidate_for_installed_version"]


def test_unknown_build_is_not_inferred_from_three_version_components(tmp_path):
    path = write_config(tmp_path, "4_1_15_53_mac.json")
    result = doctor.inspect_config(path, "4.1.15", "270134")
    assert result["build_matches"] is None
    assert not result["candidate_for_installed_version"]


def test_malformed_or_missing_core_offsets_cannot_be_selected(tmp_path):
    path = write_config(tmp_path)
    for content in ["{}", "[]", "broken JSON", json.dumps({name: "0x1" for name in doctor.CORE_OFFSETS})]:
        path.write_text(content)
        result = doctor.inspect_config(path, "4.1.12", "269365")
        assert not result["core_offsets_well_formed"]
        assert not result["candidate_for_installed_version"]
