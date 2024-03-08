import tkinter as tk

import pyautogui
import win32gui

try:
    from common import helpers
except ModuleNotFoundError:
    import helpers


class OverlayApp:
    def __init__(self):
        self.game_state = "start"  # start, host, run, accept1, accept2
        self.root: tk.Tk = tk.Tk()
        self.canvas = tk.Canvas(self.root, bg="white", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        # Set the window to be transparent and always on top
        self.root.wm_attributes("-transparentcolor", "white")
        self.root.wm_attributes("-topmost", True)
        self.root.overrideredirect(True)
        self.update_overlay()

    def start(self):
        self.root.mainloop()

    def update_overlay(self):
        handle = win32gui.FindWindow(None, "ARK: Survival Evolved")
        try:
            rect = win32gui.GetWindowRect(handle)
        except Exception as e:
            if "Invalid window handle" in str(e):
                rect = None
        images = helpers.get_images()
        if rect:
            # Unpack the window's position and size
            # x, y, x1, y1
            # left, top, right, bottom
            left, top, right, bottom = rect
            width = right - left
            height = bottom - top

            game_aspect_ratio = 16 / 9
            window_aspect_ratio = width / height
            if window_aspect_ratio > game_aspect_ratio:
                # Window is too wide, black bars will be on the sides
                inner_height = height
                inner_width = int(inner_height * game_aspect_ratio)
            else:
                # Window is too tall, black bars will be on the top/bottom
                inner_width = width
                inner_height = int(inner_width / game_aspect_ratio)

            # Calculate offsets for black bars if present
            offset_x = (width - inner_width) // 2
            offset_y = (height - inner_height) // 2

            # Resize and move the overlay window to match the game window
            self.root.geometry(f"{width}x{height}+{left}+{top}")
            # Clear the canvas and draw a red rectangle
            self.canvas.delete("all")
            # Draw the main window border
            # self.canvas.create_rectangle(10, 3, width - 10, height - 10, outline="red", width=5)
            # Draw each of the button outlines
            positions = helpers.get_positions()
            for button_name, (x_ratio, y_ratio, w_ratio, h_ratio) in positions.items():
                # if self.game_state in positions and button_name != self.game_state:
                #     continue
                # X and Y ratio represent the center of the button as a percentage of the game window
                # W and H ratio represent the width and height of the button relative to the game window as a percentage
                # If the window is out of perfect 16:9 aspect ratio, the game UI will have black bars on the sides or top and bottom

                # If window is wider than 16:9, there will be black bars on the sides
                # If window is taller than 16:9, there will be black bars on the top and bottom
                # Calculate button dimensions based on its ratios and inner dimensions
                button_x = int(offset_x + (inner_width * x_ratio)) - (w_ratio * inner_width) // 2
                button_y = int(offset_y + (inner_height * y_ratio)) - (h_ratio * inner_height) // 2
                button_width = int(inner_width * w_ratio)
                button_height = int(inner_height * h_ratio)

                loc = pyautogui.locateOnScreen(images[button_name], confidence=0.85, grayscale=True)
                if loc:
                    print(f"{button_name}: {loc}")
                    self.canvas.create_rectangle(
                        loc.left,
                        loc.top,
                        loc.left + loc.width,
                        loc.top + loc.height,
                        outline="green",
                        width=2,
                    )
                    center = pyautogui.center(loc)
                    # draw a circle on the center of the button
                    self.canvas.create_oval(
                        center.x - 5,
                        center.y - 5,
                        center.x + 5,
                        center.y + 5,
                        fill="green",
                    )
                else:
                    self.canvas.create_rectangle(
                        button_x,
                        button_y,
                        button_x + button_width,
                        button_y + button_height,
                        outline="red",
                        width=2,
                    )
                    # draw a circle on the center of the button
                    self.canvas.create_oval(
                        button_x + button_width // 2 - 5,
                        button_y + button_height // 2 - 5,
                        button_x + button_width // 2 + 5,
                        button_y + button_height // 2 + 5,
                        fill="red",
                    )

        # Schedule the overlay to be updated again after 100ms
        self.root.after(100, self.update_overlay)


def main():
    app = OverlayApp()
    app.start()


if __name__ == "__main__":
    main()
