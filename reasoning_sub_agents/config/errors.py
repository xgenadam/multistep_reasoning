class ConfigError(ValueError):
    """Invalid orchestrator YAML or unknown component name."""


class IncompatibleComponentsError(ConfigError):
    """Selected components declare conflicting capabilities."""
