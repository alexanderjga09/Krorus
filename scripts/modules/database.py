import logging
import shutil
import sqlite3 as sql
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "settings.db"
BACKUP_DIR = DB_PATH.parent / "backups"
MAX_BACKUPS = 5


def _ensure_db_dir():
    """Asegura que el directorio de la base de datos existe."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _ensure_backup_dir():
    """Asegura que el directorio de backups existe."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def _cleanup_old_backups():
    """Elimina backups antiguos, manteniendo solo los ultimos MAX_BACKUPS."""
    try:
        if not BACKUP_DIR.exists():
            return
        files = sorted(BACKUP_DIR.glob("settings_*.db"), key=lambda p: p.stat().st_mtime)
        for f in files[:-MAX_BACKUPS]:
            f.unlink()
            logger.info(f"[DB] Backup antiguo eliminado: {f.name}")
    except Exception as e:
        logger.warning(f"[DB] Error al limpiar backups: {e}")


def backup_db():
    """Crea un backup de la base de datos."""
    if not DB_PATH.exists():
        logger.warning("[DB] No hay DB para respaldar.")
        return False

    _ensure_backup_dir()
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = BACKUP_DIR / f"settings_{timestamp}.db"
        shutil.copy2(DB_PATH, backup_path)
        logger.info(f"[DB] Backup creado: {backup_path.name}")
        _cleanup_old_backups()
        return True
    except Exception as e:
        logger.exception(f"[DB] Error al crear backup: {e}")
        return False


def restore_latest_backup() -> bool:
    """Restaura el backup mas reciente."""
    if not BACKUP_DIR.exists():
        logger.warning("[DB] No hay backups para restaurar.")
        return False

    try:
        files = sorted(BACKUP_DIR.glob("settings_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            logger.warning("[DB] No hay archivos de backup.")
            return False

        latest = files[0]
        shutil.copy2(latest, DB_PATH)
        logger.info(f"[DB] Restaurado desde: {latest.name}")
        return True
    except Exception as e:
        logger.exception(f"[DB] Error al restaurar backup: {e}")
        return False


def create_table():
    """Crea la tabla de configuracion si no existe."""
    _ensure_db_dir()
    try:
        with sql.connect(str(DB_PATH)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS settings (staff_channel integer, role_id integer)"
            )
            cursor.execute("SELECT COUNT(*) FROM settings")
            if cursor.fetchone()[0] == 0:
                cursor.execute("INSERT INTO settings VALUES (0, 0)")
    except sql.OperationalError as e:
        logger.exception(f"Error creando tabla en DB: {e}")


def insert_row(staff_channel: int, role_id: int):
    """Inserta o actualiza la unica fila de configuracion."""
    create_table()
    backup_db()
    try:
        with sql.connect(str(DB_PATH)) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM settings")
            cursor.execute(
                "INSERT INTO settings VALUES (?, ?)", (staff_channel, role_id)
            )
    except sql.OperationalError as e:
        logger.exception(f"Error en la base de datos: {e}")


def read_row():
    """Lee la configuracion actual. Devuelve [(channel, role)] o [(0, 0)]."""
    create_table()
    try:
        with sql.connect(str(DB_PATH)) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM settings")
            rows = cursor.fetchall()
            return rows if rows else [(0, 0)]
    except sql.OperationalError as e:
        logger.exception(f"Error leyendo DB: {e}")
        return [(0, 0)]


def try_read_row() -> tuple:
    """Lee la configuracion de forma segura, creando la tabla si es necesario."""
    try:
        rows = read_row()
        return rows[0]
    except Exception as e:
        logger.exception(f"Error obteniendo fila de configuracion: {e}")
        create_table()
        return (0, 0)
