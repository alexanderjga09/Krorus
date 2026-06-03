"""Helper centralizado para acceder a la cadena de alertas (ChainLog)."""

from pathlib import Path

from chainlog_rs import ChainLog

_LOGS_PATH = str(Path(__file__).resolve().parent.parent.parent / "data" / "logs.json")


def get_chain_log() -> ChainLog:
    """Devuelve una instancia de ChainLog releyendo el archivo desde disco.

    Importante: se crea una instancia nueva (que reparsea ``logs.json``) en cada
    llamada de forma deliberada. La cadena es un log append-only con integridad
    verificable, y ``/verify-chain`` debe poder detectar manipulaciones hechas
    directamente sobre el fichero. Cachear una única instancia en memoria
    ocultaría esas ediciones externas y anularía la detección de tampering.

    Como dentro del proceso del bot toda operación lectura→escritura ocurre sin
    ``await`` intermedio, no hay riesgo de lost-update por el bucle de asyncio.
    El coste de reparsear es asumible dado el volumen de moderación.
    """
    return ChainLog(_LOGS_PATH)
