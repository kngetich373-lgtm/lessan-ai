import logging
import sys
import os
import json
import re
from typing import Any, Optional

def setup_logging(level: int = logging.INFO, log_file: Optional[str] = None) -> logging.Logger:
    """
    Configure and return a logger for the Lessan agent.
    """
    logger = logging.getLogger('lessan')
    if logger.handlers:
        # Avoid adding handlers multiple times
        return logger
    logger.setLevel(level)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    # Optional file handler
    if log_file:
        try:
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except IOError as e:
            logger.error(f"Unable to open log file '{log_file}': {e}")
    return logger

def sanitize_input(user_input: str) -> str:
    """
    Strip and normalize whitespace from user input.
    Returns an empty string for non‑string inputs.
    """
    if not isinstance(user_input, str):
        return ''
    cleaned = user_input.strip()
    # Collapse multiple whitespace characters to a single space
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned

def safe_read_file(filepath: str) -> Optional[str]:
    """
    Read the entire contents of a file safely.
    Returns None on failure, logging the error.
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        logging.getLogger('lessan').warning(f"File not found: {filepath}")
    except IOError as e:
        logging.getLogger('lessan').error(f"IO error reading '{filepath}': {e}")
    return None

def safe_write_file(filepath: str, content: str) -> bool:
    """
    Write content to a file safely, creating parent directories if needed.
    Returns True on success, False on failure.
    """
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    except IOError as e:
        logging.getLogger('lessan').error(f"IO error writing '{filepath}': {e}")
        return False

def load_json(filepath: str) -> Optional[Any]:
    """
    Load and parse a JSON file.
    Returns the parsed object or None on failure.
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.getLogger('lessan').warning(f"JSON file not found: {filepath}")
    except json.JSONDecodeError as e:
        logging.getLogger('lessan').error(f"Invalid JSON in '{filepath}': {e}")
    except IOError as e:
        logging.getLogger('lessan').error(f"IO error reading JSON '{filepath}': {e}")
    return None

def save_json(filepath: str, data: Any, indent: int = 2) -> bool:
    """
    Serialize data to JSON and write it to a file.
    Returns True on success, False on failure.
    """
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
        return True
    except (TypeError, ValueError) as e:
        logging.getLogger('lessan').error(f"Error serializing JSON for '{filepath}': {e}")
    except IOError as e:
        logging.getLogger('lessan').error(f"IO error writing JSON to '{filepath}': {e}")
    return False