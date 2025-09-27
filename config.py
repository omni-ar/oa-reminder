from dotenv import load_dotenv
import os

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
HF_API_KEY = os.getenv("HF_API_KEY")
DB_PATH = os.getenv("DB_PATH", "./data/users.db")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not found in .env")
