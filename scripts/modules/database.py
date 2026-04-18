import sqlite3 as sql


def createDB():
    try:
        conn = sql.connect("settings.db")
        conn.commit()
        conn.close()
    except sql.OperationalError:
        return


def createTable():
    try:
        conn = sql.connect("settings.db")
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE settings (staff_channel integer,role_id integer)")
        conn.commit()
        conn.close()
    except sql.OperationalError:
        return


def insertRow(staff_channel, role_id):
    conn = sql.connect("settings.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO settings (staff_channel, role_id) VALUES (?, ?)",
        (staff_channel, role_id),
    )
    conn.commit()
    conn.close()


def readRow():
    conn = sql.connect("settings.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM settings")
    row = cursor.fetchall()
    conn.commit()
    conn.close()
    return row
