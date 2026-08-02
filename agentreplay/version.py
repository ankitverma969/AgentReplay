"""Package version helpers."""

from importlib.metadata import PackageNotFoundError, version

from agentreplay.constants import PACKAGE_NAME


def get_version() -> str:
    """Return the installed AgentReplay distribution version."""
    try:
        return version(PACKAGE_NAME)
    except PackageNotFoundError:
        return "0.1.0"


__version__ = get_version()

__all__ = ["__version__", "get_version"]
