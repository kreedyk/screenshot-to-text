#!/usr/bin/env python3
"""
kreed's Screenshot to Text
==============================
OCR tool with screen capture functionality.
Supports multiple languages, hotkey capture, and file loading.

Dependencies:
    pip install customtkinter pyautogui pytesseract pyperclip Pillow keyboard

Tesseract OCR must be installed separately:
    https://github.com/UB-Mannheim/tesseract/wiki
"""

import json
import logging
import os
import platform
import threading
import time
from pathlib import Path

import customtkinter as ctk
import pyautogui
import pyperclip
import pytesseract
import tkinter as tk
from PIL import Image, ImageTk, UnidentifiedImageError
from tkinter import filedialog, messagebox, simpledialog

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ScreenshotToText")

# ---------------------------------------------------------------------------
# Tesseract path resolution (Windows)
# ---------------------------------------------------------------------------

_TESSERACT_WINDOWS_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]

if platform.system() == "Windows":
    for _path in _TESSERACT_WINDOWS_PATHS:
        if os.path.exists(_path):
            pytesseract.pytesseract.tesseract_cmd = _path
            log.info("Tesseract found at: %s", _path)
            break

# ---------------------------------------------------------------------------
# Optional keyboard module
# ---------------------------------------------------------------------------

try:
    import keyboard
    HAS_KEYBOARD = True
    log.info("Keyboard module loaded successfully.")
except ImportError:
    HAS_KEYBOARD = False
    log.warning("Keyboard module not available — hotkey support disabled.")

# ---------------------------------------------------------------------------
# Application constants
# ---------------------------------------------------------------------------

APP_TITLE      = "kreed's Screenshot to Text"
APP_GEOMETRY   = "920x580"
APP_MIN_SIZE   = (640, 440)
SETTINGS_FILE  = Path("ocr_settings.json")
DEFAULT_HOTKEY = "f7"

# Colour palette
CLR_BG_MAIN    = "#2D1B2E"
CLR_BG_PANEL   = "#3D2B3E"
CLR_PRIMARY    = "#E91E63"
CLR_PRIMARY_HV = "#C2185B"
CLR_SECONDARY  = "#F06292"
CLR_ACCENT     = "#AD1457"
CLR_ACCENT_HV  = "#880E4F"
CLR_DANGER     = "#880E4F"
CLR_DANGER_HV  = "#4A0E4F"
CLR_TEXT_MAIN  = "#FF1493"
CLR_TEXT_SUB   = "#F8BBD9"
CLR_STATUS     = "#FF69B4"

# Supported image types for the file dialog
IMAGE_FILETYPES = [
    ("Images", ["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.webp", "*.tiff"]),
    ("All Files", "*.*"),
]

# Preview constraints (pixels)
PREVIEW_MAX_W = 280
PREVIEW_MAX_H = 280

# ---------------------------------------------------------------------------
# Helper: detect available Tesseract languages
# ---------------------------------------------------------------------------

def get_available_languages() -> list[str]:
    """Return a sorted list of installed Tesseract language codes.

    Falls back to ``["eng"]`` if Tesseract cannot be queried.
    """
    try:
        langs = pytesseract.get_languages(config="")
        # Filter out internal pseudo-languages (osd, snum, equ, …)
        valid = sorted(
            lang for lang in langs
            if len(lang) == 3 and lang.isalpha()
        )
        return valid if valid else ["eng"]
    except Exception as exc:
        log.warning("Could not retrieve Tesseract languages: %s", exc)
        return ["eng"]


# ---------------------------------------------------------------------------
# Settings dataclass
# ---------------------------------------------------------------------------

class Settings:
    """Persistent user preferences stored as JSON."""

    def __init__(self) -> None:
        self.hotkey: str = DEFAULT_HOTKEY
        self.language: str = "eng"

    # ------------------------------------------------------------------
    def load(self) -> None:
        """Load settings from *SETTINGS_FILE*. Silently ignores errors."""
        if not SETTINGS_FILE.exists():
            return
        try:
            with SETTINGS_FILE.open("r", encoding="utf-8") as fh:
                data: dict = json.load(fh)
            self.hotkey   = data.get("hotkey",   DEFAULT_HOTKEY)
            self.language = data.get("language", "eng")
            log.info("Settings loaded: hotkey=%s, language=%s", self.hotkey, self.language)
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Failed to load settings (%s) — using defaults.", exc)

    # ------------------------------------------------------------------
    def save(self) -> None:
        """Persist settings to *SETTINGS_FILE*. Silently ignores errors."""
        try:
            with SETTINGS_FILE.open("w", encoding="utf-8") as fh:
                json.dump({"hotkey": self.hotkey, "language": self.language}, fh, indent=2)
            log.info("Settings saved.")
        except OSError as exc:
            log.warning("Failed to save settings: %s", exc)


# ---------------------------------------------------------------------------
# Main application class
# ---------------------------------------------------------------------------

class ScreenshotToText:
    """Main application window and controller."""

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self) -> None:
        self.settings = Settings()
        self.settings.load()

        # Runtime state
        self.current_image:    Image.Image | None = None
        self.screenshot_image: Image.Image | None = None
        self._bg_photo:        ImageTk.PhotoImage | None = None  # prevent GC
        self._hotkey_active:   bool = False

        # Available OCR languages (resolved once at startup)
        self.available_languages: list[str] = get_available_languages()
        log.info("Available OCR languages: %s", self.available_languages)

        # Ensure saved language is still installed
        if self.settings.language not in self.available_languages:
            self.settings.language = self.available_languages[0]

        # UI references (populated in _build_ui)
        self.root:           ctk.CTk          | None = None
        self.status_var:     tk.StringVar      | None = None
        self.text_output:    ctk.CTkTextbox    | None = None
        self.image_label:    ctk.CTkLabel      | None = None
        self.extract_btn:    ctk.CTkButton     | None = None
        self.info_label:     ctk.CTkLabel      | None = None
        self.hotkey_label:   ctk.CTkLabel      | None = None
        self.lang_var:       tk.StringVar      | None = None
        self.lang_menu:      ctk.CTkOptionMenu | None = None

        self._build_ui()
        self._register_hotkey()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Build and configure the main application window."""
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("green")
        pyautogui.FAILSAFE = False

        self.root = ctk.CTk()
        self.root.title(f"💖 {APP_TITLE}")
        self.root.geometry(APP_GEOMETRY)
        self.root.minsize(*APP_MIN_SIZE)

        self.root.grid_columnconfigure((0, 1), weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        self._build_left_panel()
        self._build_right_panel()

        # Status bar
        self.status_var = tk.StringVar(value=f"✨ Ready — press {self.settings.hotkey.upper()} to capture or open a file")
        ctk.CTkLabel(
            self.root,
            textvariable=self.status_var,
            font=ctk.CTkFont(size=12),
            text_color=CLR_STATUS,
        ).grid(row=1, column=0, columnspan=2, pady=(0, 10))

    # ------------------------------------------------------------------

    def _build_left_panel(self) -> None:
        """Construct the left control/preview panel."""
        frame = ctk.CTkFrame(self.root, fg_color=CLR_BG_MAIN)
        frame.grid(row=0, column=0, sticky="nsew", padx=(20, 10), pady=20)
        frame.grid_rowconfigure(4, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        # Title
        ctk.CTkLabel(
            frame,
            text="💖 SCREENSHOT TO TEXT",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=CLR_TEXT_MAIN,
        ).grid(row=0, column=0, pady=(20, 2))

        ctk.CTkLabel(
            frame,
            text="github.com/kreedyk",
            font=ctk.CTkFont(size=11),
            text_color=CLR_TEXT_SUB,
        ).grid(row=1, column=0, pady=(0, 12))

        # Action buttons
        btn_frame = ctk.CTkFrame(frame, fg_color=CLR_BG_PANEL)
        btn_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=6)
        btn_frame.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            btn_frame,
            text="📷  Screen Capture",
            command=self._start_screenshot,
            font=ctk.CTkFont(size=13, weight="bold"),
            height=38,
            fg_color=CLR_PRIMARY,
            hover_color=CLR_PRIMARY_HV,
        ).grid(row=0, column=0, padx=(10, 5), pady=10, sticky="ew")

        ctk.CTkButton(
            btn_frame,
            text="📁  Open Image",
            command=self._open_file,
            font=ctk.CTkFont(size=13, weight="bold"),
            height=38,
            fg_color=CLR_SECONDARY,
            hover_color=CLR_PRIMARY,
        ).grid(row=0, column=1, padx=(5, 10), pady=10, sticky="ew")

        # Hotkey + language settings
        cfg_frame = ctk.CTkFrame(frame, fg_color=CLR_BG_PANEL)
        cfg_frame.grid(row=3, column=0, sticky="ew", padx=20, pady=6)
        cfg_frame.grid_columnconfigure(1, weight=1)

        self.hotkey_label = ctk.CTkLabel(
            cfg_frame,
            text=f"⌨️  Hotkey: {self.settings.hotkey.upper()}",
            font=ctk.CTkFont(size=12),
            text_color=CLR_STATUS,
        )
        self.hotkey_label.grid(row=0, column=0, padx=(12, 6), pady=8, sticky="w")

        ctk.CTkButton(
            cfg_frame,
            text="⚙️ Change",
            command=self._change_hotkey,
            width=100,
            height=28,
            fg_color=CLR_ACCENT,
            hover_color=CLR_ACCENT_HV,
        ).grid(row=0, column=1, padx=(0, 6), pady=8, sticky="e")

        # Language selector
        ctk.CTkLabel(
            cfg_frame,
            text="🌐  Language:",
            font=ctk.CTkFont(size=12),
            text_color=CLR_STATUS,
        ).grid(row=1, column=0, padx=(12, 6), pady=(0, 8), sticky="w")

        self.lang_var = tk.StringVar(value=self.settings.language)
        self.lang_menu = ctk.CTkOptionMenu(
            cfg_frame,
            variable=self.lang_var,
            values=self.available_languages,
            command=self._on_language_changed,
            fg_color=CLR_ACCENT,
            button_color=CLR_ACCENT_HV,
            button_hover_color=CLR_DANGER,
            width=110,
            height=28,
        )
        self.lang_menu.grid(row=1, column=1, padx=(0, 6), pady=(0, 8), sticky="e")

        # Image preview
        preview_frame = ctk.CTkFrame(frame, fg_color=CLR_BG_PANEL)
        preview_frame.grid(row=4, column=0, sticky="nsew", padx=20, pady=6)
        preview_frame.grid_rowconfigure(0, weight=1)
        preview_frame.grid_columnconfigure(0, weight=1)

        self.image_label = ctk.CTkLabel(
            preview_frame,
            text="💕\n\nDrag an image here or\nuse the buttons above\n\nSupported: PNG · JPG · BMP · WebP · TIFF",
            font=ctk.CTkFont(size=13),
            text_color=CLR_TEXT_SUB,
        )
        self.image_label.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")

        # Extract button
        self.extract_btn = ctk.CTkButton(
            frame,
            text="✨  Extract Text",
            command=self._extract_text,
            font=ctk.CTkFont(size=15, weight="bold"),
            height=42,
            state="disabled",
            fg_color=CLR_PRIMARY,
            hover_color=CLR_PRIMARY_HV,
        )
        self.extract_btn.grid(row=5, column=0, padx=20, pady=(6, 20), sticky="ew")

    # ------------------------------------------------------------------

    def _build_right_panel(self) -> None:
        """Construct the right text output panel."""
        frame = ctk.CTkFrame(self.root, fg_color=CLR_BG_MAIN)
        frame.grid(row=0, column=1, sticky="nsew", padx=(10, 20), pady=20)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            frame,
            text="💝  Extracted Text",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=CLR_TEXT_MAIN,
        ).grid(row=0, column=0, pady=(20, 8))

        self.text_output = ctk.CTkTextbox(
            frame,
            font=ctk.CTkFont(size=12),
            wrap="word",
            fg_color=CLR_BG_PANEL,
            text_color=CLR_TEXT_SUB,
        )
        self.text_output.grid(row=1, column=0, sticky="nsew", padx=20, pady=6)

        # Clipboard action buttons
        btn_frame = ctk.CTkFrame(frame, fg_color=CLR_BG_PANEL)
        btn_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=6)
        btn_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        actions = [
            ("💕 Copy",  self._copy_text,  CLR_PRIMARY,  CLR_PRIMARY_HV),
            ("🌸 Paste", self._paste_text, CLR_SECONDARY, CLR_PRIMARY),
            ("✂️ Cut",   self._cut_text,   CLR_ACCENT,   CLR_ACCENT_HV),
            ("🗑️ Clear", self._clear_text, CLR_DANGER,   CLR_DANGER_HV),
        ]
        for col, (label, cmd, fg, hv) in enumerate(actions):
            ctk.CTkButton(
                btn_frame, text=label, command=cmd,
                fg_color=fg, hover_color=hv, width=80,
            ).grid(row=0, column=col, padx=5, pady=10, sticky="ew")

        # Info / stats bar
        info_frame = ctk.CTkFrame(frame, fg_color=CLR_BG_PANEL)
        info_frame.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 20))

        self.info_label = ctk.CTkLabel(
            info_frame,
            text="🌟 No text extracted yet…",
            font=ctk.CTkFont(size=11),
            text_color=CLR_TEXT_SUB,
        )
        self.info_label.grid(row=0, column=0, padx=10, pady=8)

    # ------------------------------------------------------------------
    # Settings callbacks
    # ------------------------------------------------------------------

    def _on_language_changed(self, selected: str) -> None:
        """Handle OCR language selection change."""
        self.settings.language = selected
        self.settings.save()
        self._set_status(f"🌐 OCR language set to: {selected.upper()}")
        log.info("OCR language changed to: %s", selected)

    # ------------------------------------------------------------------

    def _change_hotkey(self) -> None:
        """Prompt the user to enter a new global hotkey."""
        previous = self.settings.hotkey
        new_hotkey = simpledialog.askstring(
            "Change Hotkey",
            f"Current hotkey: {previous.upper()}\n\nEnter new hotkey (e.g. f7, f8, ctrl+shift+s):",
            initialvalue=previous,
        )

        if not new_hotkey or not new_hotkey.strip() or new_hotkey.strip().lower() == previous:
            return

        candidate = new_hotkey.strip().lower()
        self._unregister_hotkey()
        self.settings.hotkey = candidate

        if self._register_hotkey():
            self.hotkey_label.configure(text=f"⌨️  Hotkey: {candidate.upper()}")
            self.settings.save()
            self._set_status(f"✨ Hotkey changed to {candidate.upper()}")
            log.info("Hotkey changed to: %s", candidate)
            messagebox.showinfo("Hotkey Updated", f"New hotkey: {candidate.upper()}")
        else:
            # Rollback to previous hotkey on failure
            log.warning("Failed to register hotkey '%s' — reverting to '%s'.", candidate, previous)
            self.settings.hotkey = previous
            self._register_hotkey()
            self.hotkey_label.configure(text=f"⌨️  Hotkey: {previous.upper()}")
            messagebox.showerror(
                "Registration Failed",
                f"Could not register hotkey: {candidate}\n\nReverted to: {previous.upper()}",
            )

    # ------------------------------------------------------------------
    # Hotkey management
    # ------------------------------------------------------------------

    def _register_hotkey(self) -> bool:
        """Register the global hotkey.

        Returns:
            ``True`` on success, ``False`` otherwise.
        """
        if not HAS_KEYBOARD:
            return False
        try:
            keyboard.add_hotkey(self.settings.hotkey, self._start_screenshot)
            self._hotkey_active = True
            log.info("Global hotkey registered: %s", self.settings.hotkey.upper())
            return True
        except Exception as exc:
            log.error("Hotkey registration failed: %s", exc)
            self._hotkey_active = False
            return False

    # ------------------------------------------------------------------

    def _unregister_hotkey(self) -> None:
        """Unregister any active global hotkey."""
        if self._hotkey_active and HAS_KEYBOARD:
            try:
                keyboard.unhook_all()
                log.info("Global hotkey unregistered.")
            except Exception as exc:
                log.warning("Failed to unregister hotkey: %s", exc)
            finally:
                self._hotkey_active = False

    # ------------------------------------------------------------------
    # Screenshot / capture
    # ------------------------------------------------------------------

    def _start_screenshot(self) -> None:
        """Hide the main window and initiate screen capture."""
        self._set_status("📷 Preparing capture…")
        self.root.withdraw()
        self.root.after(300, self._capture_screen)

    # ------------------------------------------------------------------

    def _capture_screen(self) -> None:
        """Capture the full screen and open the selection overlay."""
        try:
            self.screenshot_image = pyautogui.screenshot()
            self._open_selection_overlay()
        except Exception as exc:
            self.root.deiconify()
            log.error("Screen capture failed: %s", exc)
            messagebox.showerror("Capture Failed", f"Could not take screenshot:\n{exc}")

    # ------------------------------------------------------------------

    def _open_selection_overlay(self) -> None:
        """Open a full-screen overlay so the user can drag a selection."""
        overlay = tk.Toplevel()
        overlay.attributes("-fullscreen", True)
        overlay.attributes("-topmost", True)
        overlay.configure(bg="black")

        canvas = tk.Canvas(overlay, highlightthickness=0, bg="black")
        canvas.pack(fill=tk.BOTH, expand=True)

        # Render frozen screenshot as background
        sw = overlay.winfo_screenwidth()
        sh = overlay.winfo_screenheight()
        iw, ih = self.screenshot_image.size

        display = (
            self.screenshot_image
            if iw <= sw and ih <= sh
            else self.screenshot_image.resize((sw, sh), Image.Resampling.LANCZOS)
        )

        self._bg_photo = ImageTk.PhotoImage(display)
        canvas.create_image(0, 0, anchor=tk.NW, image=self._bg_photo)
        canvas.create_rectangle(0, 0, sw, sh, fill="black", stipple="gray25", outline="")
        canvas.create_text(
            sw // 2, 46,
            text="💖  Drag to select area  •  ESC to cancel",
            fill="#FF69B4",
            font=("Arial", 16, "bold"),
        )

        # Selection state
        state: dict = {"x0": None, "y0": None, "rect": None}

        def on_press(event: tk.Event) -> None:
            state["x0"] = event.x
            state["y0"] = event.y
            if state["rect"]:
                canvas.delete(state["rect"])
            state["rect"] = canvas.create_rectangle(
                event.x, event.y, event.x, event.y,
                outline="#FF1493", width=3,
            )

        def on_drag(event: tk.Event) -> None:
            if state["rect"]:
                canvas.coords(state["rect"], state["x0"], state["y0"], event.x, event.y)

        def on_release(event: tk.Event) -> None:
            x0, y0 = state["x0"], state["y0"]
            if x0 is None:
                return
            x1 = min(x0, event.x);  x2 = max(x0, event.x)
            y1 = min(y0, event.y);  y2 = max(y0, event.y)
            self._bg_photo = None
            overlay.destroy()

            if (x2 - x1) > 10 and (y2 - y1) > 10:
                cropped = self.screenshot_image.crop((x1, y1, x2, y2))
                self._load_image(cropped, label="Screen capture")
                self.root.deiconify()
            else:
                self.root.deiconify()
                self._set_status("❌ Selection too small — try again")

        def on_cancel(event: tk.Event) -> None:
            self._bg_photo = None
            overlay.destroy()
            self.root.deiconify()
            self._set_status("❌ Capture cancelled")

        canvas.bind("<Button-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)
        overlay.bind("<Escape>", on_cancel)

    # ------------------------------------------------------------------
    # File loading
    # ------------------------------------------------------------------

    def _open_file(self) -> None:
        """Open an image file via the file dialog."""
        path = filedialog.askopenfilename(title="Select Image", filetypes=IMAGE_FILETYPES)
        if not path:
            return

        try:
            image = Image.open(path)
            basename = Path(path).name
            display_name = basename if len(basename) < 30 else basename[:27] + "…"
            self._load_image(image, label=f"File: {display_name}")
            self._set_status(f"✨ Loaded: {display_name}")
            log.info("Image loaded from file: %s", path)
        except UnidentifiedImageError:
            messagebox.showerror("Invalid File", "The selected file is not a recognised image format.")
        except OSError as exc:
            log.error("Failed to open image: %s", exc)
            messagebox.showerror("Open Failed", f"Could not open file:\n{exc}")

    # ------------------------------------------------------------------

    def _load_image(self, image: Image.Image, label: str = "") -> None:
        """Store *image* as the current OCR source and update the preview."""
        self.current_image = image
        self._update_preview(image, label)
        self._set_status("✨ Image ready — click Extract Text to begin")

    # ------------------------------------------------------------------
    # Image preview
    # ------------------------------------------------------------------

    def _update_preview(self, image: Image.Image, label: str = "") -> None:
        """Scale *image* to fit the preview area and display it."""
        try:
            iw, ih = image.size
            scale   = min(PREVIEW_MAX_W / iw, PREVIEW_MAX_H / ih)
            nw, nh  = max(1, int(iw * scale)), max(1, int(ih * scale))

            thumb    = image.copy().resize((nw, nh), Image.Resampling.LANCZOS)
            ctk_img  = ctk.CTkImage(light_image=thumb, dark_image=thumb, size=(nw, nh))

            self.image_label.configure(image=ctk_img, text="")
            self.extract_btn.configure(state="normal")
        except Exception as exc:
            log.warning("Could not render preview: %s", exc)
            self.image_label.configure(text=f"🌸 {label or 'Image loaded'}")
            self.extract_btn.configure(state="normal")

    # ------------------------------------------------------------------
    # OCR extraction
    # ------------------------------------------------------------------

    def _extract_text(self) -> None:
        """Run OCR on the current image in a background thread."""
        if not self.current_image:
            messagebox.showwarning("No Image", "Please load or capture an image first.")
            return

        lang = self.lang_var.get()
        self._set_status("✨ Extracting text…")
        self.extract_btn.configure(state="disabled")
        log.info("Starting OCR with language: %s", lang)

        def worker() -> None:
            start = time.perf_counter()
            try:
                text = pytesseract.image_to_string(self.current_image, lang=lang)
                elapsed = time.perf_counter() - start
                self.root.after(0, self._on_extraction_done, text, elapsed, lang)
            except pytesseract.TesseractError as exc:
                self.root.after(0, self._on_extraction_error, str(exc))
            except Exception as exc:
                log.exception("Unexpected OCR error")
                self.root.after(0, self._on_extraction_error, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------

    def _on_extraction_done(self, text: str, elapsed: float, lang: str) -> None:
        """Update the UI after a successful OCR run."""
        self.extract_btn.configure(state="normal")
        self.text_output.delete("1.0", tk.END)

        stripped = text.strip()
        if stripped:
            self.text_output.insert("1.0", text)
            pyperclip.copy(stripped)

            chars = len(stripped)
            lines = stripped.count("\n") + 1
            self.info_label.configure(
                text=f"✨ {chars} chars  •  {lines} lines  •  {elapsed:.2f}s  •  {lang.upper()}  •  copied!"
            )
            self._set_status(f"💖 Extraction complete ({chars} characters)")
            log.info("OCR completed: %d chars in %.2fs using '%s'.", chars, elapsed, lang)
        else:
            self.info_label.configure(text="❌ No text detected in the selected area")
            self._set_status("❌ No text detected")
            log.warning("OCR returned no text for language '%s'.", lang)

    # ------------------------------------------------------------------

    def _on_extraction_error(self, message: str) -> None:
        """Handle an OCR failure."""
        self.extract_btn.configure(state="normal")
        self._set_status("❌ Extraction failed")
        log.error("OCR error: %s", message)
        messagebox.showerror("Extraction Error", f"OCR failed:\n\n{message}")

    # ------------------------------------------------------------------
    # Clipboard helpers
    # ------------------------------------------------------------------

    def _copy_text(self) -> None:
        """Copy selected text (or all text) to the clipboard."""
        try:
            text = self.text_output.selection_get()
        except tk.TclError:
            text = self.text_output.get("1.0", tk.END).strip()

        if text:
            pyperclip.copy(text)
            self._set_status("💕 Copied to clipboard!")
        else:
            self._set_status("❌ Nothing to copy")

    # ------------------------------------------------------------------

    def _paste_text(self) -> None:
        """Paste clipboard content at the current cursor position."""
        try:
            self.text_output.insert(tk.INSERT, self.root.clipboard_get())
            self._set_status("🌸 Pasted from clipboard")
        except tk.TclError:
            self._set_status("❌ Clipboard is empty")

    # ------------------------------------------------------------------

    def _cut_text(self) -> None:
        """Cut the selected text to the clipboard."""
        try:
            text = self.text_output.selection_get()
            pyperclip.copy(text)
            self.text_output.delete(tk.SEL_FIRST, tk.SEL_LAST)
            self._set_status("✂️ Cut to clipboard")
        except tk.TclError:
            self._set_status("❌ No text selected")

    # ------------------------------------------------------------------

    def _clear_text(self) -> None:
        """Clear the text output area."""
        self.text_output.delete("1.0", tk.END)
        self.info_label.configure(text="🌟 Text cleared")
        self._set_status("🗑️ Text cleared")

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _set_status(self, message: str) -> None:
        """Update the status bar label. Thread-safe via *after* when needed."""
        try:
            self.status_var.set(message)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Application entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Start the Tkinter event loop."""
        log.info("Application started.")
        try:
            self.root.mainloop()
        finally:
            self._unregister_hotkey()
            log.info("Application closed.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _verify_tesseract() -> bool:
    """Check that Tesseract is installed and accessible.

    Returns:
        ``True`` if Tesseract is available, ``False`` otherwise.
    """
    try:
        version = pytesseract.get_tesseract_version()
        log.info("Tesseract version: %s", version)
        return True
    except pytesseract.TesseractNotFoundError:
        messagebox.showerror(
            "Tesseract Not Found",
            "Tesseract-OCR is not installed or is not in your PATH.\n\n"
            "Download it from:\n"
            "https://github.com/UB-Mannheim/tesseract/wiki",
        )
        return False


def main() -> None:
    """Application entry point."""
    log.info("Launching %s…", APP_TITLE)
    if not _verify_tesseract():
        return
    ScreenshotToText().run()


if __name__ == "__main__":
    main()