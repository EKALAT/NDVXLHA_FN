import os
import base64
import asyncio
import requests
from typing import Optional
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# Load environment variables
load_dotenv()

# === CONFIG ===
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
GEMINI_ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

# === PROMPT ===
VIETNAMESE_PROMPT = (
    "Bạn là hệ thống nhận diện hình ảnh. "
    "Hãy mô tả ngắn gọn (1-2 câu) bằng tiếng Việt về đối tượng chính trong hình. "
    "Nếu có thể, hãy nêu loại vật thể hoặc danh mục. "
    "Chỉ trả lời nội dung kết quả, không kèm giải thích."
)

# === BOT HANDLERS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 Xin chào! Gửi cho tôi một bức ảnh, tôi sẽ giúp bạn nhận diện và mô tả nó bằng tiếng Việt."
    )

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
                    return part["text"].strip()
    except Exception as e:
        print("⚠️ Lỗi xử lý phản hồi:", e)

    return None

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    status_msg = await update.message.reply_text("⏳ Đang nhận diện hình ảnh, vui lòng chờ...")

    try:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        image_bytes = await file.download_as_bytearray()
        mime_type = "image/jpeg"
    except Exception as e:
        await status_msg.edit_text("**Kết quả:** Không thể tải hình ảnh.", parse_mode="Markdown")
        return

    result_text = await asyncio.to_thread(call_gemini_api, bytes(image_bytes), mime_type)

    if result_text:
        await status_msg.edit_text(f"**Kết quả:** {result_text}", parse_mode="Markdown")
    else:
        await status_msg.edit_text("**Kết quả:** Xin lỗi, tôi không thể nhận diện chính xác hình ảnh này.", parse_mode="Markdown")

# === MAIN ===
def main():
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("Thiếu TELEGRAM_BOT_TOKEN. Vui lòng thêm vào .env")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_photo))
    print("🤖 Bot đang chạy... Gửi ảnh đến bot để kiểm tra.")
    app.run_polling()

if __name__ == "__main__":
    main()
