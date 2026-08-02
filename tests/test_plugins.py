from __future__ import annotations

import argparse
import subprocess
import sys
import types
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, cast

import pytest
from agentreplay.cli.commands import plugins as plugins_command
from agentreplay.config import Settings, load_settings
from agentreplay.exceptions import ConfigurationError, PluginError
from agentreplay.plugins import (
    AgentReplayPlugin,
    ConfigValueType,
    PluginApp,
    PluginDependency,
    PluginDependencyResolver,
    PluginHookContext,
    PluginLoader,
    PluginManager,
    PluginMetadata,
    PluginRecord,
    PluginValidator,
)


def test_plugin_manager_loads_plugin_and_emits_lifecycle_hooks() -> None:
    plugin = _FrameworkPlugin()
    settings = Settings(
        plugin_config={"crewai": {"enabled": True, "label": "CrewAI"}},
    )
    manager = PluginManager(settings=settings)

    records = manager.load_plugins([plugin], discover=False)
    results = manager.emit_hook("before_run", payload={"run_id": "run-1"})

    assert records[0].status == "loaded"
    assert plugin.loaded is True
    assert plugin.run_ids == ["run-1"]
    assert [registration.name for registration in manager.app.registrations()] == [
        "crewai",
    ]
    assert results[0].succeeded is True


def test_disabled_plugins_do_not_register_capabilities() -> None:
    plugin = _FrameworkPlugin()
    settings = Settings(disabled_plugins=("crewai",))
    manager = PluginManager(settings=settings)

    records = manager.load_plugins([plugin], discover=False)

    assert records[0].status == "disabled"
    assert manager.app.registrations() == ()


def test_plugin_failure_is_isolated_when_fail_open() -> None:
    manager = PluginManager()

    records = manager.load_plugins([_CrashingPlugin()], discover=False)

    assert records[0].status == "failed"
    assert records[0].error == "registration exploded"
    assert manager.app.registrations() == ()


def test_discovery_failure_is_visible_when_fail_open() -> None:
    manager = PluginManager()

    records = manager.load_plugins([object()], discover=False)

    assert records[0].status == "failed"
    assert records[0].metadata.name == "object"
    assert records[0].error is not None


def test_plugin_failure_raises_when_fail_closed() -> None:
    manager = PluginManager(fail_open=False)

    with pytest.raises(PluginError, match="registration exploded"):
        manager.load_plugins([_CrashingPlugin()], discover=False)


def test_hook_failures_are_reported_without_stopping_core_flow() -> None:
    app = PluginApp()
    app.activate("unstable", {})
    app.register_hook("after_event", _broken_hook)
    app.deactivate()

    results = app.emit_hook("after_event", payload={"event_id": "event-1"})

    assert results[0].succeeded is False
    assert results[0].plugin_name == "unstable"
    assert results[0].error == "hook exploded"


def test_dependency_resolver_orders_dependencies() -> None:
    base = _metadata_record(_BasePlugin())
    dependent = _metadata_record(_DependentPlugin())

    resolved = PluginDependencyResolver().resolve((dependent, base))

    assert [record.metadata.name for record in resolved] == ["base", "dependent"]


def test_missing_dependency_raises() -> None:
    record = _metadata_record(_DependentPlugin())

    with pytest.raises(PluginError, match="depends on missing plugin"):
        PluginDependencyResolver().resolve((record,))


def test_validator_rejects_invalid_metadata_and_config() -> None:
    validator = PluginValidator()

    with pytest.raises(PluginError, match="Plugin names"):
        validator.validate_metadata(
            PluginMetadata(name="Bad Name", version="1", plugin_type="exporter"),
        )

    plugin = _FrameworkPlugin()
    metadata = plugin.metadata()
    with pytest.raises(PluginError, match="must be of type bool"):
        validator.validate_config(metadata, {"enabled": "yes"}, plugin)


def test_agentreplay_version_compatibility_is_checked() -> None:
    with pytest.raises(PluginError, match="requires AgentReplay"):
        PluginValidator().validate_plugin(_FuturePlugin())


def test_hot_loading_and_unloading_plugin() -> None:
    plugin = _FrameworkPlugin()
    manager = PluginManager(
        settings=Settings(
            plugin_config={"crewai": {"enabled": True, "label": "CrewAI"}},
        ),
    )

    record = manager.load_plugin(plugin)
    manager.unload_plugin("crewai")

    assert record.status == "loaded"
    assert plugin.unloaded is True
    assert manager.registry.require("crewai").status == "unloaded"
    assert manager.app.registrations(plugin_name="crewai") == ()


def test_loader_hot_loads_module_attribute(monkeypatch: pytest.MonkeyPatch) -> None:
    module = types.ModuleType("agentreplay_fake_plugin")
    dynamic_module = cast(Any, module)
    dynamic_module.Plugin = _FrameworkPlugin
    monkeypatch.setitem(sys.modules, "agentreplay_fake_plugin", module)

    plugin = PluginLoader().load_module("agentreplay_fake_plugin", "Plugin")

    assert plugin.name == "crewai"


def test_settings_parse_plugins_table_and_environment(tmp_path: Path) -> None:
    config_file = tmp_path / "agentreplay.toml"
    config_file.write_text(
        "\n".join(
            [
                "[plugins]",
                "enabled = true",
                "auto_discover = false",
                'disabled = ["unstable"]',
                "[plugins.crewai]",
                "enabled = true",
                'label = "CrewAI"',
            ],
        ),
        encoding="utf-8",
    )

    settings = load_settings(
        config_path=config_file,
        environ={
            "AGENTREPLAY_PLUGIN_CONFIG_CREWAI__LIMIT": "3",
            "AGENTREPLAY_DISABLED_PLUGINS": "other",
        },
    )

    assert settings.plugins_enabled is True
    assert settings.plugin_auto_discover is False
    assert settings.disabled_plugins == ("other",)
    assert settings.plugin_config["crewai"]["enabled"] is True
    assert settings.plugin_config["crewai"]["label"] == "CrewAI"
    assert settings.plugin_config["crewai"]["limit"] == 3


def test_invalid_plugin_config_table_raises(tmp_path: Path) -> None:
    config_file = tmp_path / "agentreplay.toml"
    config_file.write_text("[plugins]\ncrewai = true\n", encoding="utf-8")

    with pytest.raises(ConfigurationError):
        load_settings(config_path=config_file, environ={})


def test_plugins_cli_lists_and_shows_info(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(plugins_command, "PluginManager", _FakePluginManager)

    assert plugins_command.handle_list(argparse.Namespace()) == 0
    assert "crewai 1.0.0 agent_framework loaded" in capsys.readouterr().out

    assert plugins_command.handle_info(argparse.Namespace(name="crewai")) == 0
    assert "Name: crewai" in capsys.readouterr().out


def test_plugins_cli_disable_writes_local_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    assert plugins_command.handle_disable(argparse.Namespace(name="crewai")) == 0

    assert "Disabled AgentReplay plugin: crewai" in capsys.readouterr().out
    assert (tmp_path / ".agentreplay" / "disabled_plugins.txt").read_text(
        encoding="utf-8",
    ) == "crewai\n"


def test_plugins_cli_install_uses_pip(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[list[str]] = []

    def fake_run(
        command: list[str],
        *,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert check is False
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert (
        plugins_command.handle_install(
            argparse.Namespace(package="agentreplay-crewai"),
        )
        == 0
    )

    assert calls[0][-2:] == ["install", "agentreplay-crewai"]
    assert "Installed AgentReplay plugin package" in capsys.readouterr().out


class _FrameworkPlugin(AgentReplayPlugin):
    name = "crewai"
    version = "1.0.0"
    plugin_type = "agent_framework"
    summary = "CrewAI test adapter."
    config_schema: ClassVar[Mapping[str, ConfigValueType]] = {
        "enabled": "bool",
        "label": "str",
    }

    def __init__(self) -> None:
        self.loaded = False
        self.unloaded = False
        self.run_ids: list[object] = []

    def register(self, app: object) -> None:
        typed_app = app
        assert isinstance(typed_app, PluginApp)
        assert typed_app.config()["label"] == "CrewAI"
        typed_app.register_agent_framework("crewai", object())
        typed_app.register_hook("before_run", self.before_run)

    def on_plugin_loaded(self, app: object) -> None:
        assert isinstance(app, PluginApp)
        self.loaded = True

    def on_plugin_unloaded(self, app: object) -> None:
        assert isinstance(app, PluginApp)
        self.unloaded = True

    def before_run(self, context: object) -> None:
        payload = cast(PluginHookContext, context).payload
        self.run_ids.append(payload["run_id"])


class _CrashingPlugin(AgentReplayPlugin):
    name = "crashy"
    version = "1.0.0"
    plugin_type = "event_processor"

    def register(self, app: object) -> None:
        assert isinstance(app, PluginApp)
        raise RuntimeError("registration exploded")


class _BasePlugin(AgentReplayPlugin):
    name = "base"
    version = "1.0.0"
    plugin_type = "event_processor"


class _DependentPlugin(AgentReplayPlugin):
    name = "dependent"
    version = "1.0.0"
    plugin_type = "exporter"
    dependencies = (PluginDependency("base", ">=1.0.0"),)


class _FuturePlugin(AgentReplayPlugin):
    name = "future"
    version = "1.0.0"
    plugin_type = "event_processor"
    min_agentreplay_version = "99.0.0"


def _broken_hook(context: object) -> None:
    assert context is not None
    raise RuntimeError("hook exploded")


def _metadata_record(plugin: AgentReplayPlugin) -> PluginRecord:
    return PluginRecord(
        metadata=plugin.metadata(),
        status="discovered",
        source="test",
        plugin=plugin,
    )


@dataclass(slots=True)
class _FakePluginManager:
    disabled_plugins: tuple[str, ...] = ()

    def load_plugins(self) -> tuple[PluginRecord, ...]:
        return (
            PluginRecord(
                metadata=_FrameworkPlugin().metadata(),
                status="loaded",
                source="test",
                plugin=_FrameworkPlugin(),
            ),
        )
