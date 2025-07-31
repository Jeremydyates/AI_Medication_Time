import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import os

# App setup
root = tk.Tk()
root.title("Medication Time")
root.geometry("600x850")  # Adjust as needed

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

# Now place all your labels, buttons, etc., inside main_frame instead of root.
# Example:
welcome_label = tk.Label(main_frame, text="Welcome to Medication Time", font=("Arial", 18), bg="#ffffff")
welcome_label.pack(pady=10)