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
from bot.helpers import get_printing_queue, prepare_for_printing, print_file, sizeof_fmt
from bot.logger import configure_logging
from bot.messages import MESSAGES as msgs
from bot.settings import Settings

logger = configure_logging(__name__)


class PrintJob:
    def __init__(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.update = update
        self.context = context
        self.input_path: str | None = None
        self.printable_path: str | None = None
        self.file_name: str | None = None
        self.page_count: int | None = None
        self.main_keyboard: ReplyKeyboardMarkup = ReplyKeyboardMarkup(
            [["/start", "/status"]], resize_keyboard=True, one_time_keyboard=False
        )

    async def is_user_valid(self) -> bool:
        assert self.update.effective_user is not None
        assert self.update.message is not None

        user = self.update.effective_user
        user_id = user.id
        allowed_users = self.context.bot_data.get("allowed_users")

        if not allowed_users:
            logger.info(
                "There is no restriction on the users, so anyone can access "
                f"the service. Current user: {user.username} ({user.full_name}, "
                f"ID {user_id})"
            )
            return True

        if not isinstance(allowed_users, abc.Iterable):
            logger.error(
                f"Allowed users is not an iterable, it's {type(allowed_users)}: "
                f"{str(allowed_users)}. There is something wrong with the design "
                f"of the app. The current user: {user.username} ({user.full_name}, "
                f"ID {user_id}) will be denied access for security reasons."
            )
            await self.update.message.reply_text(msgs["no_auth"])
            return False

        if user_id not in allowed_users:
            logger.warning(
                f"Attempt to access the bot by an unathorized user: ID: {user.id}, "
                f"Name: {user.full_name}, Username: {user.username}"
            )
            await self.update.message.reply_text(msgs["no_auth"])
            return False

        logger.info(
            f"User {user.username} ({user.full_name}, ID {user.id}) is authorized"
        )
        return True

    async def process_doc(self) -> None:
        assert self.update.message is not None
        doc = self.update.message.document
        assert doc is not None
        assert doc.file_name is not None
        self.file_name = doc.file_name

        logger.info(
            f"Event: File {self.file_name} has been sent for printing as an attachment"
        )
        logger.info(
            f"Getting basic info about the file {self.file_name} with ID {doc.file_id},"
            f" size {sizeof_fmt(doc.file_size)}, MIME type {doc.mime_type} "
            "and preparing it for downloading"
        )
        file = await self.context.bot.get_file(doc.file_id)
        self.input_path = f"/tmp/{self.file_name}"
        logger.info(f"Downloading {self.file_name} to {self.input_path}")
        await self.update.message.reply_text(
            msgs["downloading_file"].format(filename=self.file_name),
            reply_markup=self.main_keyboard,
        )
        await file.download_to_drive(self.input_path)
        logger.info(f"File {self.file_name} has been successfully downloaded")

        try:
            logger.info(f"Preparing file {self.file_name} for printing")
            await self.update.message.reply_text(
                msgs["preparing_file"], reply_markup=self.main_keyboard
            )
            self.printable_path, self.page_count = prepare_for_printing(self.input_path)

        except UnprintableTypeError as e:
            logger.error(f"Printing failed: {e}")
            await self.update.message.reply_text(
                msgs["unprintable"], reply_markup=self.main_keyboard
            )
            return
        except FileNotFoundError as e:
            logger.error(
                f"!!! File {self.file_name} has not been found by path "
                f"{self.input_path}: {e}. This should not have happened and "
                "it indicates that there is something wrong with the app design !!!"
            )
            await self.update.message.reply_text(
                msgs["failed"].format(err=e), reply_markup=self.main_keyboard
            )
            return

    async def request_print_confirmation(self) -> None:
        assert self.update.message is not None
        # TODO: Make the max amount of pages a setting instead of hard coding
        logger.debug(
            "There are more than 20 pages in the document to be printed, "
            "send a confirmation message to the user"
        )
        # TODO: Add the actual inline buttons for Yes and No, and the callback
        await self.update.message.reply_text(
            msgs["page_count_warning"].format(
                filename=self.file_name, pages=self.page_count
            ),
            reply_markup=self.main_keyboard,
        )

    async def process_photo(self) -> None:
        assert self.update.message is not None
        photo = self.update.message.photo[-1]  # highest resolution
        logger.info("Event: A photo has been sent for printing")
        logger.info(
            f"Getting basic info about the photo with ID {photo.file_id}, size "
            f"{sizeof_fmt(photo.file_size)}, resolution {photo.width} x {photo.height},"
            " and preparing it for downloading"
        )
        file = await self.context.bot.get_file(photo.file_id)
        self.file_name = f"{photo.file_id}.jpg"
        self.input_path = f"/tmp/photo_{self.file_name}"
        logger.info(f"Downloading the photo to {self.input_path}")
        self.printable_path = self.input_path
        self.page_count = 1
        await file.download_to_drive(self.input_path)
        logger.info("Photo has been successfully downloaded")

    async def send_to_printer(self) -> None:
        assert self.update.message is not None
        printer_name = self.context.bot_data.get("printer_name")
        if printer_name:
            logger.info(f"File {self.file_name} will be sent to printer {printer_name}")
        else:
            logger.info(f"File {self.file_name} will be sent to the default printer")

        try:
            logger.info(f"Attempting to print file {self.file_name}")
            assert self.printable_path is not None
            print_file(self.printable_path, printer_name)
        except PrintingError as e:
            logger.error(f"Printing file {self.file_name} failed: {e}")
            await self.update.message.reply_text(
                msgs["printing_failed"], reply_markup=self.main_keyboard
            )
        else:
            logger.info(
                f"File {self.file_name} has successfully been sent to printer, "
                "and the printer did not report any errors"
            )
            await self.update.message.reply_text(
                msgs["sent_to_printer"], reply_markup=self.main_keyboard
            )

    async def cleanup(self) -> None:
        logger.info("Cleaning up")
        try:
            removed = False
            if self.input_path and os.path.exists(self.input_path):
                logger.debug(f"Removing {self.input_path}")
                os.remove(self.input_path)
                removed = True
            if (
                self.printable_path
                and self.printable_path != self.input_path
                and os.path.exists(self.printable_path)
            ):
                logger.debug(f"Removing {self.printable_path}")
                os.remove(self.printable_path)
                removed = True
            if not removed:
                logger.debug("Nothing to remove / clean up")
        except Exception as e:
            logger.warning(f"Cleaning up failed: {e}")
            pass
        else:
            logger.info("Cleaning up completed")

    async def start(self) -> None:
        logger.info("Event: /start command issued")

        assert self.update.message is not None
        await self.update.message.reply_text(
            msgs["start"], reply_markup=self.main_keyboard
        )
        logger.info("A start message has been sent to the user")

    async def get_status(self) -> None:
        logger.info("Event: /status command issued")
        assert self.update.message is not None
        try:
            logger.info("Getting the printing queue")
            queue = get_printing_queue()
            if queue:
                logger.info("Queue received, message sent to user")
                logger.debug(f"Queue: {queue}")
                await self.update.message.reply_text(
                    msgs["print_queue"].format(queue=queue),
                    reply_markup=self.main_keyboard,
                )
            else:
                logger.info("Queue received and is empty, message sent to user")
                await self.update.message.reply_text(
                    msgs["empty_queue"], reply_markup=self.main_keyboard
                )
        except PrinterStatusRetrievalError as e:
            logger.error(f"Error getting the printer queue: {e}")
            await self.update.message.reply_text(
                msgs["status_failed"], reply_markup=self.main_keyboard
            )


async def handle_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    job = PrintJob(update, context)

    if not await job.is_user_valid():
        return

    await job.process_doc()
    # TODO: Make the max amount of pages a setting instead of hard coding
    if job.page_count and job.page_count >= 20:
        await job.request_print_confirmation()
        return
    await job.send_to_printer()
    await job.cleanup()


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    job = PrintJob(update, context)

    if not await job.is_user_valid():
        return

    await job.process_photo()
    await job.send_to_printer()
    await job.cleanup()


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    job = PrintJob(update, context)

    if not await job.is_user_valid():
        return

    await job.get_status()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    job = PrintJob(update, context)

    if not await job.is_user_valid():
        return

    await job.start()


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

    app.add_handler(MessageHandler(filters.Document.ALL, handle_doc))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))

    return app
