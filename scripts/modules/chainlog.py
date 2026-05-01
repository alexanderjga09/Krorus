"""Helper centralizado para acceder a la cadena de alertas (ChainLog)."""

from pathlib import Path

from chainlog_rs import ChainLog

_LOGS_PATH = str(Path(__file__).resolve().parent.parent.parent / "data" / "logs.json")


def get_chain_log() -> ChainLog:
    """
    Devuelve una instancia de ChainLog apuntando al archivo de logs del proyecto.

    Usar este helper evita duplicar la ruta en cada cog/módulo y garantiza
    que todos apunten siempre al mismo archivo, sin importar desde dónde se llame.
    """
    return ChainLog(_LOGS_PATH)
