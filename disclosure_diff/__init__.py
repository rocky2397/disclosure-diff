"""Disclosure Diff: what annual reports disclose about a topic, and how that changes."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("disclosure-diff")
except PackageNotFoundError:  # running from a checkout that was never installed
    __version__ = "0+unknown"
