from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SandboxLimits:
    """Resource limits applied to each sandbox container."""

    timeout_seconds: float = 5.0
    memory: str = "256m"
    nano_cpus: int = 1_000_000_000
    pids_limit: int = 64

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not self.memory.strip():
            raise ValueError("memory must be non-empty")
        if self.nano_cpus <= 0:
            raise ValueError("nano_cpus must be positive")
        if self.pids_limit <= 0:
            raise ValueError("pids_limit must be positive")
