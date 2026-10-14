"""ezmd HTTP API."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("ezmd-api")
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "0+unknown"
