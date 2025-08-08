import tkinter as tk
from tkinter import messagebox, ttk
import pandas as pd
import os
import webbrowser
from datetime import datetime, timedelta
import threading
import time
from twilio.rest import Client

# Twilio setup (replace with actual credentials)
TWILIO_ACCOUNT_SID = 'your_account_sid'
TWILIO_AUTH_TOKEN = 'your_auth_token'
TWILIO_FROM_PHONE = '+1234567890'

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Paths and constants
DESKTOP_PATH = os.path.join(os.path.expanduser("~"), "Desktop")
os.makedirs(DESKTOP_PATH, exist_ok=True)
CSV_PATH = os.path.join(DESKTOP_PATH, "Medication_Files.csv")

# Create CSV if not exists
if not os.path.exists(CSV_PATH):
    df = pd.DataFrame(columns=["User", "Medication", "Dosage", "Schedule", "Phone", "Link", "Start Date", "Refill Date", "Drug Class"])
    df.to_csv(CSV_PATH, index=False)

# Load data
try:
    data = pd.read_csv(CSV_PATH)
except Exception as e:
    data = pd.DataFrame(columns=["User", "Medication", "Dosage", "Schedule", "Phone", "Link", "Start Date", "Refill Date", "Drug Class"])
    data.to_csv(CSV_PATH, index=False)

INCOMPATIBLE_COMBINATIONS = [("Aspirin", "Warfarin"), ("Ibuprofen", "Lisinopril")]
DRUG_CLASSES = {
    "Aspirin": "NSAID",
    "Ibuprofen": "NSAID",
    "Warfarin": "Anticoagulant",
    "Lisinopril": "ACE Inhibitor"
}

history_stack = []

def push_undo():
    history_stack.append(data.copy())

def undo_changes():
    global data
    if history_stack:
        data = history_stack.pop()
        data.to_csv(CSV_PATH, index=False)
        update_dropdowns()
        messagebox.showinfo("Undo", "Reverted to previous state.")
    else:
        messagebox.showinfo("Undo", "No changes to undo.")

root = tk.Tk()
root.title("Family Medication Manager")
root.geometry("1200x800")

user_var = tk.StringVar()
med_var = tk.StringVar()
dosage_var = tk.StringVar()
schedule_var = tk.StringVar()
phone_var = tk.StringVar()
link_var = tk.StringVar()
start_date_var = tk.StringVar()
refill_date_var = tk.StringVar()
drug_class_var = tk.StringVar()

last_alert_time = {}
ALERT_INTERVAL = 3600

def update_dropdowns():
    meds = sorted(data["Medication"].dropna().unique())
    med_dropdown["values"] = meds
    users = sorted(data["User"].dropna().unique())
    user_dropdown["values"] = users

def check_incompatibility(user_meds, new_med):
    for med in user_meds:
        if (med, new_med) in INCOMPATIBLE_COMBINATIONS or (new_med, med) in INCOMPATIBLE_COMBINATIONS:
            return med
    return None

def update_link_field(*args):
    med = med_var.get()
    if med:
        link = f"https://www.drugs.com/{med.lower().replace(' ', '-')}.html"
        link_var.set(link)

def generate_schedule_entries(schedule_type, start_date_str):
    try:
        start_date = datetime.strptime(str(start_date_str), "%Y-%m-%d")
    except (ValueError, TypeError):
        return "Invalid date"

    entries = []
    for i in range(7):
        day = start_date + timedelta(days=i)
        day_name = day.strftime("%A")
        if schedule_type.lower() == "daily" or \
           (schedule_type.lower() == "twice daily") or \
           (schedule_type.lower() == "weekly" and day.weekday() == start_date.weekday()):
            entries.append(day_name)
    return ", ".join(entries)

def save_entry():
    global data
    user = user_var.get()
    med = med_var.get()
    dosage = dosage_var.get()
    sched = schedule_var.get()
    phone = phone_var.get()
    start_date = start_date_var.get()
    refill_date = refill_date_var.get()
    drug_class = drug_class_var.get() or DRUG_CLASSES.get(med, "")

    if not user or not med or not start_date:
        messagebox.showerror("Error", "User, Medication, and Start Date must not be empty.")
        return

    user_meds = data[data.User == user]["Medication"].tolist()
    conflict = check_incompatibility(user_meds, med)

    if conflict:
        popup = tk.Toplevel()
        popup.configure(bg="red")
        tk.Label(popup, text=f"WARNING: {med} is incompatible with {conflict}!", fg="yellow", bg="red", font=("Arial", 14, "bold")).pack(padx=10, pady=10)
        tk.Label(popup, text="Check with a healthcare provider before combining.", bg="red", fg="white").pack(pady=5)
        tk.Button(popup, text="OK", command=popup.destroy).pack(pady=10)
        return

    schedule_days = generate_schedule_entries(sched, start_date)
    med_link = link_var.get()
    new_row = {"User": user, "Medication": med, "Dosage": dosage, "Schedule": schedule_days, "Phone": phone, "Link": med_link, "Start Date": start_date, "Refill Date": refill_date, "Drug Class": drug_class}
    push_undo()
    data = pd.concat([data, pd.DataFrame([new_row])], ignore_index=True)
    data.to_csv(CSV_PATH, index=False)
    update_dropdowns()
    messagebox.showinfo("Saved", "Medication schedule saved.")

def open_link():
    if link_var.get():
        webbrowser.open_new_tab(link_var.get())

def view_user_entries():
    user = user_var.get()
    user_data = data[data['User'] == user]
    if user_data.empty:
        messagebox.showinfo("No Data", f"No entries found for user '{user}'")
        return

    popup = tk.Toplevel()
    popup.title(f"Entries for {user}")
    text = tk.Text(popup, wrap="word")
    text.pack(padx=10, pady=10, fill="both", expand=True)
    user_data['Refill Countdown'] = pd.to_datetime(user_data['Refill Date'], errors='coerce').dt.date.apply(
        lambda d: f"{(d - datetime.today().date()).days} days left" if pd.notnull(d) else "N/A")
    text.insert("1.0", user_data.to_string(index=False))
    text.config(state="disabled")

def check_refills():
    today = datetime.today().date()
    soon = today + timedelta(days=3)
    due_refills = data[pd.to_datetime(data['Refill Date'], errors='coerce').dt.date <= soon]
    if not due_refills.empty:
        due_refills['Refill Countdown'] = pd.to_datetime(due_refills['Refill Date'], errors='coerce').dt.date.apply(
            lambda d: f"{(d - today).days} days left" if pd.notnull(d) else "N/A")
        messagebox.showinfo("Refill Alert", due_refills[['User', 'Medication', 'Refill Date', 'Refill Countdown']].to_string(index=False))

def check_class_conflict():
    user = user_var.get()
    if not user:
        messagebox.showinfo("Drug Class Check", "Please select a user.")
        return
    user_data = data[data['User'] == user]
    class_counts = user_data['Drug Class'].value_counts()
    duplicates = class_counts[class_counts > 1]
    if not duplicates.empty:
        messagebox.showwarning("Drug Class Conflict", f"Multiple medications from the same class found:\n{duplicates.to_string()}")

frame = ttk.Frame(root)
frame.pack(pady=10)

entries = [
    ("User", user_var),
    ("Medication", med_var),
    ("Dosage (e.g. Twice daily after meal)", dosage_var),
    ("Schedule Type (e.g. Daily, Weekly, Twice daily)", schedule_var),
    ("Phone Number", phone_var),
    ("Info Link (optional)", link_var),
    ("Start Date (YYYY-MM-DD)", start_date_var),
    ("Refill Date (YYYY-MM-DD, optional)", refill_date_var),
    ("Drug Class (optional, auto-fill available)", drug_class_var)
]

for i, (label, var) in enumerate(entries):
    ttk.Label(frame, text=label).grid(row=i, column=0, padx=5, pady=5, sticky="w")
    if label == "User":
        user_dropdown = ttk.Combobox(frame, textvariable=var)
        user_dropdown.grid(row=i, column=1, padx=5, pady=5)
    elif label == "Medication":
        med_dropdown = ttk.Combobox(frame, textvariable=var)
        med_dropdown.grid(row=i, column=1, padx=5, pady=5)
        med_var.trace("w", update_link_field)
    else:
        ttk.Entry(frame, textvariable=var).grid(row=i, column=1, padx=5, pady=5)

buttons = [
    ("Save Entry", save_entry),
    ("Open Info Link", open_link),
    ("View User Entries", view_user_entries),
    ("Check Refill Dates", check_refills),
    ("Check Drug Class Conflict", check_class_conflict),
    ("Undo Last Change", undo_changes)
]

for j, (text, cmd) in enumerate(buttons):
    ttk.Button(frame, text=text, command=cmd).grid(row=9 + j, column=0, columnspan=2, pady=5)

update_dropdowns()

root.mainloop()
