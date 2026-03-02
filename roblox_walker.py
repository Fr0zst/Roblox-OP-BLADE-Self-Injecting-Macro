# © 2025 Fr0zst. All rights reserved. 
# Unauthorized copying prohibited.

import tkinter as tk
import threading
import time
import ctypes
import ctypes.wintypes
import win32gui
import win32process
import psutil

# ── SendInput structures ──────────────────────────────────────────────────────
KEYEVENTF_KEYDOWN = 0x0000
KEYEVENTF_KEYUP   = 0x0002
KEYEVENTF_SCANCODE = 0x0008
INPUT_KEYBOARD    = 1

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk",         ctypes.wintypes.WORD),
        ("wScan",       ctypes.wintypes.WORD),
        ("dwFlags",     ctypes.wintypes.DWORD),
        ("time",        ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

class _INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("_pad", ctypes.c_byte * 28)]

class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.wintypes.DWORD), ("_u", _INPUT_UNION)]

SendInput = ctypes.windll.user32.SendInput

# Map key char -> scan code (using MapVirtualKey)
def _scan(vk):
    return ctypes.windll.user32.MapVirtualKeyW(vk, 0)

# ── Key virtual codes ─────────────────────────────────────────────────────────
VK_CODES = {'w': 0x57, 'a': 0x41, 's': 0x53, 'd': 0x44}

# First pass:  W, A, W, D, S, A   (delay indices 0,1,2,3,4,5)
# Loop passes:    A, W, D, S, A   (delay indices  1,2,3,4,5)
FIRST_SEQUENCE  = ['w', 'a', 'w', 'd', 's', 'a']
LOOP_SEQUENCE   = [     'a', 'w', 'd', 's', 'a']
FIRST_DELAY_IDX = [0, 1, 2, 3, 4, 5]
LOOP_DELAY_IDX  = [   1, 2, 3, 4, 5]

running = False


# ── Process detection ─────────────────────────────────────────────────────────
def find_roblox_processes():
    """Return {pid: name} for every process with 'roblox' in its name/path."""
    matches = {}
    for proc in psutil.process_iter(['pid', 'name', 'exe']):
        try:
            name = proc.info['name'] or ''
            exe  = proc.info['exe']  or ''
            if 'roblox' in name.lower() or 'roblox' in exe.lower():
                matches[proc.info['pid']] = name
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return matches


def find_roblox_player():
    """Return (hwnd, proc_name) for the best Roblox window on the system."""
    roblox_pids = find_roblox_processes()
    if not roblox_pids:
        return None, None

    found = []

    def enum_handler(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid in roblox_pids and win32gui.GetWindowText(hwnd):
                found.append((hwnd, pid))
        except Exception:
            pass

    win32gui.EnumWindows(enum_handler, None)
    if not found:
        return None, None

    for hwnd, pid in found:
        if 'player' in roblox_pids[pid].lower():
            return hwnd, roblox_pids[pid]
    hwnd, pid = found[0]
    return hwnd, roblox_pids[pid]


# ── Key injection ─────────────────────────────────────────────────────────────
def send_key(hwnd, vk, hold=0.5):
    """Press and HOLD vk for  seconds, then release."""
    try:
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.03)
    except Exception:
        pass

    scan = _scan(vk)

    down = INPUT()
    down.type = INPUT_KEYBOARD
    down._u.ki.wVk         = 0
    down._u.ki.wScan       = scan
    down._u.ki.dwFlags     = KEYEVENTF_SCANCODE | KEYEVENTF_KEYDOWN
    down._u.ki.time        = 0
    down._u.ki.dwExtraInfo = ctypes.pointer(ctypes.c_ulong(0))

    up = INPUT()
    up.type = INPUT_KEYBOARD
    up._u.ki.wVk         = 0
    up._u.ki.wScan       = scan
    up._u.ki.dwFlags     = KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP
    up._u.ki.time        = 0
    up._u.ki.dwExtraInfo = ctypes.pointer(ctypes.c_ulong(0))

    SendInput(1, ctypes.byref(down), ctypes.sizeof(INPUT))
    time.sleep(max(0.0, hold))          # hold the key for this long
    SendInput(1, ctypes.byref(up),   ctypes.sizeof(INPUT))


def run_sequence(delays, status_var, btn, popup_cb):
    global running
    hwnd, proc_name = find_roblox_player()

    # Fire the popup callback on the main thread
    popup_cb(hwnd, proc_name)

    if not hwnd:
        running = False
        btn.config(text="▶  START", bg="#00ff88")
        status_var.set("⏹  Stopped")
        return

    status_var.set(f"✅  {proc_name}")
    first_pass = True

    while running:
        seq       = FIRST_SEQUENCE  if first_pass else LOOP_SEQUENCE
        d_idx     = FIRST_DELAY_IDX if first_pass else LOOP_DELAY_IDX
        for key, di in zip(seq, d_idx):
            if not running:
                break
            send_key(hwnd, VK_CODES[key], hold=delays[di].get())
        first_pass = False

    status_var.set("⏹  Stopped")
    btn.config(text="▶  START", bg="#00ff88")


# ── Styled popup ──────────────────────────────────────────────────────────────
def show_inject_popup(root, hwnd, proc_name):
    """
    Show a themed frameless popup window matching the main GUI style.
    - Success: green accent, shows process filename
    - Failure: red accent, shows 'not found' message
    """
    success = hwnd is not None

    popup = tk.Toplevel(root)
    popup.overrideredirect(True)
    popup.configure(bg="#0a0a0f")
    popup.resizable(False, False)

    W, H = 340, 220
    # Center relative to main window
    rx = root.winfo_x()
    ry = root.winfo_y()
    rw = root.winfo_width()
    rh = root.winfo_height()
    x = rx + (rw - W) // 2
    y = ry + (rh - H) // 2
    popup.geometry(f"{W}x{H}+{x}+{y}")

    # Lift above main window
    popup.lift()
    popup.grab_set()

    accent     = "#00ff88" if success else "#ff4466"
    dim_accent = "#003322" if success else "#330011"
    icon       = "✅" if success else "❌"
    heading    = "INJECTION SUCCESS" if success else "INJECTION FAILED"
    subtext    = proc_name if success else "No Roblox process found"
    body       = "Keys will now be sent to:" if success else "Start Roblox and try again."

    # ── Title bar ──
    titlebar = tk.Frame(popup, bg="#111122", height=32)
    titlebar.pack(fill="x")

    tk.Label(titlebar, text="⚡ PROCESS SCAN", font=("Courier New", 9, "bold"),
             bg="#111122", fg=accent).pack(side="left", padx=10, pady=6)

    close = tk.Label(titlebar, text="✕", font=("Courier New", 11, "bold"),
                     bg="#111122", fg="#ff4466", cursor="hand2")
    close.pack(side="right", padx=10)
    close.bind("<Button-1>", lambda e: popup.destroy())

    # ── Body ──
    body_frame = tk.Frame(popup, bg="#0a0a0f")
    body_frame.pack(fill="both", expand=True, padx=18, pady=12)

    tk.Label(body_frame, text=icon, font=("Segoe UI Emoji", 28),
             bg="#0a0a0f", fg=accent).pack(pady=(4, 2))

    tk.Label(body_frame, text=heading, font=("Courier New", 11, "bold"),
             bg="#0a0a0f", fg=accent).pack()

    tk.Label(body_frame, text=body, font=("Courier New", 8),
             bg="#0a0a0f", fg="#555577").pack(pady=(6, 2))

    # Highlighted filename / error box
    pill = tk.Frame(body_frame, bg=dim_accent, padx=10, pady=5)
    pill.pack(fill="x", pady=(2, 10))
    tk.Label(pill, text=subtext, font=("Courier New", 10, "bold"),
             bg=dim_accent, fg=accent, wraplength=260).pack()

    # OK button
    ok_btn = tk.Button(body_frame, text="OK", font=("Courier New", 10, "bold"),
                       bg=accent, fg="#0a0a0f", activebackground=accent,
                       relief="flat", bd=0, cursor="hand2", padx=20, pady=6,
                       command=popup.destroy)
    ok_btn.pack(fill="x")

    # Allow dragging the popup too
    popup._ox, popup._oy = 0, 0
    def pm(e): popup._ox, popup._oy = e.x, e.y
    def mm(e):
        popup.geometry(f"+{popup.winfo_pointerx()-popup._ox}+{popup.winfo_pointery()-popup._oy}")
    titlebar.bind("<ButtonPress-1>", pm)
    titlebar.bind("<B1-Motion>", mm)


# ── Main App ──────────────────────────────────────────────────────────────────
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Roblox Walker")
        self.root.geometry("420x570")
        self.root.configure(bg="#0a0a0f")
        self.root.resizable(False, False)
        self.root.overrideredirect(True)

        self.delays = [tk.DoubleVar(value=v) for v in [0.55, 0.3, 0.35, 0.55, 0.35, 0.4]]
        self._offset_x = 0
        self._offset_y = 0
        self.show_loading()

    # ── Loading screen ────────────────────────────────────────────────────────
    def show_loading(self):
        self.loading_frame = tk.Frame(self.root, bg="#0a0a0f")
        self.loading_frame.place(relwidth=1, relheight=1)

        tk.Label(self.loading_frame, text="⚡", font=("Segoe UI Emoji", 48),
                 bg="#0a0a0f", fg="#00ff88").pack(pady=(120, 10))
        tk.Label(self.loading_frame, text="ROBLOX WALKER", font=("Courier New", 18, "bold"),
                 bg="#0a0a0f", fg="#00ff88").pack()
        tk.Label(self.loading_frame, text="Initializing...", font=("Courier New", 10),
                 bg="#0a0a0f", fg="#555577").pack(pady=5)

        self.progress_canvas = tk.Canvas(self.loading_frame, width=260, height=6,
                                          bg="#1a1a2e", highlightthickness=0)
        self.progress_canvas.pack(pady=20)
        self.progress_rect = self.progress_canvas.create_rectangle(0, 0, 0, 6,
                                                                    fill="#00ff88", outline="")
        self.progress = 0
        self.animate_loading()

    def animate_loading(self):
        self.progress += 3
        self.progress_canvas.coords(self.progress_rect, 0, 0,
                                    int(260 * self.progress / 100), 6)
        if self.progress < 100:
            self.root.after(30, self.animate_loading)
        else:
            self.root.after(300, self.finish_loading)

    def finish_loading(self):
        self.loading_frame.destroy()
        self.build_main()

    # ── Main UI ───────────────────────────────────────────────────────────────
    def build_main(self):
        titlebar = tk.Frame(self.root, bg="#111122", height=36)
        titlebar.pack(fill="x")
        titlebar.bind("<ButtonPress-1>", self.start_move)
        titlebar.bind("<B1-Motion>", self.do_move)

        tk.Label(titlebar, text="⚡ ROBLOX WALKER", font=("Courier New", 11, "bold"),
                 bg="#111122", fg="#00ff88").pack(side="left", padx=12, pady=6)

        close_btn = tk.Label(titlebar, text="✕", font=("Courier New", 12, "bold"),
                              bg="#111122", fg="#ff4466", cursor="hand2")
        close_btn.pack(side="right", padx=12)
        close_btn.bind("<Button-1>", lambda e: self.root.destroy())

        main = tk.Frame(self.root, bg="#0a0a0f")
        main.pack(fill="both", expand=True, padx=20, pady=10)

        tk.Label(main, text="KEY SEQUENCE & HOLD TIMES (seconds)",
                 font=("Courier New", 9, "bold"), bg="#0a0a0f", fg="#444466").pack(anchor="w", pady=(10, 2))
        tk.Label(main, text="① first-pass only — skipped on every loop  |  time key is held",
                 font=("Courier New", 8), bg="#0a0a0f", fg="#334455").pack(anchor="w", pady=(0, 6))

        seq_frame = tk.Frame(main, bg="#0a0a0f")
        seq_frame.pack(fill="x")

        labels = ['W  (forward) ①', 'A  (strafe L)', 'W  (forward)', 'D  (strafe R)', 'S  (back)', 'A  (strafe L)']
        colors = ['#aaffcc',         '#44aaff',        '#00ff88',      '#ff8844',        '#ff4466',   '#44aaff']

        for i, (label, color) in enumerate(zip(labels, colors)):
            row = tk.Frame(seq_frame, bg="#111122", pady=6, padx=10)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=f"{i+1}.", font=("Courier New", 10, "bold"),
                     bg="#111122", fg="#333355", width=2).pack(side="left")
            tk.Label(row, text=label, font=("Courier New", 10, "bold"),
                     bg="#111122", fg=color, width=17, anchor="w").pack(side="left", padx=(4, 10))
            tk.Label(row, text="hold: ", font=("Courier New", 9),
                     bg="#111122", fg="#555577").pack(side="left")
            tk.Spinbox(row, from_=0.1, to=10.0, increment=0.1,
                       textvariable=self.delays[i], width=5, format="%.1f",
                       font=("Courier New", 10, "bold"),
                       bg="#1a1a2e", fg=color, buttonbackground="#1a1a2e",
                       insertbackground=color, relief="flat", bd=0).pack(side="left", padx=(4, 0))
            tk.Label(row, text="s", font=("Courier New", 9),
                     bg="#111122", fg="#555577").pack(side="left", padx=2)

        self.status_var = tk.StringVar(value="⏹  Stopped")
        tk.Label(main, textvariable=self.status_var,
                 font=("Courier New", 10, "bold"), bg="#0a0a0f", fg="#888899").pack(pady=(16, 6))

        self.btn = tk.Button(main, text="▶  START", font=("Courier New", 13, "bold"),
                              bg="#00ff88", fg="#0a0a0f", activebackground="#00cc66",
                              activeforeground="#0a0a0f", relief="flat", bd=0,
                              cursor="hand2", command=self.toggle,
                              padx=20, pady=10)
        self.btn.pack(fill="x", pady=4)

        tk.Label(main, text="Auto-detects any running Roblox process",
                 font=("Courier New", 8), bg="#0a0a0f", fg="#333355").pack(pady=(8, 0))

    # ── Controls ──────────────────────────────────────────────────────────────
    def toggle(self):
        global running
        if not running:
            running = True
            self.btn.config(text="⏹  STOP", bg="#ff4466")
            self.status_var.set("🔍 Scanning for Roblox process...")

            def popup_cb(hwnd, proc_name):
                # Must be called back on the main thread via after()
                self.root.after(0, lambda: show_inject_popup(self.root, hwnd, proc_name))

            threading.Thread(
                target=run_sequence,
                args=(self.delays, self.status_var, self.btn, popup_cb),
                daemon=True
            ).start()
        else:
            running = False
            self.btn.config(text="▶  START", bg="#00ff88")

    def start_move(self, event):
        self._offset_x = event.x
        self._offset_y = event.y

    def do_move(self, event):
        x = self.root.winfo_pointerx() - self._offset_x
        y = self.root.winfo_pointery() - self._offset_y
        self.root.geometry(f"+{x}+{y}")


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()