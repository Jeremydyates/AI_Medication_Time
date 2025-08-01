import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from PIL import Image, ImageTk
from PIL.Image import Resampling
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

# ---------- Helper Functions for Extended Dosage Logic ----------
def should_alert_today(med, current_date):
    """
    Determine if medication should alert today based on dosage frequency
    """
    dosage = med.get("dosage_instructions", "once per day")
    prescribed_date_str = med.get("date_prescribed")
    
    if not prescribed_date_str:
        return True  # Default to daily if no start date
    
    try:
        # Parse prescribed date - handle both YYYY-MM-DD and MM-DD-YYYY formats
        if len(prescribed_date_str) == 10 and prescribed_date_str.count('-') == 2:
            parts = prescribed_date_str.split('-')
            if len(parts[0]) == 4 and parts[0].isdigit():
                # YYYY-MM-DD format
                prescribed_date = datetime.strptime(prescribed_date_str, "%Y-%m-%d").date()
            else:
                # MM-DD-YYYY format
                prescribed_date = datetime.strptime(prescribed_date_str, "%m-%d-%Y").date()
        else:
            # Fallback to MM-DD-YYYY format
            prescribed_date = datetime.strptime(prescribed_date_str, "%m-%d-%Y").date()
    except Exception as e:
        print(f"[DEBUG] Error parsing prescribed date '{prescribed_date_str}': {e}")
        return True  # Default to daily if date parsing fails
    
    days_since_prescribed = (current_date - prescribed_date).days
    
    # Only process medications that have started (prescribed date <= current date)
    if days_since_prescribed < 0:
        print(f"[DEBUG] Medication not yet started: prescribed {prescribed_date}, current {current_date}")
        return False
    
    if dosage in ["once per day", "twice daily", "three times daily"]:
        return True  # Daily medications
    elif dosage == "every other day":
        # Alert on prescribed date and every other day after
        should_alert = days_since_prescribed % 2 == 0
        print(f"[DEBUG] Every other day check: {days_since_prescribed} days since prescribed, should alert: {should_alert}")
        return should_alert
    elif dosage == "once per week":
        # Alert on prescribed date and every 7 days after
        should_alert = days_since_prescribed % 7 == 0
        print(f"[DEBUG] Once per week check: {days_since_prescribed} days since prescribed, should alert: {should_alert}")
        return should_alert
    elif dosage == "once per month":
        # Alert on the same day of month as prescribed date
        should_alert = current_date.day == prescribed_date.day
        print(f"[DEBUG] Once per month check: prescribed day {prescribed_date.day}, current day {current_date.day}, should alert: {should_alert}")
        return should_alert
    
    return True  # Default to daily for unknown dosage instructions

def calculate_days_supply(stock, dosage_instructions, scheduled_times):
    """
    Calculate days of supply based on dosage instructions
    """
    doses_per_day = len(scheduled_times) if scheduled_times else 1
    
    if dosage_instructions == "every other day":
        return (stock * 2) // doses_per_day if doses_per_day > 0 else 0
    elif dosage_instructions == "once per week":
        return (stock * 7) // doses_per_day if doses_per_day > 0 else 0
    elif dosage_instructions == "once per month":
        return (stock * 30) // doses_per_day if doses_per_day > 0 else 0
    else:
        # Daily medications
        return stock // doses_per_day if doses_per_day > 0 else 0


class MedicationApp:
    def __init__(self, root):
            self.root = root
            self.root.title("Yates Family Medication Schedule,         Select a family member to begin.")
            self.root.iconbitmap("Med_Time_Icon.ico")
            self.root.geometry("600x850")        
            
            # Add this line to track active alert windows
            self.active_alert_count = 0
            # ✅ NEW: Track active alerts per user to prevent multiple alerts per user
            self.active_user_alerts = {}  # {user_id: alert_window}

            # Load and resize background image
            if os.path.exists("background.jpg"):
                bg_image = Image.open("background.jpg")
                bg_image = bg_image.resize((600, 850), Image.Resampling.LANCZOS)
                bg_photo = ImageTk.PhotoImage(bg_image)

                # Create background label
                bg_label = tk.Label(root, image=bg_photo)
                bg_label.image = bg_photo  # keep a reference!
                bg_label.place(x=0, y=0, relwidth=1, relheight=1)

            # Use a frame with transparent widgets or light background for clarity
            main_frame = tk.Frame(root, bg="#ffffff", bd=2)
            main_frame.place(relx=0.5, rely=0.02, anchor='n')
            
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
        tk.Label(volume_frame, text="Alert Volume", font=("Helvetica", 12, "bold")).pack(side=tk.LEFT)
        volume_slider = tk.Scale(volume_frame, from_=0, to=1, resolution=0.05,
                                orient=tk.HORIZONTAL, variable=self.volume_level,
                                command=self.set_volume)
        volume_slider.pack(side=tk.LEFT)
        tk.Button(volume_frame, text="Test Sound", font=("Helvetica", 12, "bold"), command=play_alert_sound).pack(side=tk.LEFT, padx=10)

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
        tk.Label(search_frame, text="Search Medications:", font=("Helvetica", 12, "bold")).pack(side=tk.LEFT)
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

        tk.Label(entry_win, text="How are you feeling today?", font=("Helvetica", 12, "bold")).pack(pady=5)

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

        tk.Button(entry_win, text="Save Entry", font=("Helvetica", 12, "bold"), command=save_entry).pack(pady=10)


    def view_journals(self):
        if not self.current_user:
            messagebox.showwarning("No User Selected", "Please select a user first.")
            return

        window = tk.Toplevel(self.root)
        window.title("View Journal Entries")
        window.geometry("400x600")

        tk.Label(window, text="Start Date:", font=("Helvetica", 12, "bold")).pack()
        start_date = DateEntry(window)
        start_date.set_date(datetime.now() - timedelta(days=30))
        start_date.pack()

        tk.Label(window, text="End Date:", font=("Helvetica", 12, "bold")).pack()
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
                write_line(f"Dosage Instructions: {m.get('dosage_instructions', 'N/A')}")  # ✅ Added this line
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

           
    
    def open_medication_editor(self, edit_index=None):
        """Open the medication editor. If edit_index is provided, edit that medication."""
        if not self.current_user:
            messagebox.showwarning("No User Selected", "Select a user first.")
            return

        # Get current medications
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        user_id = self.current_user[0]
        c.execute("SELECT medication_data FROM users WHERE user_id = ?", (user_id,))
        raw = c.fetchone()
        existing_meds = json.loads(raw[0]) if raw and raw[0] else []
        conn.close()

        # Check if we're editing an existing medication
        is_editing = edit_index is not None and 0 <= edit_index < len(existing_meds)
        existing_med = existing_meds[edit_index] if is_editing else {}

        editor = tk.Toplevel(self.root)
        editor.title("Edit Medication" if is_editing else "Add New Medication")
        editor.geometry("500x600")

        tk.Label(editor, text="Medication Name:", font=("Helvetica", 18)).pack()
        name_entry = tk.Entry(editor, font=("Helvetica", 18))
        name_entry.pack()
        if is_editing:
            name_entry.insert(0, existing_med.get("medication_name", ""))

        tk.Label(editor, text="Doctor Name:", font=("Helvetica", 18)).pack()
        doctor_entry = tk.Entry(editor, font=("Helvetica", 18))
        doctor_entry.pack()
        if is_editing:
            doctor_entry.insert(0, existing_med.get("doctor_name", ""))

        tk.Label(editor, text="Date Prescribed:", font=("Helvetica", 18)).pack()
        date_entry = DateEntry(editor, font=("Helvetica", 18), date_pattern="mm-dd-yyyy")
        if is_editing and existing_med.get("date_prescribed"):
            try:
                # Handle different date formats
                date_str = existing_med.get("date_prescribed")
                if len(date_str) == 10 and date_str.count('-') == 2:  # YYYY-MM-DD format
                    parsed_date = datetime.strptime(date_str, "%Y-%m-%d")
                else:  # MM-DD-YYYY format
                    parsed_date = datetime.strptime(date_str, "%m-%d-%Y")
                date_entry.set_date(parsed_date.date())
            except:
                date_entry.set_date(datetime.today())
        else:
            date_entry.set_date(datetime.today())
        date_entry.pack()

        tk.Label(editor, text="Stop After Date (optional):", font=("Helvetica", 18)).pack()
        stop_entry = tk.Entry(editor, justify="center", font=("Helvetica", 18))
        stop_entry.pack()
        
        # Pre-fill stop date if editing
        if is_editing and existing_med.get("stop_after_date"):
            try:
                stop_date_str = existing_med.get("stop_after_date")
                if stop_date_str:
                    # Convert from YYYY-MM-DD to MM-DD-YYYY for display
                    parsed_date = datetime.strptime(stop_date_str, "%Y-%m-%d")
                    display_date = parsed_date.strftime("%m-%d-%Y")
                    stop_entry.insert(0, display_date)
                else:
                    stop_entry.insert(0, "MM-DD-YYYY")
            except:
                stop_entry.insert(0, "MM-DD-YYYY")
        else:
            stop_entry.insert(0, "MM-DD-YYYY")

        def clear_placeholder(e):
            if stop_entry.get() == "MM-DD-YYYY":
                stop_entry.delete(0, tk.END)
        stop_entry.bind("<FocusIn>", clear_placeholder)

        tk.Label(editor, text="Dosage Instructions:", font=("Helvetica", 18)).pack()
        dosage_var = tk.StringVar()
        # ✅ MODIFIED: Extended dosage options
        dosage_options = [
            "once per day", 
            "twice daily", 
            "three times daily",
            "every other day",
            "once per week",
            "once per month"
        ]
        
        # Set current value if editing
        current_dosage = existing_med.get("dosage_instructions", "once per day") if is_editing else "once per day"
        dosage_var.set(current_dosage)
        
        dosage_combobox = ttk.Combobox(editor, textvariable=dosage_var, values=dosage_options, state="readonly",
                                    font=("Helvetica", 16))
        dosage_combobox.pack()

        tk.Label(editor, text="Select time(s) for doses:", font=("Helvetica", 18)).pack()
        time_vars = {"9 AM": tk.IntVar(), "3:30 PM": tk.IntVar(), "9 PM": tk.IntVar(), "3:30 AM": tk.IntVar()}
        
        # Pre-select times if editing
        if is_editing:
            existing_times = existing_med.get("scheduled_times", [])
            time_mapping = {"09:00": "9 AM", "15:30": "3:30 PM", "21:00": "9 PM", "03:30": "3:30 AM"}
            for time_24, time_label in time_mapping.items():
                if time_24 in existing_times:
                    time_vars[time_label].set(1)
        
        time_frame = tk.Frame(editor)
        time_frame.pack(pady=5)

        for label in time_vars:
            chk = tk.Checkbutton(time_frame, text=label, variable=time_vars[label], font=("Helvetica", 16))
            chk.pack(side=tk.LEFT, padx=10)

        tk.Label(editor, text="Quantity on-hand:", font=("Helvetica", 18)).pack()
        stock_entry = tk.Entry(editor, font=("Helvetica", 18))
        stock_entry.pack()
        if is_editing:
            stock_entry.insert(0, str(existing_med.get("stock", 0)))

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

            # ✅ FIXED: Store prescribed date in YYYY-MM-DD format for consistency
            prescribed_date = date_entry.get_date().isoformat()

            med = {
                "medication_name": name_entry.get(),
                "doctor_name": doctor_entry.get(),
                "date_prescribed": prescribed_date,  # Store in YYYY-MM-DD format
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
            
            if is_editing:
                # Update existing medication
                data[edit_index] = med
                messagebox.showinfo("Success", "Medication updated successfully!")
            else:
                # Add new medication
                data.append(med)
                messagebox.showinfo("Success", "Medication added successfully!")
            
            c.execute("UPDATE users SET medication_data = ? WHERE user_id = ?", (json.dumps(data), user_id))
            conn.commit()
            conn.close()
            editor.destroy()
            
            # ✅ REFRESH: Fetch updated data and refresh display
            self.users = self.fetch_users()
            if self.current_user:
                # Find the updated user data
                updated_user = next((u for u in self.users if u[0] == self.current_user[0]), self.current_user)
                self.show_user_data(updated_user)

        save_text = "Update Medication" if is_editing else "Save Medication"
        tk.Button(editor, text=save_text, font=("Helvetica", 18), command=save_medication).pack(pady=10)


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

            # ✅ IMPROVED: Better display formatting with date conversion
            display_med = {}
            for k, v in m.items():
                if k == "date_prescribed" and v:
                    # Convert YYYY-MM-DD to MM-DD-YYYY for display
                    try:
                        if len(v) == 10 and v.count('-') == 2:
                            parts = v.split('-')
                            if len(parts[0]) == 4:  # YYYY-MM-DD format
                                date_obj = datetime.strptime(v, "%Y-%m-%d")
                                display_med[k] = date_obj.strftime("%m-%d-%Y")
                            else:  # Already MM-DD-YYYY
                                display_med[k] = v
                        else:
                            display_med[k] = v
                    except:
                        display_med[k] = v
                elif k == "stop_after_date" and v:
                    # Convert YYYY-MM-DD to MM-DD-YYYY for display
                    try:
                        date_obj = datetime.strptime(v, "%Y-%m-%d")
                        display_med[k] = date_obj.strftime("%m-%d-%Y")
                    except:
                        display_med[k] = v
                elif k == "scheduled_times" and isinstance(v, list):
                    # Convert 24-hour times to 12-hour format for display
                    time_display = []
                    for time_str in v:
                        try:
                            time_obj = datetime.strptime(time_str, "%H:%M")
                            formatted_time = time_obj.strftime("%I:%M %p").lstrip('0')
                            time_display.append(formatted_time)
                        except:
                            time_display.append(time_str)
                    display_med[k] = ", ".join(time_display)
                else:
                    display_med[k] = v

            med_text = "\n".join([
                f"{label_map.get(k, k)}: {v}"
                for k, v in display_med.items()
                if k in label_map  # Only show mapped fields
            ])

            frame = tk.Frame(container, borderwidth=1, relief="solid", padx=10, pady=5)
            tk.Label(frame, text=med_text, justify="left", font=("Courier", 10)).pack(anchor="w")

            button_frame = tk.Frame(frame)
            button_frame.pack(pady=5)
            
            # ✅ NEW: Add Edit Medication button
            edit_btn = tk.Button(button_frame, text="Edit Medication", 
                               command=lambda idx=i: self.open_medication_editor(edit_index=idx),
                               bg="lightblue")
            edit_btn.pack(side=tk.LEFT, padx=5)
            
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
                dosage_instructions = med.get("dosage_instructions", "once per day")

                # ✅ MODIFIED: Use new calculation function
                days_left = calculate_days_supply(stock, dosage_instructions, scheduled_times)

                stop_date_str = med.get("stop_after_date")
                stop_date = None
                if stop_date_str:
                    try:
                        stop_date = datetime.strptime(stop_date_str, "%Y-%m-%d").date()
                    except:
                        pass

                today = datetime.today().date()

                # Only alert if days left < 5 AND medication isn't ending within 5 days
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
        # Add confirmation dialog
        if messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this medication?"):
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            user_id = self.current_user[0]
            c.execute("SELECT medication_data FROM users WHERE user_id = ?", (user_id,))
            data = json.loads(c.fetchone()[0])
            if 0 <= index < len(data):
                deleted_med = data[index]
                del data[index]
                c.execute("UPDATE users SET medication_data = ? WHERE user_id = ?", (json.dumps(data), user_id))
                messagebox.showinfo("Deleted", f"Medication '{deleted_med.get('medication_name', 'Unknown')}' has been deleted.")
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
        def check_alerts():
            print("[DEBUG] Alert thread started")
            while True:
                try:
                    now = datetime.now()
                    today_key = now.strftime("%Y-%m-%d")
                    current_date = now.date()
                    
                    # Reset alerted_today at midnight
                    if not hasattr(self, '_last_reset_date') or self._last_reset_date != current_date:
                        alerted_today.clear()
                        self._last_reset_date = current_date
                        print(f"[DEBUG] Reset daily alerts for {current_date}")

                    # Fetch fresh user data
                    try:
                        self.users = self.fetch_users()
                    except Exception as e:
                        print(f"[DEBUG] Error fetching users: {e}")
                        time.sleep(60)
                        continue

                    # ✅ NEW: Group medications by user and time
                    user_time_meds = {}  # {(user_id, time): [(med, med_index), ...]}
                    
                    for user in self.users:
                        user_id, fname, lname, med_data_json = user
                        try:
                            meds = json.loads(med_data_json) if med_data_json else []
                        except Exception as e:
                            print(f"[DEBUG] Error parsing medication data for user {fname}: {e}")
                            continue
                            
                        for idx, med in enumerate(meds):
                            # Check if medication should still be active
                            stop_date_str = med.get("stop_after_date")
                            if stop_date_str:
                                try:
                                    stop_date = datetime.strptime(stop_date_str, "%Y-%m-%d").date()
                                    if current_date > stop_date:
                                        continue  # Skip expired medications
                                except Exception as e:
                                    print(f"[DEBUG] Error parsing stop date: {e}")
                            
                            # ✅ IMPROVED: Check if medication should alert today based on dosage frequency
                            if not should_alert_today(med, current_date):
                                print(f"[DEBUG] Skipping {med.get('medication_name', 'Unknown')} - not scheduled for today")
                                continue
                            
                            times = med.get("scheduled_times", [])
                            for t in times:
                                try:
                                    med_time = datetime.strptime(t, "%H:%M").replace(
                                        year=now.year, month=now.month, day=now.day
                                    )
                                    delta = abs((now - med_time).total_seconds())
                                    
                                    # Check if within 1 minute window
                                    if delta <= 60:
                                        key = (user_id, t)
                                        if key not in user_time_meds:
                                            user_time_meds[key] = []
                                        
                                        # Check if this specific medication hasn't been alerted today
                                        alert_key = f"{today_key}-{user_id}-{idx}-{t}"
                                        if alert_key not in alerted_today:
                                            user_time_meds[key].append((med, idx, alert_key, fname, lname))
                                        
                                except Exception as e:
                                    print(f"[DEBUG] Error processing scheduled time '{t}': {e}")
                    
                    # ✅ NEW: Trigger combined alerts for each user/time combination
                    for (user_id, time_str), med_list in user_time_meds.items():
                        if med_list:  # Only create alert if there are medications to show
                            print(f"[DEBUG] Combined alert triggered: User {user_id} at {time_str} with {len(med_list)} medications")
                            self.root.after(0, self.trigger_combined_alert, user_id, time_str, med_list)
                    
                except Exception as e:
                    print(f"[DEBUG] Unexpected error in alert thread: {e}")
                
                # Sleep for 30 seconds instead of 60 for more responsive alerts
                time.sleep(30)

        # Start the background thread as a daemon so it stops when main program exits
        alert_thread = threading.Thread(target=check_alerts, daemon=True)
        alert_thread.start()
        print("[DEBUG] Alert monitoring thread started")

    def trigger_combined_alert(self, user_id, time_str, med_list):
        """Display combined medication alert popup for multiple medications at the same time"""
        try:
            # ✅ SAFETY CHECK: Don't create alert if user already has one
            if user_id in self.active_user_alerts:
                existing_alert = self.active_user_alerts[user_id]
                try:
                    if existing_alert and existing_alert.winfo_exists():
                        print(f"[DEBUG] Prevented duplicate alert for user {user_id} - alert already exists")
                        return
                    else:
                        # Clean up stale reference
                        del self.active_user_alerts[user_id]
                except:
                    # Window doesn't exist, clean up
                    del self.active_user_alerts[user_id]
            
            play_alert_sound()

            alert = tk.Toplevel(self.root)
            alert.title("Medication Alert")
            
            # ✅ REGISTER: This alert for the user IMMEDIATELY
            self.active_user_alerts[user_id] = alert
            
            # Dynamic sizing based on number of medications
            base_height = 150
            button_height = 100
            
            # Determine if we need scrolling
            needs_scrolling = len(med_list) >= 1
            
            if needs_scrolling:
                med_display_height = 350  # Fixed height for scrollable area
                total_height = base_height + med_display_height + button_height
            else:
                med_height = len(med_list) * 80  # Approximate height per medication
                total_height = base_height + med_height + button_height
            
            alert.geometry(f"500x{total_height}")
            alert.attributes("-topmost", True)
            alert.lift()

            # FIXED: Better offset calculation for multiple user alerts
            # Use the current count of active alerts to offset horizontally by 300 pixels
            offset_x = self.active_alert_count * 300
            offset_y = 50  # Small vertical offset to avoid title bar overlap
            x = self.root.winfo_x() + offset_x
            y = self.root.winfo_y() + offset_y
            alert.geometry(f"500x{total_height}+{x}+{y}")
            
            # Increment active alert count
            self.active_alert_count += 1

            # Header
            user_name = f"{med_list[0][3]} {med_list[0][4]}"  # fname, lname from first medication
            # Convert 24-hour time to 12-hour format for display
            try:
                time_obj = datetime.strptime(time_str, "%H:%M")
                display_time = time_obj.strftime("%I:%M %p").lstrip('0')
            except:
                display_time = time_str
            
            header_text = f"Time for {user_name} to take medications at {display_time}:"
            if len(med_list) > 1:
                header_text += f" ({len(med_list)} medications)"
            
            tk.Label(alert, text=header_text, 
                    font=("Helvetica", 16, "bold"), wraplength=450).pack(pady=10)

            # Create medication container - scrollable if 5+ medications
            if needs_scrolling:
                # Create frame for canvas and scrollbar
                scroll_container = tk.Frame(alert)
                scroll_container.pack(fill="both", expand=True, padx=10, pady=5)
                
                # Create canvas and scrollbar
                canvas = tk.Canvas(scroll_container, height=med_display_height, highlightthickness=0)
                scrollbar = tk.Scrollbar(scroll_container, orient="vertical", command=canvas.yview)
                scrollable_frame = tk.Frame(canvas)
                
                # Configure scrolling
                def configure_scrollregion(event):
                    canvas.configure(scrollregion=canvas.bbox("all"))
                
                def on_mousewheel_alert(event):
                    # Handle cross-platform mouse wheel scrolling
                    if event.num == 4:   # Linux scroll up
                        canvas.yview_scroll(-1, "units")
                    elif event.num == 5: # Linux scroll down
                        canvas.yview_scroll(1, "units")
                    else:  # Windows and Mac
                        canvas.yview_scroll(int(-1*(event.delta/120)), "units")
                
                scrollable_frame.bind("<Configure>", configure_scrollregion)
                
                # Bind mouse wheel events to canvas and scrollable_frame for better coverage
                canvas.bind("<MouseWheel>", on_mousewheel_alert)
                canvas.bind("<Button-4>", on_mousewheel_alert)
                canvas.bind("<Button-5>", on_mousewheel_alert)
                scrollable_frame.bind("<MouseWheel>", on_mousewheel_alert)
                scrollable_frame.bind("<Button-4>", on_mousewheel_alert)
                scrollable_frame.bind("<Button-5>", on_mousewheel_alert)
                
                # Also bind to the alert window itself for comprehensive scroll support
                alert.bind("<MouseWheel>", on_mousewheel_alert)
                alert.bind("<Button-4>", on_mousewheel_alert)
                alert.bind("<Button-5>", on_mousewheel_alert)
                
                # Create window in canvas
                canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
                
                # Configure canvas scrolling
                canvas.configure(yscrollcommand=scrollbar.set)
                
                # Pack canvas and scrollbar
                canvas.pack(side="left", fill="both", expand=True)
                scrollbar.pack(side="right", fill="y")
                
                # Configure canvas window width to match canvas
                def configure_canvas_window(event):
                    canvas.itemconfig(canvas_window, width=canvas.winfo_width())
                canvas.bind("<Configure>", configure_canvas_window)
                
                med_container = scrollable_frame
                
                print(f"[DEBUG] Created scrollable container for {len(med_list)} medications")
            else:
                # Regular container for fewer medications
                med_container = tk.Frame(alert)
                med_container.pack(fill="both", expand=True, padx=10, pady=5)

            # Track medication states
            med_states = {}  # {med_index: {'taken': BooleanVar, 'skipped': BooleanVar}}
            
            # Create medication entries
            for i, (med, med_index, alert_key, fname, lname) in enumerate(med_list):
                med_frame = tk.Frame(med_container, relief="ridge", bd=2, padx=10, pady=8)
                med_frame.pack(fill="x", padx=5, pady=3)

                # Medication info
                med_name = med.get('medication_name', 'Unknown Medication')
                dosage = med.get('dosage_instructions', '')
                stock = med.get('stock', 0)
                
                # Medication name and stock info
                name_frame = tk.Frame(med_frame)
                name_frame.pack(fill="x")
                
                tk.Label(name_frame, text=f"{i+1}. {med_name}", 
                        font=("Helvetica", 14, "bold")).pack(side="left")
                tk.Label(name_frame, text=f"Stock: {stock}", 
                        font=("Helvetica", 10), fg="blue").pack(side="right")
                
                if dosage:
                    tk.Label(med_frame, text=dosage, font=("Helvetica", 10), 
                            fg="gray", wraplength=400).pack(anchor="w")

                # Individual medication buttons
                button_frame = tk.Frame(med_frame)
                button_frame.pack(fill="x", pady=5)
                
                # State tracking
                taken_var = tk.BooleanVar()
                skipped_var = tk.BooleanVar()
                med_states[med_index] = {
                    'taken': taken_var, 
                    'skipped': skipped_var, 
                    'alert_key': alert_key,
                    'med': med
                }

                def create_taken_callback(idx, t_var, s_var):
                    def callback():
                        t_var.set(True)
                        s_var.set(False)
                        update_button_colors()
                    return callback

                def create_skip_callback(idx, t_var, s_var):
                    def callback():
                        t_var.set(False)
                        s_var.set(True)
                        update_button_colors()
                    return callback

                taken_btn = tk.Button(button_frame, text="✓ Taken", 
                                    command=create_taken_callback(med_index, taken_var, skipped_var),
                                    font=("Helvetica", 11), width=10)
                taken_btn.pack(side=tk.LEFT, padx=5)

                skip_btn = tk.Button(button_frame, text="✗ Skip", 
                                   command=create_skip_callback(med_index, taken_var, skipped_var),
                                   font=("Helvetica", 11), width=10)
                skip_btn.pack(side=tk.LEFT, padx=5)

                # Store button references for color updates
                med_states[med_index]['taken_btn'] = taken_btn
                med_states[med_index]['skip_btn'] = skip_btn

            def update_button_colors():
                """Update button colors based on selection state"""
                for med_index, state in med_states.items():
                    if state['taken'].get():
                        state['taken_btn'].config(bg="#90EE90", relief="sunken")  # Light green
                        state['skip_btn'].config(bg="SystemButtonFace", relief="raised")
                    elif state['skipped'].get():
                        state['taken_btn'].config(bg="SystemButtonFace", relief="raised")
                        state['skip_btn'].config(bg="#FFB6C1", relief="sunken")  # Light pink
                    else:
                        state['taken_btn'].config(bg="SystemButtonFace", relief="raised")
                        state['skip_btn'].config(bg="SystemButtonFace", relief="raised")

            # Main action buttons frame
            main_button_frame = tk.Frame(alert, bg="lightgray", relief="raised", bd=1)
            main_button_frame.pack(fill="x", pady=10, padx=10)

            # Summary label
            summary_label = tk.Label(main_button_frame, 
                                   text=f"Managing {len(med_list)} medication(s) for {user_name}",
                                   font=("Helvetica", 12), bg="lightgray")
            summary_label.pack(pady=5)

            # Button container
            button_container = tk.Frame(main_button_frame, bg="lightgray")
            button_container.pack(pady=5)

            def take_all_meds():
                """Mark all medications as taken"""
                for med_index, state in med_states.items():
                    state['taken'].set(True)
                    state['skipped'].set(False)
                update_button_colors()
                apply_and_close()

            def apply_and_close():
                """Apply all medication states and close the alert"""
                try:
                    conn = sqlite3.connect(self.db_path)
                    c = conn.cursor()
                    c.execute("SELECT medication_data FROM users WHERE user_id = ?", (user_id,))
                    result = c.fetchone()
                    
                    taken_count = 0
                    skipped_count = 0
                    
                    if result and result[0]:
                        meds = json.loads(result[0])
                        
                        # Update stock for taken medications
                        for med_index, state in med_states.items():
                            if state['taken'].get() and 0 <= med_index < len(meds):
                                current_stock = meds[med_index].get('stock', 0)
                                meds[med_index]['stock'] = max(0, current_stock - 1)
                                taken_count += 1
                                print(f"[DEBUG] Updated stock for {meds[med_index].get('medication_name')}: {current_stock} -> {meds[med_index]['stock']}")
                            elif state['skipped'].get():
                                skipped_count += 1
                            
                            # Mark as alerted regardless of taken/skipped
                            alerted_today.add(state['alert_key'])
                        
                        # Save updated medication data
                        c.execute("UPDATE users SET medication_data = ? WHERE user_id = ?", 
                                (json.dumps(meds), user_id))
                        conn.commit()
                    
                    conn.close()
                    
                    # Show summary message
                    if taken_count > 0 or skipped_count > 0:
                        summary_msg = f"Applied: {taken_count} taken, {skipped_count} skipped"
                        print(f"[DEBUG] {summary_msg}")
                    
                    # ✅ FIXED: Remove this alert from user tracking
                    if user_id in self.active_user_alerts:
                        del self.active_user_alerts[user_id]
                    
                    # IMPORTANT: Decrement active alert count when closing
                    self.active_alert_count = max(0, self.active_alert_count - 1)
                    alert.destroy()
                    
                    # Refresh user data display if current user matches
                    if self.current_user and self.current_user[0] == user_id:
                        self.users = self.fetch_users()
                        self.show_user_data(self.current_user)
                    
                except Exception as e:
                    print(f"Error updating medication stocks: {e}")
                    # ✅ FIXED: Remove this alert from user tracking even on error
                    if user_id in self.active_user_alerts:
                        del self.active_user_alerts[user_id]
                    # IMPORTANT: Decrement active alert count even on error
                    self.active_alert_count = max(0, self.active_alert_count - 1)
                    alert.destroy()

            def cancel_alert():
                """Close alert without making changes, but mark as alerted to prevent re-triggering"""
                # Mark individual medications as alerted
                for med_index, state in med_states.items():
                    alerted_today.add(state['alert_key'])
                
                # ✅ FIXED: Remove this alert from user tracking
                if user_id in self.active_user_alerts:
                    del self.active_user_alerts[user_id]
                
                # IMPORTANT: Decrement active alert count when canceling
                self.active_alert_count = max(0, self.active_alert_count - 1)
                alert.destroy()

            # Add window close protocol to handle X button clicks
            def on_closing():
                """Handle window close button (X)"""
                # Mark individual medications as alerted
                for med_index, state in med_states.items():
                    alerted_today.add(state['alert_key'])
                
                # ✅ FIXED: Remove this alert from user tracking
                if user_id in self.active_user_alerts:
                    del self.active_user_alerts[user_id]
                
                # Decrement active alert count
                self.active_alert_count = max(0, self.active_alert_count - 1)
                alert.destroy()
            
            alert.protocol("WM_DELETE_WINDOW", on_closing)

            # Main buttons
            tk.Button(button_container, text="✓ All Meds Taken", command=take_all_meds,
                     font=("Helvetica", 12, "bold"), bg="#90EE90", padx=15, pady=5).pack(side=tk.LEFT, padx=5)
            
            tk.Button(button_container, text="Apply Selections", command=apply_and_close,
                     font=("Helvetica", 12, "bold"), bg="#87CEEB", padx=15, pady=5).pack(side=tk.LEFT, padx=5)
            
            tk.Button(button_container, text="Cancel", command=cancel_alert,
                     font=("Helvetica", 12), bg="#F0F0F0", padx=15, pady=5).pack(side=tk.LEFT, padx=5)

            # Initialize button colors
            update_button_colors()
            
            # If scrollable, scroll to top
            if needs_scrolling:
                canvas.yview_moveto(0)
            
            print(f"[DEBUG] Created combined alert for {len(med_list)} medications, scrollable: {needs_scrolling}, offset: {offset_x}px")
            
        except Exception as e:
            print(f"Error creating combined medication alert: {e}")
            # Ensure we don't leave the counter in an inconsistent state
            self.active_alert_count = max(0, self.active_alert_count - 1)
#--------------------------------------------------------------------

    def trigger_alert(self, med, user_fname, user_id, med_index, alert_key):
        """Legacy single medication alert - kept for backward compatibility if needed"""
        # This method is now largely replaced by trigger_combined_alert
        # but kept in case single medication alerts are still needed
        pass


def main():
    """Main function to start the application"""
    try:
        # Initialize database tables
        setup_tables()
        
        # Create the main window
        root = tk.Tk()
        
        # Create the application instance
        app = MedicationApp(root)
        
        # Start the GUI event loop
        root.mainloop()
        
    except Exception as e:
        print(f"Error starting application: {e}")
        messagebox.showerror("Application Error", f"Failed to start application:\n{str(e)}")


if __name__ == "__main__":
    main()
            