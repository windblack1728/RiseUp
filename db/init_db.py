import sqlite3

connection = sqlite3.connect('riseup.db')


with open('schema.sql') as f:
    connection.executescript(f.read())

cur = connection.cursor()

cur.execute("INSERT INTO Children (name,birthday,gender,height) VALUES (?, ?, ?, ?)",
            ('name', '1/1/2025', 'male', 80)
            )

cur.execute("INSERT INTO Records (child_id, height, date) VALUES (?,?,?)",
            (1, 80, '6/7/2026')
            )

connection.commit()
connection.close()