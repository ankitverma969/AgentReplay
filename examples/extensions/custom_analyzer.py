"""Example AgentReplay SDK custom analyzer extension."""

from __future__ import annotations

from agentreplay.sdk import AnalyzerResult, SDKExtensionMetadata, TraceSnapshot


class PromptLengthAnalyzer:
    """Analyze prompt payload sizes in a recorded trace."""

    metadata = SDKExtensionMetadata(
        name="prompt-length-analyzer",
        version="0.1.0",
        kind="analyzer",
        summary="Counts prompt characters in recorded traces.",
    )

    def analyze(self, trace: TraceSnapshot) -> AnalyzerResult:
        """Return prompt-size metrics."""
        total = 0
        for event in trace.events:
            prompt = event.payload.get("prompt")
            if isinstance(prompt, str):
                total += len(prompt)
        return AnalyzerResult(
            analyzer=self.metadata.name,
            metrics={"prompt_characters": total},
            recommendations=(
                "Reduce prompt size." if total > 4_000 else "Prompt size is healthy.",
            ),
        )
