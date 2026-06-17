"""Configuration loader for Stripsmith."""

import os
import yaml
from pathlib import Path
from typing import Any, Dict, Optional

# Single source of truth for the default Claude model used by the narrative
# analyzer and panel breakdown. Keeping it here (rather than as a literal in
# each module) ensures the in-code fallback can't drift out of sync with
# config/config.yaml. The previous value, "claude-3-opus-20240229", was retired
# on 2026-01-05 and now returns 404; "claude-opus-4-8" is its supported
# replacement per Anthropic's migration guide.
DEFAULT_LLM_MODEL = "claude-opus-4-8"

# Default cap on Claude's output tokens. The pipeline asks for structured JSON
# describing many chapters/characters/panels, so we give it generous headroom to
# avoid truncated (unparseable) responses. Stays well under the SDK's
# non-streaming HTTP timeout threshold.
DEFAULT_LLM_MAX_TOKENS = 8192


class Config:
    """Configuration manager for Stripsmith."""

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize configuration.

        Args:
            config_path: Path to config.yaml file. If None, uses default.
        """
        if config_path is None:
            # Default to config/config.yaml in project root
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "config" / "config.yaml"

        self.config_path = Path(config_path)
        self._config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)
            return config or {}
        except FileNotFoundError:
            print(f"Warning: Config file not found at {self.config_path}")
            return {}
        except yaml.YAMLError as e:
            print(f"Error parsing config file: {e}")
            return {}

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value using dot notation.

        Args:
            key: Configuration key (e.g., "image.size")
            default: Default value if key not found

        Returns:
            Configuration value

        Example:
            >>> config = Config()
            >>> config.get("image.size")
            "1024x1024"
        """
        keys = key.split('.')
        value = self._config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def set(self, key: str, value: Any):
        """
        Set configuration value using dot notation.

        Args:
            key: Configuration key (e.g., "image.size")
            value: Value to set
        """
        keys = key.split('.')
        config = self._config

        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]

        config[keys[-1]] = value

    def save(self):
        """Save current configuration back to file."""
        with open(self.config_path, 'w') as f:
            yaml.dump(self._config, f, default_flow_style=False)

    @property
    def image(self) -> Dict[str, Any]:
        """Get image generation settings."""
        return self.get('image', {})

    @property
    def characters(self) -> Dict[str, Any]:
        """Get character settings."""
        return self.get('characters', {})

    @property
    def layout(self) -> Dict[str, Any]:
        """Get layout settings."""
        return self.get('layout', {})

    @property
    def bubbles(self) -> Dict[str, Any]:
        """Get speech bubble settings."""
        return self.get('bubbles', {})

    @property
    def analysis(self) -> Dict[str, Any]:
        """Get analysis settings."""
        return self.get('analysis', {})

    @property
    def panels(self) -> Dict[str, Any]:
        """Get panel settings."""
        return self.get('panels', {})

    @property
    def export(self) -> Dict[str, Any]:
        """Get export settings."""
        return self.get('export', {})

    @property
    def processing(self) -> Dict[str, Any]:
        """Get processing settings."""
        return self.get('processing', {})

    def __repr__(self) -> str:
        return f"Config(path={self.config_path})"


# Global config instance
_global_config: Optional[Config] = None


def get_config(config_path: Optional[str] = None) -> Config:
    """
    Get global configuration instance.

    Args:
        config_path: Optional path to config file

    Returns:
        Config instance
    """
    global _global_config

    if _global_config is None or config_path is not None:
        _global_config = Config(config_path)

    return _global_config
