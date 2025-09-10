import os

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bot.helpers import convert_to_pdf, is_allowed, print_file
from bot.settings import Settings


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert update.effective_user is not None
    assert update.message is not None

    user_id = update.effective_user.id
    allowed_users = context.bot_data.get("allowed_users")
    if not is_allowed(user_id, allowed_users):
        await update.message.reply_text("⛔ You are not authorized to use this bot.")
        return

    file_path = None
    printable_path = None

    try:
        if update.message.document:
            doc = update.message.document
            file = await context.bot.get_file(doc.file_id)
            file_path = f"/tmp/{doc.file_name}"
            await file.download_to_drive(file_path)

            assert doc.file_name is not None
            lower_name = doc.file_name.lower()
            printable_path = file_path

            if lower_name.endswith((".doc", ".docx", ".xls", ".xlsx")):
                await update.message.reply_text("📄 Converting to PDF...")
                printable_path = convert_to_pdf(file_path)

        elif update.message.photo:
            photo = update.message.photo[-1]  # highest resolution
            file = await context.bot.get_file(photo.file_id)
            file_path = f"/tmp/photo_{photo.file_id}.jpg"
            printable_path = file_path
            await file.download_to_drive(file_path)

        else:
            await update.message.reply_text("Unsupported file type.")
            return

        printer_name = context.bot_data.get("printer_name")
        print_file(printable_path, printer_name)
        await update.message.reply_text("✅ File sent to printer.")

    # Replace with a custom exception
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to process/print: {e}")
    finally:
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
            if (
                printable_path
                and printable_path != file_path
                and os.path.exists(printable_path)
            ):
                os.remove(printable_path)
        except Exception:
            pass


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass


def build_app(settings: Settings) -> Application:
    app = Application.builder().token(settings.tg_token).build()

    app.bot_data["allowed_users"] = settings.allowed_users
    app.bot_data["printer_name"] = settings.printer_name

    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))
    app.add_handler(CommandHandler("status", status))

    return app
