# Plugin SDK

AgentReplay plugins let external packages add integrations without changing
AgentReplay core code.

Plugins are discovered through Python package entry points. A package such as
`agentreplay-crewai` becomes available after installation when it exposes an
entry point in the `agentreplay.plugins` group.

## Plugin Types

Supported plugin types:

- `agent_framework`
- `llm_provider`
- `storage_backend`
- `exporter`
- `cli_command`
- `event_processor`
- `metadata_collector`
- `auth_provider`

Authentication providers are future-ready registration points. They should not
require network calls during plugin loading.

## Minimal Plugin

```python
from agentreplay.plugins import AgentReplayPlugin


class CrewAIPlugin(AgentReplayPlugin):
    name = "crewai"
    version = "1.0.0"
    plugin_type = "agent_framework"
    summary = "CrewAI integration for AgentReplay."

    def register(self, app):
        app.register_agent_framework("crewai", object())
```

Package metadata:

```toml
[project.entry-points."agentreplay.plugins"]
crewai = "agentreplay_crewai:CrewAIPlugin"
```

## Registration API

The plugin `register(app)` method receives a `PluginApp`.

Registration methods:

- `register_agent_framework(name, value)`
- `register_llm_provider(name, value)`
- `register_storage_backend(name, value)`
- `register_exporter(name, value)`
- `register_cli_command(name, registrar)`
- `register_event_processor(name, processor)`
- `register_metadata_collector(name, collector)`
- `register_auth_provider(name, provider)`
- `register_hook(hook, handler)`

Each registration is owned by the active plugin and can be removed when the
plugin is unloaded.

## Lifecycle Hooks

Supported hooks:

- `before_run`
- `after_run`
- `before_event`
- `after_event`
- `before_replay`
- `after_replay`
- `before_export`
- `after_export`
- `plugin_loaded`
- `plugin_unloaded`

Hook handlers receive a `PluginHookContext` with the hook name, optional plugin
name, and JSON-compatible payload. Hook exceptions are caught and reported as
failed `PluginHookResult` objects so core behavior can continue.

## Metadata

Plugins declare metadata as class attributes:

```python
from agentreplay.plugins import AgentReplayPlugin, PluginDependency


class MarkdownExporterPlugin(AgentReplayPlugin):
    name = "markdown-exporter"
    version = "1.2.0"
    plugin_type = "exporter"
    min_agentreplay_version = "0.1.0"
    max_agentreplay_version = "1.0.0"
    dependencies = (PluginDependency("shared-utils", ">=1.0.0"),)
```

The validator checks plugin name format, version presence, plugin type,
AgentReplay compatibility bounds, dependency constraints, and config schema
types.

## Configuration

AgentReplay supports plugin enablement and plugin-specific configuration.

```toml
[plugins]
enabled = true
auto_discover = true
disabled = ["unstable-plugin"]

[plugins.crewai]
record_tasks = true
team = "automation"
```

Environment variables:

- `AGENTREPLAY_PLUGINS_ENABLED`
- `AGENTREPLAY_PLUGIN_AUTO_DISCOVER`
- `AGENTREPLAY_DISABLED_PLUGINS`
- `AGENTREPLAY_PLUGIN_CONFIG_<PLUGIN>__<KEY>`

Example:

```bash
AGENTREPLAY_PLUGIN_CONFIG_CREWAI__TEAM=automation
```

Plugin class config schema:

```python
class CrewAIPlugin(AgentReplayPlugin):
    name = "crewai"
    version = "1.0.0"
    plugin_type = "agent_framework"
    config_schema = {"record_tasks": "bool", "team": "str"}
```

## Plugin Manager

```python
from agentreplay.plugins import PluginManager

manager = PluginManager()
records = manager.load_plugins()
manager.emit_hook("before_run", payload={"run_id": "run-123"})
```

Use `load_plugin(plugin)` for hot-loading tests or local application plugins.
Use `unload_plugin(name)` to remove plugin-owned registrations and invoke unload
lifecycle behavior.

## CLI

```bash
agentreplay plugins
agentreplay plugins list
agentreplay plugins info crewai
agentreplay plugins install agentreplay-crewai
agentreplay plugins disable crewai
```

`plugins install` delegates to `python -m pip install`. `plugins disable`
records local CLI disablement in `.agentreplay/disabled_plugins.txt`.

## Best Practices

- Keep imports cheap. Do not call providers, databases, tools, or LLMs while
  loading a plugin.
- Fail open where possible and surface diagnostics through plugin records.
- Register capabilities only inside `register(app)`.
- Store secrets outside config files; use environment variables.
- Keep plugin names stable and lowercase.
- Declare `min_agentreplay_version` when relying on newer SDK features.

## Failure Handling

The plugin manager isolates registration and hook exceptions. A failed plugin is
marked `failed`, its registrations are removed, and AgentReplay core remains
available unless the manager is explicitly configured with `fail_open=False`.

## Migration Guide

Existing in-repo adapters can be moved to plugins by:

1. Subclassing `AgentReplayPlugin`.
2. Moving adapter setup into `register(app)`.
3. Publishing an entry point in `agentreplay.plugins`.
4. Keeping the adapter package optional.
5. Adding config schema entries for plugin-owned settings.
