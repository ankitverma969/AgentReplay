"""Example AgentReplay SDK custom CLI command extension."""

from __future__ import annotations

import argparse

from agentreplay.cli.commands._shared import write_line
from agentreplay.sdk import SDKExtensionMetadata


class MyPluginCommand:
    """Register a namespaced custom CLI command."""

    metadata = SDKExtensionMetadata(
        name="myplugin",
        version="0.1.0",
        kind="cli_command",
        summary="Example namespaced SDK CLI command.",
    )

    def register(
        self,
        subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    ) -> None:
        """Register ``agentreplay myplugin``."""
        parser = subparsers.add_parser("myplugin")
        parser.add_argument("action", choices=("analyze",))
        parser.set_defaults(handler=self.handle)

    def handle(self, args: argparse.Namespace) -> int:
        """Handle the custom command."""
        write_line(f"myplugin {args.action}")
        return 0
