import os

# ─── BOT SETTINGS ─────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
BOT_USERNAME = os.getenv("BOT_USERNAME", "")  # без @

# ─── ADMIN ────────────────────────────────────────────────────────────────────
# Укажи свой Telegram ID в переменной окружения ADMIN_ID
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# ─── DATABASE ─────────────────────────────────────────────────────────────────
DB_PATH = "whisperlink.db"

# ─── VALIDATION ───────────────────────────────────────────────────────────────
if not BOT_TOKEN:
    raise ValueError("Переменная окружения BOT_TOKEN не задана!")
if not BOT_USERNAME:
    raise ValueError("Переменная окружения BOT_USERNAME не задана!")
if ADMIN_ID == 0:
    raise ValueError("Переменная окружения ADMIN_ID не задана!")
