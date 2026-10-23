
import os
import re
import asyncio

from aiohttp import web
from dotenv import load_dotenv
from instaloader import Instaloader, Post
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# Lokal kompyuterda .env faylini ham o'qish mumkin.
# Render'da Environment Variables ishlatiladi.
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", "10000"))

# Instagram yuklovchi
loader = Instaloader()


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.message:
        await update.message.reply_text(
            "👋 Salom! Instagram video yoki rasm havolasini yuboring."
        )


def download_instagram_media(url: str):
    """Instagram postidan media URL manzilini oladi."""
    try:
        pattern = r"(?:www\.)?instagram\.com/(?:p|reel|tv)/([\w-]+)"
        match = re.search(pattern, url)

        if not match:
            return None

        shortcode = match.group(1)
        post = Post.from_shortcode(loader.context, shortcode)

        if post.is_video:
            return post.video_url

        return post.url

    except Exception as e:
        print(f"Instagram xatosi: {e}")
        return None


async def handle_instagram_url(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not update.message or not update.message.text:
        return

    url = update.message.text.strip()

    await update.message.reply_text("⏳ Yuklab olinmoqda...")

    # Sinxron Instaloader amali bot event loop'ini to'sib qo'ymasligi uchun
    media_url = await asyncio.to_thread(
        download_instagram_media, url
    )

    if not media_url:
        await update.message.reply_text(
            "❌ Media topilmadi. Havolani tekshirib qayta yuboring."
        )
        return

    try:
        if media_url.split("?")[0].lower().endswith(".mp4"):
            await update.message.reply_video(video=media_url)
        else:
            await update.message.reply_photo(photo=media_url)

    except Exception as e:
        print(f"Telegram media yuborish xatosi: {e}")
        await update.message.reply_text(
            "❌ Media yuborilmadi. Instagram havolasi "
            "yoki media formati bilan muammo bo'lishi mumkin."
        )


# UptimeRobot uchun HTTP endpointlar
async def health_check(request: web.Request) -> web.Response:
    return web.Response(text="OK", status=200)


async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN topilmadi. Environment Variables'ni tekshiring."
        )

    # Telegram bot
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT
            & filters.Regex(r"(?i)instagram\.com/"),
            handle_instagram_url,
        )
    )

    # Oddiy aiohttp web-server
    web_app = web.Application()
    web_app.router.add_get("/", health_check)
    web_app.router.add_get("/health", health_check)

    runner = web.AppRunner(web_app)

    try:
        # HTTP serverni ishga tushirish
        await runner.setup()
        site = web.TCPSite(
            runner,
            host="0.0.0.0",
            port=PORT,
        )
        await site.start()

        # Telegram botni polling rejimida ishga tushirish
        await application.initialize()
        await application.start()

        if application.updater is None:
            raise RuntimeError("Telegram updater mavjud emas.")

        await application.updater.start_polling()

        print(f"Bot ishga tushdi. HTTP server porti: {PORT}")

        # Ikkala vazifa ham ishlashda davom etadi
        await asyncio.Event().wait()

    finally:
        # Jarayon to'xtatilganda resurslarni yopish
        if application.updater is not None:
            if application.updater.running:
                await application.updater.stop()

        if application.running:
            await application.stop()

        await application.shutdown()
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
