import os
import io
import base64
import asyncio
import requests
import sqlite3
from typing import Optional
from dotenv import load_dotenv
from telegram import Update, InputFile, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# === LOAD ENVIRONMENT VARIABLES ===
load_dotenv()

# === CONFIG ===
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
GEMINI_ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

DB_PATH = "fruits.db"
# Dùng GIF online thay vì file cục bộ (có thể thay URL này bằng GIF bạn thích)
WELCOME_GIF_URL = "https://media0.giphy.com/media/v1.Y2lkPTc5MGI3NjExOHltNTQzczM1bWN6c2VnMnQzb3YyMDJmMTJqcjJjN2hrNHI5MHd4ayZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/k5gCYqpdDZEEpW5Lyz/giphy.gif"

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
    user = update.effective_user
    name = user.first_name or "bạn"

    # Gửi GIF chào mừng từ URL
    try:
        if WELCOME_GIF_URL:
            resp = requests.get(WELCOME_GIF_URL, timeout=20)
            resp.raise_for_status()
            bio = io.BytesIO(resp.content)
            bio.name = "welcome.gif"
            await update.message.reply_animation(animation=InputFile(bio))
    except Exception:
        pass

    # Gửi box greeting đẹp và giàu màu sắc (dùng emoji) + keyboard nhanh
    greeting_message = (
        "🍎🍊🍋🍐🍓🍇🍉🍒🍍\n"
        f"✨ *Xin chào, {name}!* ✨\n\n"
        "🍏 **PMSshop** — Nhận diện trái cây tự động\n"
        "🌿 Giá bán • Mô tả • Gợi ý nhanh\n\n"
        "📸 *Cách dùng nhanh:*\n"
        "- Gửi 1 bức ảnh trái cây bất kỳ\n"
        "- Đợi vài giây để hệ thống xử lý\n"
        "- Nhận kết quả: tên, giá, mô tả ✨\n\n"
        "💡 Gõ */help* để xem hướng dẫn chi tiết.\n"
        "🛍️ Chúc bạn mua sắm vui vẻ tại PMSshop!"
    )

    keyboard = ReplyKeyboardMarkup([["/help", "📸 Gửi ảnh"]], resize_keyboard=True)
    await update.message.reply_text(greeting_message, parse_mode="Markdown", reply_markup=keyboard)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "📖 *Hướng dẫn sử dụng PMSshop*\n\n"
        "- **Bước 1**: Chụp hoặc chọn một *ảnh trái cây*.\n"
        "- **Bước 2**: Gửi ảnh trực tiếp vào cuộc trò chuyện này.\n"
        "- **Bước 3**: Đợi bot *nhận diện* và trả về **tên trái cây**, **giá bán** và **mô tả** (nếu có).\n\n"
        "🔎 Mẹo: Ảnh rõ nét, nền đơn giản sẽ cho kết quả tốt hơn.\n"
        "❔ Nếu hệ thống chưa có loại trái cây đó, bot sẽ thông báo để cửa hàng sớm cập nhật."
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    status_msg = await update.message.reply_text("🔍 Đang nhận diện hình ảnh, vui lòng chờ...")

    try:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        image_bytes = await file.download_as_bytearray()
        mime_type = "image/jpeg"
    except Exception:
        await status_msg.edit_text("❌ Không thể tải hình ảnh.")
        return

    fruit_name = await asyncio.to_thread(call_gemini_api, bytes(image_bytes), mime_type)

    if not fruit_name:
        await status_msg.edit_text("⚠️ Tôi không thể nhận diện chính xác loại trái cây này.")
        return

    info = get_fruit_info(fruit_name)
    if info:
        await status_msg.edit_text(
            f"🍉 **Kết quả nhận diện:** *{info['name'].capitalize()}*\n"
            f"💰 **Giá bán:** {info['price']}\n"
            f"📖 **Mô tả:** {info['description']}",
            parse_mode="Markdown"
        )
    else:
        await status_msg.edit_text(
            f"🙇‍♀️ *Xin lỗi quý khách!* Hiện tại sản phẩm **{fruit_name.capitalize()}** "
            "vẫn chưa có trong danh mục của *PMSshop*. 🍏\n\n"
            "🛒 *Chúng tôi sẽ sớm cập nhật thêm loại trái cây này để phục vụ quý khách tốt hơn!* 💚",
            parse_mode="Markdown"
        )

# === MAIN ===
def main():
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("Thiếu TELEGRAM_BOT_TOKEN. Vui lòng thêm vào .env")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_photo))
    print("🤖 Bot PMSshop đang chạy... Gửi ảnh trái cây để kiểm tra 🍓")
    app.run_polling()

if __name__ == "__main__":
    main()
