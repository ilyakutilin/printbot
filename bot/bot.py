import os

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bot.exceptions import UnprintableTypeError
from bot.helpers import is_allowed, prepare_for_printing, print_file
from bot.messages import MESSAGES as msgs
from bot.settings import Settings


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert update.effective_user is not None
    assert update.message is not None

    user_id = update.effective_user.id
    allowed_users = context.bot_data.get("allowed_users")
    if not is_allowed(user_id, allowed_users):
        await update.message.reply_text(msgs["no_auth"])
        return

    file_path = None
    printable_path = None

    if update.message.document:
        doc = update.message.document
        file = await context.bot.get_file(doc.file_id)
        file_path = f"/tmp/{doc.file_name}"
        await file.download_to_drive(file_path)

        assert doc.file_name is not None
        printable_path = file_path

        try:
            printable_path = prepare_for_printing(file_path)
        except UnprintableTypeError:
            await update.message.reply_text(msgs["unprintable"])
        except FileNotFoundError as e:
            await update.message.reply_text(msgs["failed"].format(err=e))

    elif update.message.photo:
        photo = update.message.photo[-1]  # highest resolution
        file = await context.bot.get_file(photo.file_id)
        file_path = f"/tmp/photo_{photo.file_id}.jpg"
        printable_path = file_path
        await file.download_to_drive(file_path)

    else:
        await update.message.reply_text(msgs["unsupported"])
        return

    printer_name = context.bot_data.get("printer_name")
    print_file(printable_path, printer_name)
    await update.message.reply_text(msgs["sent_to_printer"])

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
