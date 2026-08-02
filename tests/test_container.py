from __future__ import annotations

from datetime import datetime

from agentreplay.config import Settings
from agentreplay.container import create_container


def test_container_uses_explicit_settings() -> None:
    settings = Settings(enabled=True)
    container = create_container(settings=settings)

    assert container.settings is settings
    assert isinstance(container.clock.now(), datetime)
    assert container.id_generator.new_id()
