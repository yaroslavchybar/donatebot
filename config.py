import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

_admin_id = os.getenv("ADMIN_ID")
ADMIN_ID = int(_admin_id.strip()) if _admin_id else None

CONVEX_URL = os.getenv("CONVEX_URL")
CONVEX_AUTHORIZATION = os.getenv("CONVEX_AUTHORIZATION")
