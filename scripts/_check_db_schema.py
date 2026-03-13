import sqlite3
import os

db_path = r'C:\Users\S.C.C\OneDrive\Desktop\jwala_gemini\outputs\guna_pipeline_state.db'
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(beat_state);")
    for row in cur.fetchall():
        print(row)
    conn.close()
