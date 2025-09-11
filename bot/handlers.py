import os
from collections import abc

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bot.exceptions import (
    PrinterStatusRetrievalError,
    PrintingError,
    UnprintableTypeError,
)
from bot.helpers import get_printing_queue, prepare_for_printing, print_file
from bot.logger import configure_logging
from bot.messages import MESSAGES as msgs
from bot.settings import Settings

logger = configure_logging(__name__)

main_keyboard = ReplyKeyboardMarkup(
    [["/start", "/status"]], resize_keyboard=True, one_time_keyboard=False
)


async def _is_user_valid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert update.effective_user is not None
    assert update.message is not None

    user = update.effective_user
    user_id = user.id
    allowed_users = context.bot_data.get("allowed_users")

    if not allowed_users:
        logger.info(
            f"There is no restriction on the users, so anyone can access the service. "
            f"Current user: {user.username} ({user.full_name}, ID {user_id})"
        )
        return True

    if not isinstance(allowed_users, abc.Iterable):
        logger.error(
            f"Allowed users is not an iterable, it's {type(allowed_users)}: "
            f"{str(allowed_users)}. There is something wrong with the design "
            f"of the app. The current user: {user.username} ({user.full_name}, "
            f"ID {user_id}) will be denied access for security reasons."
        )
        await update.message.reply_text(msgs["no_auth"])
        return False

    if user_id not in allowed_users:
        logger.warning(
            f"Attempt to access the bot by an unathorized user: ID: {user.id}, Name: "
            f"{user.full_name}, Username: {user.username}"
        )
        await update.message.reply_text(msgs["no_auth"])
        return False

    logger.info(f"User {user.username} ({user.full_name}, ID {user.id}) is authorized")
    return True


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Event: object sent for printing")
    user_is_valid = await _is_user_valid(update, context)
    if not user_is_valid:
        return

    file_path = None
    printable_path = None
    assert update.message is not None

    if update.message.document:
        doc = update.message.document
        assert doc.file_name is not None
        logger.info(f"File {doc.file_name} has been sent as an attachment")
        logger.info(
            # TODO: Get human size
            f"Getting basic info about the file {doc.file_name}, size {doc.file_size}, "
            f"MIME type {doc.mime_type} and preparing it for downloading"
        )
        file = await context.bot.get_file(doc.file_id)
        file_path = f"/tmp/{doc.file_name}"
        logger.info(
            f"Downloading the file {doc.file_name} (file ID {file.file_id}) to "
            f"{file_path}"
        )
        await file.download_to_drive(file_path)
        logger.info(
            f"File {doc.file_name} with ID {file.file_id} has been successfully "
            f"downloaded to {file_path}"
        )

        printable_path = file_path

        try:
            logger.info(f"Preparing file {doc.file_name} for printing")
            printable_path = prepare_for_printing(file_path)
        except UnprintableTypeError as e:
            logger.error(f"File {doc.file_name} could not be printed: {e}")
            await update.message.reply_text(
                msgs["unprintable"], reply_markup=main_keyboard
            )
        except FileNotFoundError as e:
            logger.error(
                f"!!! File {doc.file_name} has not been found by path {file_path}: {e}."
                " This should not have happened and it indicates that there is "
                "something wrong with the app design !!!"
            )
            await update.message.reply_text(
                msgs["failed"].format(err=e), reply_markup=main_keyboard
            )

    elif update.message.photo:
        photo = update.message.photo[-1]  # highest resolution
        logger.info("An object sent to be printed is a photo")
        logger.info(
            # TODO: Get human size
            f"Getting basic info about the photo, size {photo.file_size}, "
            f"dimensions {photo.width} x {photo.height}, and preparing it "
            "for downloading"
        )
        file = await context.bot.get_file(photo.file_id)
        file_path = f"/tmp/photo_{photo.file_id}.jpg"
        logger.info(f"Downloading the photo file (ID {file.file_id}) to {file_path}")
        printable_path = file_path
        await file.download_to_drive(file_path)
        logger.info(
            f"Photo with ID {file.file_id} has been successfully downloaded to "
            f"{file_path}"
        )

    else:
        logger.warning(
            "An object sent to be printed is a not a photo and not a document, "
            "so it's unsupported."
        )
        await update.message.reply_text(msgs["unsupported"], reply_markup=main_keyboard)
        return

    file_name = os.path.basename(printable_path)
    printer_name = context.bot_data.get("printer_name")
    if printer_name:
        logger.info(f"File {file_name} will be sent to printer {printer_name}")
    else:
        logger.info(f"File {file_name} will be sent to the default printer")

    try:
        logger.info(f"Attempting to print file {file_name}")
        print_file(printable_path, printer_name)
    except PrintingError as e:
        logger.error(f"Printing file {file_name} failed: {e}")
        await update.message.reply_text(
            msgs["printing_failed"], reply_markup=main_keyboard
        )
    else:
        logger.info(
            f"File {file_name} has successfully been sent to printer, "
            "and the printer did not report any errors"
        )
        await update.message.reply_text(
            msgs["sent_to_printer"], reply_markup=main_keyboard
        )
    finally:
        logger.info("Cleaning up")
        try:
            if file_path and os.path.exists(file_path):
                logger.debug(f"Removing {file_path}")
                os.remove(file_path)
            if (
                printable_path
                and printable_path != file_path
                and os.path.exists(printable_path)
            ):
                logger.debug(f"Removing {printable_path}")
                os.remove(printable_path)
        except Exception as e:
            logger.warning(f"Cleaning up failed: {e}")
            pass


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Event: /status command issued")
    user_is_valid = await _is_user_valid(update, context)
    if not user_is_valid:
        return

    assert update.message is not None
    try:
        logger.info("Getting the printing queue")
        queue = get_printing_queue()
        if queue:
            logger.info("Queue received, message sent to user")
            logger.debug(f"Queue: {queue}")
            await update.message.reply_text(
                msgs["print_queue"].format(queue=queue), reply_markup=main_keyboard
            )
        else:
            logger.info("Queue received and is empty, message sent to user")
            await update.message.reply_text(
                msgs["empty_queue"], reply_markup=main_keyboard
            )
    except PrinterStatusRetrievalError as e:
        logger.error(f"Error getting the printer queue: {e}")
        await update.message.reply_text(
            msgs["status_failed"], reply_markup=main_keyboard
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Event: /start command issued")
    user_is_valid = await _is_user_valid(update, context)
    if not user_is_valid:
        return

    assert update.message is not None
    await update.message.reply_text(msgs["start"], reply_markup=main_keyboard)
    logger.info("A start message has been sent to the user")


def build_app(settings: Settings) -> Application:
    app = Application.builder().token(settings.tg_token).build()

    app.bot_data["allowed_users"] = settings.allowed_users
    logger.info(
        "Info on the allowed users has been added to bot_data and is now available "
        "to handlers via context with key 'allowed_users': "
        f"{app.bot_data['allowed_users']}"
    )
    app.bot_data["printer_name"] = (
        settings.printer_name if not settings.debug else settings.debug_printer_name
    )
    logger.info(
        "Printer name has been added to bot_data and is now available "
        "to handlers via context with key 'printer_name': "
        f"{app.bot_data['printer_name']}"
    )

    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))

    return app
