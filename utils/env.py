"""
Utilidades sencillas para cargar variables desde un archivo .env.
"""

from __future__ import annotations

import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_env_file(path: Path | str = Path(".env")) -> None:
    """
    Carga pares clave=valor desde un archivo .env sin sobrescribir variables ya definidas.
    """
    env_path = Path(path)
    if not env_path.exists():
        return

    try:
        content = env_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not read env file '%s': %s", env_path, exc)
        return

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        parsed = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, parsed)


__all__ = ["load_env_file"]
