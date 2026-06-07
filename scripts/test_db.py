import sqlite3

# https://docs.python.org/3/library/sqlite3.html
# https://www.canva.com/design/DAHFGRheCFE/w_3h-2A4QpNVSaicDMByQg/edit
con = sqlite3.connect("../db/riseup.db")
cur = con.cursor()
cur.execute("""
    INSERT INTO Records VALUES
        (1, 'timur', 175, 860)
""")

con.commit()