import os
import io
import base64
import asyncio
import requests
import sqlite3
from typing import Optional
from dotenv import load_dotenv
from telegram import Update, InputFile, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler,
    ConversationHandler, filters
)

# === LOAD ENVIRONMENT VARIABLES ===
load_dotenv()

# === CONFIG ===
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
ADMIN_ID = int(os.getenv("ADMIN_ID", "6079753756"))  # ID Telegram của admin

GEMINI_ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
DB_PATH = "fruits.db"

WELCOME_GIF_URL = "https://media0.giphy.com/media/v1.Y2lkPTc5MGI3NjExOHltNTQzczM1bWN6c2VnMnQzb3YyMDJmMTJqcjJjN2hrNHI5MHd4ayZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/k5gCYqpdDZEEpW5Lyz/giphy.gif"

# === PROMPT ===
VIETNAMESE_PROMPT = (
    "Bạn là hệ thống nhận diện hình ảnh. "
    "Hãy xác định loại trái cây trong ảnh và trả lại duy nhất tên loại trái cây bằng tiếng Việt, "
    "không kèm câu giải thích, chỉ 1 từ hoặc cụm từ ngắn (ví dụ: 'chuối', 'xoài', 'cam')."
)

# === DATABASE ===
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fruits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            price TEXT,
            description TEXT
        )
    """)
    conn.commit()
    conn.close()

def get_fruit_info(fruit_name: str) -> Optional[dict]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name, price, description FROM fruits WHERE LOWER(name)=?", (fruit_name.lower(),))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"name": row[0], "price": row[1], "description": row[2]}
    return None

def list_all_fruits() -> list:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, price, description FROM fruits ORDER BY id ASC")
    fruits = cursor.fetchall()
    conn.close()
    return fruits

# === GEMINI ===
def _build_gemini_request_body(image_b64: str, mime_type: str) -> dict:
    return {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": VIETNAMESE_PROMPT},
                    {"inline_data": {"mime_type": mime_type, "data": image_b64}},
                ],
            }
        ]
    }

def call_gemini_api(image_bytes: bytes, mime_type: str) -> Optional[str]:
    if not GEMINI_API_KEY:
        return None
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    body = _build_gemini_request_body(image_b64, mime_type)
    params = {"key": GEMINI_API_KEY}
    try:
        response = requests.post(GEMINI_ENDPOINT, params=params, json=body, timeout=60)
        response.raise_for_status()
        data = response.json()
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            for part in parts:
                if "text" in part:
                    return part["text"].strip().lower()
    except Exception as e:
        print("❌ Gemini API Error:", e)
    return None

# === TELEGRAM HANDLERS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    name = user.first_name or "bạn"
    try:
        if WELCOME_GIF_URL:
            resp = requests.get(WELCOME_GIF_URL, timeout=20)
            resp.raise_for_status()
            bio = io.BytesIO(resp.content)
            bio.name = "welcome.gif"
            await update.message.reply_animation(animation=InputFile(bio))
    except Exception:
        pass

    greeting_message = (
        f"🍎 Xin chào, *{name}!* 🍇\n\n"
        "🌿 **PMSshop - Nhận diện trái cây tự động** 🌿\n\n"
        "📸 Gửi 1 bức ảnh trái cây bất kỳ để nhận kết quả!\n"
        "💰 Xem giá và mô tả chi tiết.\n\n"
        "🧭 /help để xem hướng dẫn.\n"
    )

    if user.id == ADMIN_ID:
        greeting_message += "\n🛠️ *Bạn đang đăng nhập với quyền Admin.*\nDùng /admin để xem menu quản lý."
        keyboard = ReplyKeyboardMarkup([["/admin", "/help"]], resize_keyboard=True)
    else:
        keyboard = ReplyKeyboardMarkup([["📸 Gửi ảnh", "/help"]], resize_keyboard=True)

    await update.message.reply_text(greeting_message, parse_mode="Markdown", reply_markup=keyboard)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📖 *Hướng dẫn sử dụng PMSshop*\n\n"
        "- **Bước 1**: Gửi ảnh trái cây bạn muốn nhận diện.\n"
        "- **Bước 2**: Đợi bot xử lý (2–5 giây).\n"
        "- **Bước 3**: Nhận kết quả gồm *tên*, *giá* và *mô tả sản phẩm*.\n\n"
        "❗ Nếu sản phẩm chưa có, hệ thống sẽ thông báo để cập nhật."
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("🔍 Đang nhận diện hình ảnh...")
    try:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        image_bytes = await file.download_as_bytearray()
        fruit_name = await asyncio.to_thread(call_gemini_api, bytes(image_bytes), "image/jpeg")
    except Exception:
        await status_msg.edit_text("❌ Không thể tải ảnh hoặc xử lý.")
        return

    if not fruit_name:
        await status_msg.edit_text("⚠️ Không thể nhận diện loại trái cây này.")
        return

    info = get_fruit_info(fruit_name)
    if info:
        await status_msg.edit_text(
            f"🍉 **Kết quả:** *{info['name'].capitalize()}*\n"
            f"💰 Giá: {info['price']}\n"
            f"📖 Mô tả: {info['description']}",
            parse_mode="Markdown"
        )
    else:
        await status_msg.edit_text(
            f"🙇‍♀️ Xin lỗi, sản phẩm *{fruit_name.capitalize()}* chưa có trong hệ thống.\n"
            "🛒 Chúng tôi sẽ cập nhật sớm!",
            parse_mode="Markdown"
        )

# === ADMIN FUNCTIONS ===
async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Bạn không có quyền truy cập.")
        return
    menu = (
        "🛠️ *Menu Quản lý Admin*\n\n"
        "/addfruit - Thêm trái cây mới\n"
        "/updatefruit - Cập nhật thông tin\n"
        "/deletefruit - Xóa sản phẩm\n"
        "/listfruits - Xem danh sách tất cả\n"
    )
    await update.message.reply_text(menu, parse_mode="Markdown")

async def add_fruit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("🚫 Bạn không có quyền này.")
    try:
        args = context.args
        if len(args) < 3:
            return await update.message.reply_text("📌 Cú pháp: /addfruit <tên> <giá> <mô tả>")
        name, price, description = args[0], args[1], " ".join(args[2:])
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO fruits (name, price, description) VALUES (?, ?, ?)", (name, price, description))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ Đã thêm sản phẩm *{name}* thành công!", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi thêm sản phẩm: {e}")

async def update_fruit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("🚫 Không có quyền.")
    try:
        args = context.args
        if len(args) < 3:
            return await update.message.reply_text("📌 Cú pháp: /updatefruit <tên> <giá> <mô tả>")
        name, price, description = args[0], args[1], " ".join(args[2:])
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE fruits SET price=?, description=? WHERE LOWER(name)=?", (price, description, name.lower()))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✏️ Đã cập nhật sản phẩm *{name}*!", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi cập nhật: {e}")

async def delete_fruit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("🚫 Không có quyền.")
    try:
        args = context.args
        if not args:
            return await update.message.reply_text("📌 Cú pháp: /deletefruit <tên>")
        name = " ".join(args)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM fruits WHERE LOWER(name)=?", (name.lower(),))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"🗑️ Đã xóa sản phẩm *{name}*!", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi xóa: {e}")

async def list_fruits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("🚫 Không có quyền.")
    fruits = list_all_fruits()
    if not fruits:
        await update.message.reply_text("📭 Chưa có sản phẩm nào.")
        return
    msg = "📋 *Danh sách trái cây:*\n\n"
    for idx, (_fid, name, price, desc) in enumerate(fruits, start=1):
        msg += f"{idx}. *{name}* — 💰 {price}\n📖 {desc}\n\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

# === MAIN ===
def main():
    init_db()
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("Thiếu TELEGRAM_BOT_TOKEN trong .env")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("admin", admin_menu))
    app.add_handler(CommandHandler("addfruit", add_fruit))
    app.add_handler(CommandHandler("updatefruit", update_fruit))
    app.add_handler(CommandHandler("deletefruit", delete_fruit))
    app.add_handler(CommandHandler("listfruits", list_fruits))
    app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_photo))

    print("🤖 Bot PMSshop đang chạy... (Admin có thể thêm/sửa/xóa sản phẩm)")
    app.run_polling()

if __name__ == "__main__":
    main()
