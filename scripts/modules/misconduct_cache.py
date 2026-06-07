import json
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_MISCONDUCT_CACHE: dict[str, dict] = {}
_MISCONDUCT_CACHE_MAX = 512
_MISCONDUCT_CACHE_TTL = 300
_DATA_DIR = Path(__file__).parent.parent.parent / "data"
_MISCONDUCT_CACHE_PATH = _DATA_DIR / "misconduct_cache.json"
_MISCONDUCT_STATS_PATH = _DATA_DIR / "misconduct_cache_stats.json"
_MISCONDUCT_CACHE_HITS = 0
_MISCONDUCT_CACHE_MISSES = 0


def _load_misconduct_cache() -> dict[str, dict]:
    path = _MISCONDUCT_CACHE_PATH
    if not path.exists():
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
        data: dict = json.loads(raw)
        now = time.time()
        valid = {
            k: v
            for k, v in data.items()
            if isinstance(v, dict)
            and "result" in v
            and "ts" in v
            and now - v["ts"] < _MISCONDUCT_CACHE_TTL
        }
        if len(valid) < len(data):
            _save_misconduct_cache(valid)
        return valid
    except Exception as e:
        logger.warning(f"[Cache] Error cargando misconduct_cache.json: {e}")
        return {}


def _save_misconduct_cache(cache: dict[str, dict]) -> None:
    try:
        _MISCONDUCT_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _MISCONDUCT_CACHE_PATH.write_text(
            json.dumps(cache, indent=2), encoding="utf-8"
        )
    except Exception as e:
        logger.warning(f"[Cache] Error guardando misconduct_cache.json: {e}")


def _load_misconduct_stats() -> tuple[int, int]:
    path = _MISCONDUCT_STATS_PATH
    if not path.exists():
        return 0, 0
    try:
        data: dict = json.loads(path.read_text(encoding="utf-8"))
        return int(data.get("hits", 0)), int(data.get("misses", 0))
    except Exception as e:
        logger.warning(f"[Cache] Error cargando misconduct_cache_stats.json: {e}")
        return 0, 0


def _save_misconduct_stats() -> None:
    try:
        _MISCONDUCT_STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _MISCONDUCT_STATS_PATH.write_text(
            json.dumps(
                {"hits": _MISCONDUCT_CACHE_HITS, "misses": _MISCONDUCT_CACHE_MISSES},
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning(f"[Cache] Error guardando misconduct_cache_stats.json: {e}")


def record_cache_hit() -> None:
    """Registra un acierto de caché y lo persiste a disco.

    La persistencia permite que otro proceso (p. ej. la GUI) lea las
    estadísticas reales en lugar de su copia local, que siempre sería 0.
    """
    global _MISCONDUCT_CACHE_HITS
    _MISCONDUCT_CACHE_HITS += 1
    _save_misconduct_stats()


def record_cache_miss() -> None:
    """Registra un fallo de caché y lo persiste a disco."""
    global _MISCONDUCT_CACHE_MISSES
    _MISCONDUCT_CACHE_MISSES += 1
    _save_misconduct_stats()


def get_misconduct_cache_stats() -> dict:
    # Recarga desde disco para que un proceso distinto al del bot (la GUI)
    # vea los valores reales escritos por el bot, no su copia en memoria.
    global _MISCONDUCT_CACHE, _MISCONDUCT_CACHE_HITS, _MISCONDUCT_CACHE_MISSES
    _MISCONDUCT_CACHE = _load_misconduct_cache()
    _MISCONDUCT_CACHE_HITS, _MISCONDUCT_CACHE_MISSES = _load_misconduct_stats()
    return {
        "size": len(_MISCONDUCT_CACHE),
        "max_size": _MISCONDUCT_CACHE_MAX,
        "ttl_seconds": _MISCONDUCT_CACHE_TTL,
        "hits": _MISCONDUCT_CACHE_HITS,
        "misses": _MISCONDUCT_CACHE_MISSES,
    }


def clear_misconduct_cache() -> None:
    global _MISCONDUCT_CACHE, _MISCONDUCT_CACHE_HITS, _MISCONDUCT_CACHE_MISSES
    _MISCONDUCT_CACHE = {}
    _MISCONDUCT_CACHE_HITS = 0
    _MISCONDUCT_CACHE_MISSES = 0
    _save_misconduct_cache({})
    _save_misconduct_stats()


_MISCONDUCT_CACHE = _load_misconduct_cache()
_MISCONDUCT_CACHE_HITS, _MISCONDUCT_CACHE_MISSES = _load_misconduct_stats()
