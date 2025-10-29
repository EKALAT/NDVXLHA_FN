import os
import base64
import asyncio
import requests
import sqlite3
from typing import Optional
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# Load environment variables
load_dotenv()

# === CONFIG ===
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
GEMINI_ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

DB_PATH = "fruits.db"

# === PROMPT ===
VIETNAMESE_PROMPT = (
    "Bạn là hệ thống nhận diện hình ảnh. "
    "Hãy xác định loại trái cây trong ảnh và trả lại duy nhất tên loại trái cây bằng tiếng Việt, "
    "không kèm câu giải thích, chỉ 1 từ hoặc cụm từ ngắn (ví dụ: 'chuối', 'xoài', 'cam')."
)

# === DATABASE ===
def get_fruit_info(fruit_name: str) -> Optional[dict]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name, price, description FROM fruits WHERE LOWER(name)=?", (fruit_name.lower(),))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"name": row[0], "price": row[1], "description": row[2]}
    return None

# === GEMINI ===
def _build_gemini_request_body(image_b64: str, mime_type: str) -> dict:
    return {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": VIETNAMESE_PROMPT},
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": image_b64,
                        }
                    },
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
    except requests.RequestException as e:
        print("❌ Lỗi khi gọi Gemini API:", e)
        return None

    try:
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            for part in parts:
                if "text" in part:
                    return part["text"].strip().lower()
    except Exception as e:
        print("⚠️ Lỗi xử lý phản hồi:", e)

    return None

# === TELEGRAM HANDLERS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🍎 Xin chào! Gửi cho tôi một bức ảnh trái cây 🍇, tôi sẽ nhận diện và cho bạn biết thông tin chi tiết!"
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    status_msg = await update.message.reply_text("⏳ Đang nhận diện hình ảnh, vui lòng chờ...")

    try:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        image_bytes = await file.download_as_bytearray()
        mime_type = "image/jpeg"
    except Exception as e:
        await status_msg.edit_text("❌ Không thể tải hình ảnh.", parse_mode="Markdown")
        return

    fruit_name = await asyncio.to_thread(call_gemini_api, bytes(image_bytes), mime_type)

    if not fruit_name:
        await status_msg.edit_text("⚠️ Tôi không thể nhận diện chính xác loại trái cây này.", parse_mode="Markdown")
        return

    info = get_fruit_info(fruit_name)
    if info:
        await status_msg.edit_text(
            f"**Kết quả nhận diện:** {info['name'].capitalize()}\n"
            f"**Giá bán:** {info['price']}\n"
            f"**Mô tả:** {info['description']}",
            parse_mode="Markdown"
        )
    else:
        await status_msg.edit_text(
            f"**Kết quả nhận diện:** {fruit_name.capitalize()}\n"
            f"❌ Hiện chưa có thông tin về loại trái cây này trong cơ sở dữ liệu.",
            parse_mode="Markdown"
        )

# === MAIN ===
def main():
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("Thiếu TELEGRAM_BOT_TOKEN. Vui lòng thêm vào .env")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_photo))
    print("🤖 Bot đang chạy... Gửi ảnh trái cây để kiểm tra.")
    app.run_polling()

if __name__ == "__main__":
    main()
