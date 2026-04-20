import sqlite3 as sql


def createDB():
    try:
        conn = sql.connect("data/settings.db")
        conn.commit()
        conn.close()
    except sql.OperationalError:
        return


def createTable():
    try:
        conn = sql.connect("data/settings.db")
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE settings (staff_channel integer,role_id integer)")
        conn.commit()
        conn.close()
    except sql.OperationalError:
        return


def insertRow(staff_channel, role_id):
    try:
        with sql.connect("data/settings.db") as conn:
            cursor = conn.cursor()
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS settings (staff_channel integer, role_id integer)"
            )
            cursor.execute(
                "INSERT INTO settings VALUES (?, ?)", (staff_channel, role_id)
            )
            conn.commit()
    except sql.OperationalError as e:
        print(f"Error en la base de datos: {e}")


def readRow():
    with sql.connect("data/settings.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM settings")
        return cursor.fetchall()


def try_read_row():
    try:
        return readRow()[0]
    except Exception:
        createDB()
        createTable()
        return None
