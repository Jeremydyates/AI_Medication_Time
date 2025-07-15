import tkinter as tk
from tkinter import messagebox
import sqlite3
import json
import os
import importlib.util
import subprocess
import sys

DB_PATH = 'medication_time_db.db'

def create_database_and_launch_app(user_inputs):
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            medication_data TEXT
        );
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS user_journals (
            entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            date TEXT,
            journal_text TEXT
        );
    ''')

    for first_name, last_name in user_inputs:
        if not first_name.strip() or not last_name.strip():
            continue

        sample_med = [{
            "medication_name": f"{first_name[:3]}Med",
            "doctor_name": "Dr. Example",
            "date_prescribed": "2022-01-01",
            "stop_after_date": "2026-01-01",
            "dosage_instructions": "Take 1 pill daily.",
            "stock": 30,
            "scheduled_times": ["08:00"]
        }]
        c.execute('INSERT INTO users (first_name, last_name, medication_data) VALUES (?, ?, ?);',
                  (first_name.strip(), last_name.strip(), json.dumps(sample_med)))

    conn.commit()
    conn.close()
    messagebox.showinfo("Success", "Database created. Launching Medication App...")
    root.destroy()

    # ✅ Launch your main app (change the filename as needed)
    subprocess.Popen(["MedicationTime.exe"], shell=True)

# ---------- GUI Setup ----------
root = tk.Tk()
root.title("Initialize Medication Database")
root.geometry("400x250")

frame = tk.Frame(root)
frame.pack(pady=10)

tk.Label(frame, text="No.", font=("Helvetica", 10, "bold")).grid(row=0, column=0, padx=5)
tk.Label(frame, text="First name", font=("Helvetica", 10, "bold")).grid(row=0, column=1, padx=5)
tk.Label(frame, text="Last name", font=("Helvetica", 10, "bold")).grid(row=0, column=2, padx=5)

entries = []
for i in range(4):
    tk.Label(frame, text=f"{i+1}.").grid(row=i+1, column=0, padx=5, pady=2)
    first = tk.Entry(frame)
    last = tk.Entry(frame)
    first.grid(row=i+1, column=1, padx=5, pady=2)
    last.grid(row=i+1, column=2, padx=5, pady=2)
    entries.append((first, last))

tk.Button(root, text="Create Database and Launch App", font=("Helvetica", 12, "bold"),
          command=lambda: create_database_and_launch_app([(f.get(), l.get()) for f, l in entries])).pack(pady=10)

root.mainloop()
