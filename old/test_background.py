import tkinter as tk
from PIL import Image, ImageTk
from PIL.Image import Resampling

root = tk.Tk()
root.title("Medication Time")
root.geometry("600x850")

# Load and resize background image
bg_image = Image.open("background.jpg")
bg_image = bg_image.resize((600, 850), Resampling.LANCZOS)
bg_photo = ImageTk.PhotoImage(bg_image)

# Create canvas with background image
canvas = tk.Canvas(root, width=600, height=850)
canvas.pack(fill="both", expand=True)
canvas.create_image(0, 0, image=bg_photo, anchor="nw")

# Add a label on top
label = tk.Label(root, text="Welcome to Medication Time", font=("Helvetica", 20), bg="#ffffff")
canvas.create_window(400, 50, window=label)

root.mainloop()




        # Load and set background image
        bg_image = Image.open("background.jpg")  # Replace with your image path
        bg_image = bg_image.resize((600, 850), Resampling.LANCZOS)
        self.bg_photo = ImageTk.PhotoImage(bg_image)

        self.canvas = tk.Canvas(self.root, width=600, height=850)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_image(0, 0, image=self.bg_photo, anchor="nw")

        # Add your interface elements like this
        self.canvas.create_window(400, 50, window=tk.Label(self.root, text="Medication Time", font=("Helvetica", 20), bg="white"))
        # Repeat canvas.create_window(...) for all other interface elements
