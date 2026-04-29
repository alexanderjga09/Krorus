import os
import sqlite3 as sql


def createDB():
    try:
        if not os.path.exists("data"):
            os.makedirs("data")
        conn = sql.connect("data/settings.db")
        conn.commit()
        conn.close()
    except sql.OperationalError:
        return


def createTable():
    createDB()
    try:
        conn = sql.connect("data/settings.db")
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS settings (staff_channel integer, role_id integer)"
        )
        # Insertamos valores por defecto si la tabla está recién creada y vacía
        cursor.execute("SELECT COUNT(*) FROM settings")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO settings VALUES (0, 0)")
        conn.commit()
        conn.close()
    except sql.OperationalError:
        return


def insertRow(staff_channel, role_id):
    createTable()
    try:
        with sql.connect("data/settings.db") as conn:
            cursor = conn.cursor()
            # Limpiamos la tabla para mantener solo una fila de configuración
            cursor.execute("DELETE FROM settings")
            cursor.execute(
                "INSERT INTO settings VALUES (?, ?)", (staff_channel, role_id)
            )
            conn.commit()
    except sql.OperationalError as e:
        print(f"Error en la base de datos: {e}")


def readRow():
    try:
        with sql.connect("data/settings.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM settings")
            rows = cursor.fetchall()
            return rows if rows else [(0, 0)]
    except sql.OperationalError:
        createTable()
        return [(0, 0)]


def try_read_row():
    try:
        rows = readRow()
        return rows[0]
    except Exception:
        createTable()
        return (0, 0)
