"""Where the reports, extracted text and results live.

The data is kept outside the repository, for example on an external drive. The location
comes from, in this order: an explicit path, the ``DIA_DATA_DIR`` environment variable, or
a ``.dia-data-dir`` file in the current directory that holds the path on its first line.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

ENV_VAR = "DIA_DATA_DIR"
POINTER_FILE = ".dia-data-dir"


class DataDirError(RuntimeError):
    """The data folder is not configured or cannot be reached."""


@dataclass(frozen=True)
class DataDir:
    root: Path

    @property
    def reports(self) -> Path:
        """Annual report PDFs, one folder per company."""
        return self.root / "reports"

    @property
    def extracted(self) -> Path:
        """Passages extracted from the PDFs."""
        return self.root / "extracted"

    @property
    def judged(self) -> Path:
        """Judgements on candidate passages."""
        return self.root / "judged"

    @property
    def scanned(self) -> Path:
        """Judgements on passages the phrase search did not find."""
        return self.root / "scanned"

    @property
    def paired(self) -> Path:
        """Pairs of passages that were written anew from one report to the next."""
        return self.root / "paired"

    @property
    def output(self) -> Path:
        """Comparison reports."""
        return self.root / "output"


def resolve_data_dir(
    explicit: str | Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> DataDir:
    """Find the data folder, or raise :class:`DataDirError` saying what to do."""
    env = os.environ if env is None else env
    cwd = Path.cwd() if cwd is None else cwd

    value: str | None = str(explicit) if explicit else env.get(ENV_VAR)
    if not value:
        pointer = cwd / POINTER_FILE
        if pointer.is_file():
            lines = pointer.read_text(encoding="utf-8").splitlines()
            value = lines[0].strip() if lines else None
    if not value:
        raise DataDirError(
            f"No data folder configured. Pass --data-dir, set {ENV_VAR}, "
            f"or put the path in a {POINTER_FILE} file."
        )

    root = Path(value).expanduser()
    if not root.is_dir():
        raise DataDirError(
            f"Data folder not found: {root}. "
            "If it is on an external drive, check that the drive is plugged in."
        )
    return DataDir(root)


def is_sidecar(path: Path) -> bool:
    """True for the ``._name`` files macOS writes next to real files on ExFAT/FAT drives."""
    return path.name.startswith("._")
