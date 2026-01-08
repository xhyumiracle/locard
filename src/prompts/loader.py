"""
Prompt loader. Latest in prompts/, archived in prompts/archive/.

Usage:
    load_prompt("router")              # Latest
    load_prompt("router", version="v1") # Archived
"""

from pathlib import Path
from functools import lru_cache

PROMPTS_DIR = Path(__file__).parent


@lru_cache(maxsize=32)
def load_prompt(name: str, version: str = None) -> str:
    """Load prompt by name. Optionally specify archived version."""
    if version:
        path = PROMPTS_DIR / "archive" / version / f"{name}.md"
    else:
        path = PROMPTS_DIR / f"{name}.md"

    if not path.exists():
        raise FileNotFoundError(f"Prompt '{name}' not found: {path}")

    return path.read_text(encoding="utf-8").strip()
