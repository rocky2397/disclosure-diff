from pathlib import Path

import pytest

from disclosure_diff.settings import (
    ENV_VAR,
    POINTER_FILE,
    DataDirError,
    is_sidecar,
    resolve_data_dir,
)


def test_explicit_path_wins(tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    data = resolve_data_dir(tmp_path, env={ENV_VAR: str(other)}, cwd=tmp_path)
    assert data.root == tmp_path
    assert data.reports == tmp_path / "reports"
    assert data.extracted == tmp_path / "extracted"
    assert data.output == tmp_path / "output"


def test_environment_variable(tmp_path):
    assert resolve_data_dir(env={ENV_VAR: str(tmp_path)}, cwd=tmp_path).root == tmp_path


def test_pointer_file(tmp_path):
    data_root = tmp_path / "drive"
    data_root.mkdir()
    cwd = tmp_path / "repo"
    cwd.mkdir()
    (cwd / POINTER_FILE).write_text(f"{data_root}\n", encoding="utf-8")
    assert resolve_data_dir(env={}, cwd=cwd).root == data_root


def test_not_configured(tmp_path):
    with pytest.raises(DataDirError, match="No data folder configured"):
        resolve_data_dir(env={}, cwd=tmp_path)


def test_missing_folder_mentions_the_drive(tmp_path):
    with pytest.raises(DataDirError, match="plugged in"):
        resolve_data_dir(tmp_path / "unplugged", env={}, cwd=tmp_path)


def test_sidecar_files_are_recognised():
    assert is_sidecar(Path("/Volumes/x/reports/._BP_2023.pdf"))
    assert not is_sidecar(Path("/Volumes/x/reports/BP_2023.pdf"))
