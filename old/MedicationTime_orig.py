import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
import sqlite3
import json
from datetime import datetime, timedelta
from tkcalendar import DateEntry
import threading
import time
import pygame  # <-- Import pygame for playing MP3
import os
from fpdf import FPDF
import platform
import subprocess

DB_PATH = 'medication_time_db.db'
SETTINGS_PATH = 'settings.json'
alerted_today = set()

# ---------- Setup Database Tables ----------
def setup_tables():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            medication_data TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS user_journals (
            entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            date TEXT,
            journal_text TEXT
        )
    ''')

    # Sample users (if empty)
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        sample_users = [
            ('R', 'Y', json.dumps([{
                "medication_name": "Med1",
                "doctor_name": "Dr. A",
                "date_prescribed": "2022-10-01",
                "stop_after_date": "2026-01-01",
                "dosage_instructions": "Take 2 pills every morning.",
                "stock": 30,
                "scheduled_times": ["08:00"]
            }]))
        ]
        for first, last, meds in sample_users:
            c.execute('INSERT INTO users (first_name, last_name, medication_data) VALUES (?, ?, ?);',
                      (first, last, meds))

    conn.commit()
    conn.close()

# ---------- Settings Management ----------
def load_settings():
    if os.path.exists(SETTINGS_PATH):
        with open(SETTINGS_PATH, 'r') as f:
            return json.load(f)
    return {"volume": 0.5}

def save_settings(settings):
    with open(SETTINGS_PATH, 'w') as f:
        json.dump(settings, f)

# ---------- Initialize Audio Playback ----------
settings = load_settings()
pygame.mixer.init()
pygame.mixer.music.set_volume(settings.get("volume", 0.5))

def play_alert_sound():
    try:
        if os.path.exists("MedicationTime.mp3"):
            pygame.mixer.music.load("MedicationTime.mp3")
            pygame.mixer.music.play()
        else:
            print("MedicationTime.mp3 file not found.")
    except Exception as e:
        print("Error playing sound:", e)


class MedicationApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Yates Family Medication Schedule,         Select a family member to begin.")
        self.root.geometry("600x850")

        self.db_path = DB_PATH
        self.users = self.fetch_users()
        self.volume_level = tk.DoubleVar(value=settings.get("volume", 0.5))
        self.filter_text = tk.StringVar()
        self.current_user = None

        self.create_widgets()
        self.start_alert_thread()

    def create_widgets(self):
        title_label = tk.Label(self.root, text="Medication Time", font=("Helvetica", 20, "bold"))
        title_label.pack(pady=10)

        volume_frame = tk.Frame(self.root)
        volume_frame.pack(side=tk.TOP, pady=5)
        tk.Label(volume_frame, text="Alert Volume").pack(side=tk.LEFT)
        volume_slider = tk.Scale(volume_frame, from_=0, to=1, resolution=0.05,
                                orient=tk.HORIZONTAL, variable=self.volume_level,
                                command=self.set_volume)
        volume_slider.pack(side=tk.LEFT)
        tk.Button(volume_frame, text="Test Sound", command=play_alert_sound).pack(side=tk.LEFT, padx=10)

        button_frame = tk.Frame(self.root)
        button_frame.pack()

        for user in self.users:
            btn = tk.Button(button_frame, text=user[1], font=("Helvetica", 20, "bold"),
                            command=lambda u=user: self.show_user_data(u))
            btn.pack(side=tk.LEFT, padx=20)

        # ✅ Add the Medication Editor button above scrollable meds
        editor_frame = tk.Frame(self.root)
        editor_frame.pack(pady=(10, 0))

        tk.Button(editor_frame, text="Add Medication", font=("Helvetica", 12, "bold"),
                command=self.open_medication_editor).pack(side=tk.LEFT, padx=5)

        tk.Button(editor_frame, text="Add Journal Entry", font=("Helvetica", 12, "bold"),
                command=self.add_journal_entry).pack(side=tk.LEFT, padx=5)

        tk.Button(editor_frame, text="View Journals", font=("Helvetica", 12, "bold"),
                command=self.view_journals).pack(side=tk.LEFT, padx=5)


        search_frame = tk.Frame(self.root)
        search_frame.pack(pady=5)
        tk.Label(search_frame, text="Search Medications:").pack(side=tk.LEFT)
        search_entry = tk.Entry(search_frame, textvariable=self.filter_text)
        search_entry.pack(side=tk.LEFT)
        search_entry.bind("<KeyRelease>", lambda event: self.show_user_data(self.current_user))

        self.scroll_frame = tk.Frame(self.root)
        self.scroll_frame.pack(fill=tk.BOTH, expand=True)

        # Create a centered container inside scroll_frame
        canvas_container = tk.Frame(self.scroll_frame)
        canvas_container.pack(anchor="center", pady=10)

        # Set fixed width for canvas if needed (adjust width as necessary)
        canvas_width = 500
        canvas_height = 500  # Or any height you want
        self.canvas = tk.Canvas(canvas_container, width=canvas_width, height=canvas_height)
        self.scrollbar = ttk.Scrollbar(canvas_container, orient="vertical", command=self.canvas.yview)

        self.scrollable_frame = tk.Frame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # ✅ Add this after canvas is set up
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", self._on_mousewheel)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel)

    def _on_mousewheel(self, event):
        if event.num == 4:   # Linux scroll up
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5: # Linux scroll down
            self.canvas.yview_scroll(1, "units")
        else:  # Windows and Mac
            self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def set_volume(self, value):
        volume = float(value)
        pygame.mixer.music.set_volume(volume)
        save_settings({"volume": volume})

    def fetch_users(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT user_id, first_name, last_name, medication_data FROM users")
        users = c.fetchall()
        conn.close()
        return users

    def add_journal_entry(self):
        if not self.current_user:
            messagebox.showwarning("No User Selected", "Please select a user first.")
            return

        entry_win = tk.Toplevel(self.root)
        entry_win.title("Journal Entry")
        entry_win.geometry("400x300")

        tk.Label(entry_win, text="How are you feeling today?").pack(pady=5)

        text_box = tk.Text(entry_win, height=10, wrap=tk.WORD)
        text_box.pack(expand=True, fill=tk.BOTH, padx=10, pady=5)

        def save_entry():
            entry_text = text_box.get("1.0", tk.END).strip()
            if entry_text:
                conn = sqlite3.connect(self.db_path)
                c = conn.cursor()
                c.execute("INSERT INTO user_journals (user_id, date, journal_text) VALUES (?, ?, ?)",
                        (self.current_user[0], datetime.now().strftime("%Y-%m-%d"), entry_text))
                conn.commit()
                conn.close()
                messagebox.showinfo("Saved", "Journal entry saved.")
                entry_win.destroy()
            else:
                messagebox.showwarning("Empty Entry", "Please enter some text before saving.")

        tk.Button(entry_win, text="Save Entry", command=save_entry).pack(pady=10)


    def view_journals(self):
        if not self.current_user:
            messagebox.showwarning("No User Selected", "Please select a user first.")
            return

        window = tk.Toplevel(self.root)
        window.title("View Journal Entries")
        window.geometry("400x600")

        tk.Label(window, text="Start Date:").pack()
        start_date = DateEntry(window)
        start_date.set_date(datetime.now() - timedelta(days=30))
        start_date.pack()

        tk.Label(window, text="End Date:").pack()
        end_date = DateEntry(window)
        end_date.set_date(datetime.now())
        end_date.pack()

        result_box = tk.Text(window, wrap=tk.WORD)
        result_box.pack(expand=True, fill=tk.BOTH, pady=10)

        def fetch_entries():
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("""
                SELECT date, journal_text FROM user_journals
                WHERE user_id = ? AND date BETWEEN ? AND ?
                ORDER BY date
            """, (
                self.current_user[0],
                start_date.get_date().strftime("%Y-%m-%d"),
                end_date.get_date().strftime("%Y-%m-%d")
            ))
            entries = c.fetchall()
            conn.close()
            result_box.delete("1.0", tk.END)
            if entries:
                for entry in entries:
                    result_box.insert(tk.END, f"{entry[0]}:\n{entry[1]}\n\n")
            else:
                result_box.insert(tk.END, "No entries found in this range.\n")

        def export_entries():
            date_str = datetime.now().strftime("%m-%d-%Y")
            filename = f"{self.current_user[1]}-Journal-{date_str}.pdf"
            file_path = filedialog.asksaveasfilename(defaultextension=".pdf", initialfile=filename,
                                                    filetypes=[("PDF Files", "*.pdf")])
            if not file_path:
                return

            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()

            # Fetch medications
            c.execute("SELECT medication_data FROM users WHERE user_id = ?", (self.current_user[0],))
            meds_json = c.fetchone()[0]
            meds = json.loads(meds_json) if meds_json else []

            # Fetch journal entries
            c.execute("""
                SELECT date, journal_text FROM user_journals
                WHERE user_id = ? AND date BETWEEN ? AND ?
                ORDER BY date
            """, (
                self.current_user[0],
                start_date.get_date().strftime("%Y-%m-%d"),
                end_date.get_date().strftime("%Y-%m-%d")
            ))
            entries = c.fetchall()
            conn.close()

            from reportlab.lib.pagesizes import letter
            from reportlab.pdfgen import canvas
            from reportlab.lib.units import inch

            c = canvas.Canvas(file_path, pagesize=letter)
            width, height = letter
            x_margin = inch
            y = height - inch

            def write_line(text, font_size=12, bold=False):
                nonlocal y
                if y < inch:
                    c.showPage()
                    y = height - inch
                font = "Helvetica-Bold" if bold else "Helvetica"
                c.setFont(font, font_size)
                c.drawString(x_margin, y, text)
                y -= 14

            # Header
            write_line(f"{self.current_user[1]} {self.current_user[2]} - Medication Summary", 16, bold=True)
            write_line("")

            for m in meds:
                write_line(f"Medication: {m.get('medication_name', 'N/A')}", 12, bold=True)
                write_line(f"Prescribed by: {m.get('doctor_name', 'N/A')}")
                write_line(f"Date Prescribed: {m.get('date_prescribed', 'N/A')}")
                write_line(f"Instructions: {m.get('dosage_instructions', 'N/A')}")
                write_line("")

            write_line("Journal Entries", 16, bold=True)
            write_line("")

            if entries:
                for entry in entries:
                    write_line(f"{entry[0]}", 12, bold=True)
                    for line in entry[1].splitlines():
                        write_line(line.strip())
                    write_line("")
            else:
                write_line("No journal entries found in selected date range.")

            c.save()
            messagebox.showinfo("Exported", f"Journal PDF saved as:\n{file_path}")

            try:
                if platform.system() == "Windows":
                    os.startfile(file_path)
                elif platform.system() == "Darwin":
                    subprocess.run(["open", file_path])
                else:
                    subprocess.run(["xdg-open", file_path])
            except Exception as e:
                print(f"Could not open PDF automatically: {e}")


        button_frame = tk.Frame(window)
        button_frame.pack(pady=5)
        tk.Button(button_frame, text="Refresh this List", command=fetch_entries).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Create PDF Report", command=export_entries).pack(side=tk.LEFT, padx=5)

        fetch_entries()

           
    
    def open_medication_editor(self):
        if not self.current_user:
            messagebox.showwarning("No User Selected", "Select a user first.")
            return

        editor = tk.Toplevel(self.root)
        editor.title("Add New Medication")
        editor.geometry("500x600")

        tk.Label(editor, text="Medication Name:", font=("Helvetica", 18)).pack()
        name_entry = tk.Entry(editor, font=("Helvetica", 18))
        name_entry.pack()

        tk.Label(editor, text="Doctor Name:", font=("Helvetica", 18)).pack()
        doctor_entry = tk.Entry(editor, font=("Helvetica", 18))
        doctor_entry.pack()

        tk.Label(editor, text="Date Prescribed:", font=("Helvetica", 18)).pack()
        date_entry = DateEntry(editor, font=("Helvetica", 18), date_pattern="mm-dd-yyyy")
        date_entry.set_date(datetime.today())
        date_entry.pack()

        tk.Label(editor, text="Stop After Date (optional):", font=("Helvetica", 18)).pack()
        stop_entry = tk.Entry(editor, justify="center", font=("Helvetica", 18))
        stop_entry.pack()
        stop_entry.insert(0, "MM-DD-YYYY")

        def clear_placeholder(e):
            if stop_entry.get() == "MM-DD-YYYY":
                stop_entry.delete(0, tk.END)
        stop_entry.bind("<FocusIn>", clear_placeholder)

        tk.Label(editor, text="Dosage Instructions:", font=("Helvetica", 18)).pack()
        dosage_var = tk.StringVar(value="once per day")
        dosage_options = ["once per day", "twice daily", "three times daily"]
        dosage_combobox = ttk.Combobox(editor, textvariable=dosage_var, values=dosage_options, state="readonly",
                                    font=("Helvetica", 16))
        dosage_combobox.pack()

        tk.Label(editor, text="Select time(s) for doses:", font=("Helvetica", 18)).pack()
        time_vars = {"9 AM": tk.IntVar(), "3:30 PM": tk.IntVar(), "9 PM": tk.IntVar(), "3:30 AM": tk.IntVar()}
        time_frame = tk.Frame(editor)
        time_frame.pack(pady=5)

        for label in time_vars:
            chk = tk.Checkbutton(time_frame, text=label, variable=time_vars[label], font=("Helvetica", 16))
            chk.pack(side=tk.LEFT, padx=10)

        tk.Label(editor, text="Quantity on-hand:", font=("Helvetica", 18)).pack()
        stock_entry = tk.Entry(editor, font=("Helvetica", 18))
        stock_entry.pack()

        def save_medication():
            scheduled = []
            if time_vars["9 AM"].get(): scheduled.append("09:00")
            if time_vars["3:30 PM"].get(): scheduled.append("15:30")
            if time_vars["9 PM"].get(): scheduled.append("21:00")
            if time_vars["3:30 AM"].get(): scheduled.append("03:30")

            raw_stop = stop_entry.get().strip()
            stop_after_date = None
            if raw_stop and raw_stop != "MM-DD-YYYY":
                try:
                    parsed_date = datetime.strptime(raw_stop, "%m-%d-%Y")
                    stop_after_date = parsed_date.date().isoformat()
                except ValueError:
                    messagebox.showerror("Invalid Date", "Please enter Stop After Date in MM-DD-YYYY format.")
                    return

            med = {
                "medication_name": name_entry.get(),
                "doctor_name": doctor_entry.get(),
                "date_prescribed": date_entry.get(),
                "stop_after_date": stop_after_date,
                "dosage_instructions": dosage_var.get(),
                "stock": int(stock_entry.get() or 0),
                "scheduled_times": scheduled
            }

            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            user_id = self.current_user[0]
            c.execute("SELECT medication_data FROM users WHERE user_id = ?", (user_id,))
            raw = c.fetchone()
            data = json.loads(raw[0]) if raw and raw[0] else []
            data.append(med)
            c.execute("UPDATE users SET medication_data = ? WHERE user_id = ?", (json.dumps(data), user_id))
            conn.commit()
            conn.close()
            editor.destroy()
            self.users = self.fetch_users()
            self.show_user_data(self.current_user)

        tk.Button(editor, text="Save Medication", font=("Helvetica", 18), command=save_medication).pack(pady=10)


    def show_user_data(self, user):
        self.current_user = user
        self.users = self.fetch_users()
        user = next((u for u in self.users if u[0] == user[0]), user)

        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()

        meds = json.loads(user[3])
        
        # Centered container
        container = tk.Frame(self.scrollable_frame)
        container.pack(anchor="center", pady=10)

        tk.Label(container, text=f"Prescriptions for: {user[1]} {user[2]}",
                font=("Helvetica", 24, "bold")).pack(pady=10)

        filter_val = self.filter_text.get().lower()

        label_map = {
            "medication_name": "Medication",
            "doctor_name": "Doctor",
            "date_prescribed": "Prescribed on",
            "stop_after_date": "End Medication on",
            "dosage_instructions": "Instructions",
            "stock": "Doses Remaining",
            "scheduled_times": "Scheduled for"
        }

        for i, m in enumerate(meds):
            if filter_val and filter_val not in m.get("medication_name", "").lower():
                continue

            med_text = "\n".join([
                f"{label_map.get(k, k)}: {v}"
                for k, v in m.items()
            ])

            frame = tk.Frame(container, borderwidth=1, relief="solid", padx=10, pady=5)
            tk.Label(frame, text=med_text, justify="left", font=("Courier", 10)).pack(anchor="w")

            button_frame = tk.Frame(frame)
            button_frame.pack(pady=5)
            
            stock_btn = tk.Button(button_frame, text="Modify Stock", command=lambda idx=i: self.modify_stock(idx))
            stock_btn.pack(side=tk.LEFT, padx=5)

            del_btn = tk.Button(button_frame, text="Delete Medication", command=lambda idx=i: self.delete_medication(idx))
            del_btn.pack(side=tk.LEFT, padx=5)

            frame.pack(pady=10)
        self.check_stock_levels()    

    def check_stock_levels(self):
        alerts = []

        for user in self.users:
            user_id = user[0]
            user_name = f"{user[1]} {user[2]}"
            try:
                medications = json.loads(user[3])
            except Exception as e:
                continue

            for med in medications:
                stock = med.get("stock", 0)
                scheduled_times = med.get("scheduled_times", [])
                doses_per_day = len(scheduled_times)

                if doses_per_day == 0:
                    continue  # Avoid divide-by-zero

                days_left = stock // doses_per_day

                stop_date_str = med.get("stop_after_date")
                stop_date = None
                if stop_date_str:
                    try:
                        stop_date = datetime.strptime(stop_date_str, "%Y-%m-%d").date()
                    except:
                        pass

                today = datetime.today().date()

                # Only alert if days left < 5 AND medication isn’t ending within 5 days
                if days_left < 5 and (not stop_date or (stop_date - today).days > 5):
                    alerts.append(f"{user_name} is running low on {med.get('medication_name')} ({days_left} days left)")

        if alerts:
            alert_win = tk.Toplevel(self.root)
            alert_win.title("Low Medication Stock")
            alert_win.geometry("500x300")
            alert_win.attributes("-topmost", True)

            tk.Label(alert_win, text="Low Medication Stock Alert", font=("Helvetica", 20, "bold")).pack(pady=10)

            text_frame = tk.Frame(alert_win)
            text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

            alert_text = tk.Text(text_frame, wrap=tk.WORD, font=("Helvetica", 16), height=10)
            alert_text.pack(fill=tk.BOTH, expand=True)

            alert_text.insert(tk.END, "\n\n".join(alerts))
            alert_text.config(state=tk.DISABLED)

            tk.Button(alert_win, text="Close", font=("Helvetica", 14), command=alert_win.destroy).pack(pady=10)

    def delete_medication(self, index):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        user_id = self.current_user[0]
        c.execute("SELECT medication_data FROM users WHERE user_id = ?", (user_id,))
        data = json.loads(c.fetchone()[0])
        if 0 <= index < len(data):
            del data[index]
            c.execute("UPDATE users SET medication_data = ? WHERE user_id = ?", (json.dumps(data), user_id))
        conn.commit()
        conn.close()
        self.users = self.fetch_users()
        self.show_user_data(self.current_user)

    def modify_stock(self, index):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        user_id = self.current_user[0]
        c.execute("SELECT medication_data FROM users WHERE user_id = ?", (user_id,))
        data = json.loads(c.fetchone()[0])
        if 0 <= index < len(data):
            new_stock = simpledialog.askinteger("Modify Stock", "Enter new stock quantity:", initialvalue=data[index].get("stock", 0))
            if new_stock is not None:
                data[index]["stock"] = new_stock
                c.execute("UPDATE users SET medication_data = ? WHERE user_id = ?", (json.dumps(data), user_id))
                conn.commit()
        conn.close()
        self.users = self.fetch_users()
        self.show_user_data(self.current_user)

    def start_alert_thread(self):
        last_reset_day = [datetime.now().date()]  # wrap in list for mutability inside thread
        def check_alerts():
            print("[DEBUG] Alert thread started")
            while True:
                now = datetime.now()
                now_str = now.strftime("%H:%M")
                today_key = now.strftime("%Y-%m-%d")

                self.users = self.fetch_users()
                for user in self.users:
                    user_id, fname, _, med_data_json = user
                    try:
                        meds = json.loads(med_data_json)
                    except:
                        continue
                    for idx, med in enumerate(meds):
                        times = med.get("scheduled_times", [])
                        for t in times:
                            try:
                                med_time = datetime.strptime(t, "%H:%M").replace(year=now.year, month=now.month, day=now.day)
                                delta = abs((now - med_time).total_seconds())
                                key = f"{today_key}-{user_id}-{idx}-{t}"
                                if delta < 61 and key not in alerted_today:
                                    print(f"[DEBUG] Alert match: {fname} - {med['medication_name']} at {t}")
                                    self.root.after(0, self.trigger_alert, med, fname, user_id, idx, key)
                            except Exception as e:
                                print(f"[DEBUG] Error parsing time '{t}':", e)
                time.sleep(60)


        threading.Thread(target=check_alerts, daemon=True).start()

    def trigger_alert(self, med, user_fname, user_id, med_index, alert_key):
        play_alert_sound()

        alert = tk.Toplevel(self.root)
        alert.title("Medication Alert")
        alert.geometry("300x300")
        alert.attributes("-topmost", True)
        alert.lift()

        offset_x = 50 * (len(alerted_today) % 5)
        offset_y = 50 * (len(alerted_today) // 5)
        x = self.root.winfo_x() + offset_x
        y = self.root.winfo_y() + offset_y
        alert.geometry(f"300x300+{x}+{y}")

        tk.Label(alert, text=f"Time for {user_fname} to take:", font=("Helvetica", 20)).pack(pady=10)
        tk.Label(alert, text=med['medication_name'], font=("Helvetica", 20, "bold")).pack(pady=10)
        tk.Label(alert, text=med.get('dosage_instructions', ""), wraplength=250).pack(pady=5)

        def taken():
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("SELECT medication_data FROM users WHERE user_id = ?", (user_id,))
            meds = json.loads(c.fetchone()[0])
            if 0 <= med_index < len(meds):
                meds[med_index]['stock'] = max(0, meds[med_index].get('stock', 0) - 1)
                c.execute("UPDATE users SET medication_data = ? WHERE user_id = ?", (json.dumps(meds), user_id))
            conn.commit()
            conn.close()
            alert.destroy()

        tk.Button(alert, text="Taken", command=taken).pack(pady=5)
        tk.Button(alert, text="Skip", command=lambda: [alerted_today.add(alert_key), alert.destroy()]).pack(pady=5)
        alerted_today.add(alert_key)

        

if __name__ == "__main__":
    setup_tables()
    root = tk.Tk()
    app = MedicationApp(root)
    root.mainloop()