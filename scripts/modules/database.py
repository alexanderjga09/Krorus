import logging
import sqlite3 as sql
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "settings.db"


def createDB():
    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sql.connect(str(DB_PATH))
        conn.commit()
        conn.close()
    except sql.OperationalError as e:
        logger.exception(f"Error creando DB: {e}")
        return


def createTable():
    createDB()
    try:
        conn = sql.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS settings (staff_channel integer, role_id integer)"
        )
        cursor.execute("SELECT COUNT(*) FROM settings")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO settings VALUES (0, 0)")
        conn.commit()
        conn.close()
    except sql.OperationalError as e:
        logger.exception(f"Error creando tabla en DB: {e}")
        return


def insertRow(staff_channel, role_id):
    createTable()
    try:
        with sql.connect(str(DB_PATH)) as conn:
            cursor = conn.cursor()
            # Limpiamos la tabla para mantener solo una fila de configuración
            cursor.execute("DELETE FROM settings")
            cursor.execute(
                "INSERT INTO settings VALUES (?, ?)", (staff_channel, role_id)
            )
            conn.commit()
    except sql.OperationalError as e:
        logger.exception(f"Error en la base de datos: {e}")


def readRow():
    try:
        with sql.connect(str(DB_PATH)) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM settings")
            rows = cursor.fetchall()
            return rows if rows else [(0, 0)]
    except sql.OperationalError as e:
        logger.exception(f"Error leyendo DB: {e}")
        createTable()
        return [(0, 0)]


def try_read_row():
    try:
        rows = readRow()
        return rows[0]
    except Exception as e:
        logger.exception(f"Error obteniendo fila de configuración: {e}")
        createTable()
        return (0, 0)
