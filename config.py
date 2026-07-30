
import os

class Config:
    # ——— Bot Settings ———
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "8680846598:AAE0o3vS2fn16ZuIvvPJjXeuPQubDT2eUo8")
    ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "8691519315").split(",")]
    
    # ——— Web App URL (your Render domain) ———
    # Render पर deploy करने के बाद यह अपने-आप set हो जाएगा
    BASE_URL = os.environ.get("BASE_URL", "")
    
    # ——— Bot Webhook Path ———
    WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"  # Secret path, कोई और hit न करे
    
    # ——— Database ———
    DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///bot_data.db")
