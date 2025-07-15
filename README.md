# 💊 Medication Time Manager

**A family-friendly desktop medication scheduler and journal tracker.**  
Designed for tracking prescriptions, alerting users at scheduled dose times, monitoring stock levels, and exporting health logs to PDF reports.

---

## 🚀 Features

### ✅ Medication Management

- Add multiple users (up to 4+)
- Assign medications per user with:
  - Medication name
  - Prescribing doctor
  - Date prescribed
  - Optional end date
  - Dosage instructions
  - Daily schedule (7 AM, Noon, 5 PM, 10 PM)
  - Quantity in stock

### 🔔 Dose Alerts

- Real-time **dose reminders** trigger with sound and popup windows
- "Taken" or "Skip" actions reduce or preserve inventory
- Runs continuously in the background with built-in threading

### 🔁 Refill Alerts

- Automatically checks for low stock across all users
- Alerts if a medication has **less than 5 days of supply**
  - Only alerts if the prescription is **not** set to end within those 5 days
- Custom alert message displays user name, medication, and days remaining

### 📓 Journal Entries

- Each user can write personal journal entries
- Entries stored in a SQLite database and filterable by date range
- Useful for tracking side effects, recovery, or daily wellbeing

### 📄 Export to PDF (and TXT)

- Filter journal entries by date and export:
  - Prefixed with current medication list, prescribing doctors, and dosage instructions
  - Saves cleanly to `.pdf` (using `reportlab`)
  - Optionally exports to `.txt` with same format
- PDF auto-opens upon save

### 🎛️ Settings

- Adjustable alert volume (saved between sessions)
- Built-in test alert sound button

---

## 🛠️ Installation

### Requirements

- Python 3.9+
- Modules:
  - `tkinter` (standard)
  - `tkcalendar`
  - `pygame`
  - `reportlab`

Install with:

```bash
pip install tkcalendar pygame reportlab

---

📂 First-Time Setup
Use the provided Run_once_db_setup.py script to initialize the database.

🆕 Run_once_db_setup.py
Launches a friendly UI to create up to 4 new user profiles with sample medications.

Prompts for first and last names

Adds sample prescriptions and dose schedules

Creates a new medication_time_db.db

Auto-launches the main app upon success (launches .exe if compiled)

🟢 To run:
bash
Copy
Edit
python Run_once_db_setup.py
📝 Note: Re-running this will overwrite the existing database.

🧪 Development Mode
To run the main app directly:

bash
Copy
Edit
python MedicationTime.py
📦 Compiling to EXE (Optional)
You can use pyinstaller to bundle the application into an executable:

bash
Copy
Edit
pyinstaller --noconsole --onefile MedicationTime.py
Ensure that MedicationTime.exe is in the same folder as your DB setup script so Run_once_db_setup.py can launch it.

📁 Files in Repository
File	Description
MedicationTime.py	Main application
Run_once_db_setup.py	One-time setup utility for creating new users and sample medications
medication_time_db.db	Auto-created SQLite DB file
MedicationTime.mp3	Optional alert sound (place in same folder) (One Flew Over The Coo Coo's Nest 'Medication Time... Medication Time...' works great)
settings.json	Auto-created volume settings

Developed by Jeremy Yates
FAA Part 107 Drone Pilot | Python Developer | Mobile Healthcare Tech Enthusiast
