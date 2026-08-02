"""SDK compatibility checks, stable API policy, and deprecation helpers."""

from __future__ import annotations

import functools
import warnings
from collections.abc import Callable
from typing import ParamSpec, TypeVar

from agentreplay.exceptions import SDKError
from agentreplay.sdk.models import SDKCompatibility, SDKExtensionMetadata, SDKVersion

SDK_API_VERSION = "0.1.0"
DEPRECATION_POLICY = (
    "Stable SDK APIs use semantic versioning. Deprecated APIs emit "
    "DeprecationWarning for at least one minor release before removal."
)

ParamT = ParamSpec("ParamT")
ReturnT = TypeVar("ReturnT")


def ensure_sdk_compatible(
    metadata: SDKExtensionMetadata,
    *,
    sdk_version: str = SDK_API_VERSION,
) -> None:
    """Raise when an extension declares incompatible SDK bounds."""
    current = SDKVersion.parse(sdk_version)
    minimum = SDKVersion.parse(metadata.compatibility.min_sdk_version)
    if _lt(current, minimum):
        msg = (
            f"Extension {metadata.name} requires AgentReplay SDK "
            f">= {metadata.compatibility.min_sdk_version}; current {sdk_version}."
        )
        raise SDKError(msg)
    if metadata.compatibility.max_sdk_version is not None:
        maximum = SDKVersion.parse(metadata.compatibility.max_sdk_version)
        if _lt(maximum, current):
            msg = (
                f"Extension {metadata.name} supports AgentReplay SDK "
                f"<= {metadata.compatibility.max_sdk_version}; current {sdk_version}."
            )
            raise SDKError(msg)


def compatible(
    *,
    min_sdk_version: str = "0.1.0",
    max_sdk_version: str | None = None,
) -> SDKCompatibility:
    """Build an extension compatibility declaration."""
    return SDKCompatibility(
        min_sdk_version=min_sdk_version,
        max_sdk_version=max_sdk_version,
    )


def deprecated(
    message: str,
) -> Callable[[Callable[ParamT, ReturnT]], Callable[ParamT, ReturnT]]:
    """Decorate a stable SDK function with a deprecation warning."""

    def decorator(func: Callable[ParamT, ReturnT]) -> Callable[ParamT, ReturnT]:
        @functools.wraps(func)
        def wrapper(*args: ParamT.args, **kwargs: ParamT.kwargs) -> ReturnT:
            warnings.warn(message, DeprecationWarning, stacklevel=2)
            return func(*args, **kwargs)

        return wrapper

    return decorator


def _lt(left: SDKVersion, right: SDKVersion) -> bool:
    """Return whether one SDK version is lower than another."""
    return (left.major, left.minor, left.patch) < (
        right.major,
        right.minor,
        right.patch,
    )


__all__ = [
    "DEPRECATION_POLICY",
    "SDK_API_VERSION",
    "compatible",
    "deprecated",
    "ensure_sdk_compatible",
]
