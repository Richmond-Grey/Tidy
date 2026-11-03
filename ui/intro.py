"""Plays the bear intro (frames rendered with Remotion, see intro/) in a borderless splash window."""
import os
import time
import tkinter as tk

INTRO_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "intro")
FPS = 30
HOLD_MS = 450      # pause on the last frame
FADE_MS = 260
BACKGROUND = "#FAF5EC"  # the intro's own cream, whatever the app theme


def _frames() -> list[str]:
    try:
        return sorted(os.path.join(INTRO_DIR, n) for n in os.listdir(INTRO_DIR) if n.endswith(".png"))
    except OSError:
        return []


def intro_available() -> bool:
    return bool(_frames())


class IntroPlayer(tk.Toplevel):
    """Click or press any key to skip. Calls on_done() once, after the window is gone."""

    def __init__(self, master, on_done):
        super().__init__(master)
        self.on_done = on_done
        self.paths = _frames()
        self.images: dict[int, tk.PhotoImage] = {}
        self.finished = False

        self.overrideredirect(True)
        self.configure(bg=BACKGROUND)
        self._set_alpha(0.0)
        first = self._image(0)
        width, height = first.width(), first.height()
        x = (self.winfo_screenwidth() - width) // 2
        y = (self.winfo_screenheight() - height) // 3
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.attributes("-topmost", True)

        self.label = tk.Label(self, image=first, bd=0, bg=BACKGROUND, cursor="hand2")
        self.label.pack()
        tk.Label(self, text="Click to skip", bg=BACKGROUND, fg="#B3A491", font=("Segoe UI", 8)).place(
            relx=1.0, rely=1.0, x=-10, y=-6, anchor="se")
        for sequence in ("<Button-1>", "<Key>"):
            self.bind(sequence, lambda _e: self.finish())
        self.focus_force()

        self.start = time.perf_counter()
        self._fade(0.0, 1.0, 140, self._tick)

    def _image(self, index: int) -> tk.PhotoImage:
        # Decoded on demand (a few ms each) so the intro starts instantly
        if index not in self.images:
            self.images[index] = tk.PhotoImage(master=self, file=self.paths[index])
        return self.images[index]

    def _set_alpha(self, value: float):
        try:
            self.attributes("-alpha", value)
        except tk.TclError:
            pass  # some Linux window managers don't support transparency

    def _fade(self, start: float, end: float, duration_ms: int, then):
        began = time.perf_counter()

        def step():
            if not self.winfo_exists():
                return
            t = min((time.perf_counter() - began) * 1000 / duration_ms, 1.0)
            self._set_alpha(start + (end - start) * t)
            if t < 1.0:
                self.after(12, step)
            else:
                then()
        step()

    def _tick(self):
        if self.finished:
            return
        # Pick the frame from the clock so a slow machine drops frames instead of slowing down
        index = int((time.perf_counter() - self.start) * FPS)
        if index >= len(self.paths):
            self.label.configure(image=self._image(len(self.paths) - 1))
            self.after(HOLD_MS, self.finish)
            return
        self.label.configure(image=self._image(index))
        self.after(8, self._tick)

    def finish(self):
        if self.finished:
            return
        self.finished = True
        # Show the app underneath, then fade the splash away on top of it
        self.on_done()
        self.lift()
        self._fade(1.0, 0.0, FADE_MS, self.destroy)
