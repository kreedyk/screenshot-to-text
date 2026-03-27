# 💖 Screenshot to Text

A lightweight OCR tool with UI. Capture any region of your screen or load an image file and extract the text in seconds.

---

## ✨ Features

- **Screen capture** - drag to select any area of your screen
- **File loading** - open PNG, JPG, BMP, WebP, and TIFF images
- **Multi-language OCR** - dropdown populated with every language pack you have installed in Tesseract
- **Configurable hotkey** - default `F7`, changeable at runtime and saved between sessions
- **Auto-copy** - extracted text is automatically copied to your clipboard
- **Full clipboard suite** - copy, paste, cut, and clear buttons in the output panel

![image1](https://i.imgur.com/qVJuvcm.png)
![image2](https://i.imgur.com/DnlQzVu.png)

---

## 📋 Requirements

### System dependency - Tesseract OCR

Tesseract must be installed **before** running the app.

| Platform | Instructions |
|----------|-------------|
| **Windows** | Download the installer from [UB-Mannheim/tesseract](https://github.com/UB-Mannheim/tesseract/wiki) and run it. The app detects the default install path automatically. |
| **macOS** | `brew install tesseract` |
| **Linux** | `sudo apt install tesseract-ocr` |

#### Installing extra language packs

By default Tesseract ships with English only. To add more languages:

```bash
# Example: Portuguese
sudo apt install tesseract-ocr-por   # Linux
brew install tesseract-lang          # macOS (installs all languages)
```

On Windows, re-run the Tesseract installer and select the languages you need.

---

## 🚀 Installation

```bash
git clone https://github.com/kreedyk/screenshot-to-text.git
cd screenshot-to-text

# (Optional but recommended) create a virtual environment
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
.venv\Scripts\activate           # Windows

pip install -r requirements.txt
```

---

## ▶️ Usage

```bash
python screenshot_to_text.py
```

| Action | How |
|--------|-----|
| Capture screen area | Click **Screen Capture** or press `F7` |
| Load image file | Click **Open Image** |
| Change OCR language | Use the **Language** dropdown |
| Extract text | Click **Extract Text** (enabled after an image is loaded) |
| Change hotkey | Click **⚙️ Change** next to the hotkey label |

> **Note (Linux/macOS):** The global hotkey feature requires the `keyboard` package, which typically needs `sudo` to capture input globally. If hotkeys don't work, run the app with elevated permissions or use the button instead.

---

## 🛠️ Configuration

Settings are saved automatically to `ocr_settings.json` in the same directory as the script.`

---

## 📦 Dependencies

| Package | Purpose |
|---------|---------|
| `customtkinter` | Modern themed UI widgets |
| `Pillow` | Image loading and processing |
| `pytesseract` | Python wrapper for Tesseract OCR |
| `pyautogui` | Full-screen capture |
| `pyperclip` | Cross-platform clipboard access |
| `keyboard` | Global hotkey registration |

---
