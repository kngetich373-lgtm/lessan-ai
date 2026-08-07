import os
import json
import logging

# Default configuration values
DEFAULT_MODEL = "gpt-4"
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 2000
DEFAULT_LOG_LEVEL = logging.INFO
DEFAULT_LOG_FILE = None

def load_config():
    """Load configuration from config.json if present, otherwise use defaults."""
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    config = {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except FileNotFoundError:
        # No config file found; defaults will be used
        pass
    except json.JSONDecodeError as e:
        logging.getLogger('lessan').warning(f"Invalid JSON in config file '{config_path}': {e}")
    except IOError as e:
        logging.getLogger('lessan').error(f"IO error reading config file '{config_path}': {e}")

    # Override defaults with loaded values
    model = config.get("model", DEFAULT_MODEL)
    temperature = config.get("temperature", DEFAULT_TEMPERATURE)
    max_tokens = config.get("max_tokens", DEFAULT_MAX_TOKENS)
    log_level_str = config.get("log_level")
    if log_level_str:
        log_level = getattr(logging, log_level_str.upper(), DEFAULT_LOG_LEVEL)
    else:
        log_level = DEFAULT_LOG_LEVEL
    log_file = config.get("log_file", DEFAULT_LOG_FILE)

    return {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "log_level": log_level,
        "log_file": log_file,
    }

# Load configuration once at import time
CONFIG = load_config()

# Exported configuration constants
MODEL = CONFIG["model"]
TEMPERATURE = CONFIG["temperature"]
MAX_TOKENS = CONFIG["max_tokens"]
LOG_LEVEL = CONFIG["log_level"]
LOG_FILE = CONFIG["log_file"]