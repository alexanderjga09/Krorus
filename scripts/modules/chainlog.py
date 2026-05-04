"""Helper centralizado para acceder a la cadena de alertas (ChainLog)."""

from pathlib import Path

from chainlog_rs import ChainLog

_LOGS_PATH = str(Path(__file__).resolve().parent.parent.parent / "data" / "logs.json")


def get_chain_log() -> ChainLog:
    return ChainLog(_LOGS_PATH)
