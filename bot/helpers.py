import os
import shutil
import subprocess

import filetype
from filetype.types.archive import Pdf
from filetype.types.image import Bmp, Gif, Ico, Jpeg, Png, Tiff

from bot.exceptions import (
    CommandError,
    FileConversionError,
    PrinterStatusRetrievalError,
    PrintingError,
    UnprintableTypeError,
)
from bot.logger import configure_logging

logger = configure_logging(__name__)


def sizeof_fmt(num: float | None, suffix: str = "B") -> str:
    if not num:
        return "0 B"

    for unit in ("", "K", "M", "G", "T", "P", "E", "Z"):
        if abs(num) < 1024.0:
            if num.is_integer():
                return f"{int(num)} {unit}{suffix}"
            else:
                return f"{num:.1f} {unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f} Y{suffix}"


def run_cmd(command: list[str]) -> subprocess.CompletedProcess:
    """Runs a Linux command and returns the result.

    Args:
        command (list[str]): A command to run in the form of a list of strings.

    Raises:
        CommandError: Raised in case of errors while executing a command.

    Returns:
        subprocess.CompletedProcess: The return value from run(), representing a process
            that has finished.
    """
    try:
        res = subprocess.run(command, capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError) as e:
        raise CommandError(e)
    return res


def _convert_to_pdf(input_path: str) -> str:
    """Converts a document to PDF using LibreOffice.

    Args:
        input_path (str): A path to the file to be converted.

    Raises:
        FileConversionError: Raised if file conversion fails.

    Returns:
        str: A path to the converted PDF file.
    """
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise FileConversionError(
            "LibreOffice (soffice) is not installed or not in PATH"
        )

    output_dir = os.path.dirname(input_path)
    cmd = [
        soffice,
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        output_dir,
        input_path,
    ]

    try:
        run_cmd(cmd)
    except CommandError as e:
        raise FileConversionError(
            f"Failure while running the conversion command {' '.join(cmd)}: {e}"
        )

    pdf_path = os.path.splitext(input_path)[0] + ".pdf"

    if not os.path.isfile(pdf_path):
        raise FileConversionError("Conversion did not produce a PDF file")

    return pdf_path


def prepare_for_printing(file_path: str) -> str:
    """Prepares the file for printing.

    Args:
        file_path (str): Path to the file to be prepared.

    Raises:
        FileNotFoundError: Raised if the file is not found by the specified path.
        UnprintableTypeError: Raised if the file of an unsupported type.

    Returns:
        str: A path to the file ready for printing.
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    file_name = os.path.basename(file_path)
    file_type: filetype.Type | None = filetype.guess(file_path)
    if isinstance(file_type, (Pdf, Bmp, Gif, Ico, Jpeg, Png, Tiff)):
        assert file_type is not None
        logger.debug(
            f"File {file_name} is of type ({file_type.mime}), so it can be printed "
            "as is"
        )
        return file_path

    if filetype.is_document(file_path):
        assert file_type is not None
        logger.debug(
            f"File {file_name} is an office document ({file_type.extension}), "
            "so it needs to be converted to PDF before printing"
        )
        try:
            logger.debug(f"Converting file {file_name} to PDF using LibreOffice")
            pdf_path = _convert_to_pdf(file_path)
            logger.debug(
                f"File {file_name} has successfully been converted to PDF "
                f"and is accessible by path {pdf_path}"
            )
            return pdf_path
        except FileConversionError as e:
            logger.debug(f"Conversion of the file {file_name} to PDF failed")
            raise UnprintableTypeError(
                f"File {file_path} could not be converted to PDF: {e}"
            )

    file_type_str = f": {file_type.extension}" if file_type else ""
    raise UnprintableTypeError(
        f"File {file_path} is of an unsupported type{file_type_str}"
    )


def print_file(file_path: str, printer_name: str | None) -> None:
    """Send file to printer using lp.

    Args:
        file_path (str): Path to a file to be printed.
        printer_name (str | None): Printer name that the file will be sent to. Optional.

    Raises:
        PrintingError: Raised in case the command exits with a code other than 0.
    """
    if printer_name:
        cmd = ["lp", "-d", printer_name, file_path]
        logger.debug(
            f"Printer name is supplied ({printer_name}), so the printing command "
            f"looks like this: {' '.join(cmd)}"
        )
    else:
        cmd = ["lp", file_path]
        logger.debug(
            f"Printer name is not supplied, so the printing will be done "
            f"on the default printer, and the command looks like this: {' '.join(cmd)}"
        )

    try:
        logger.debug("Executing the printing command")
        run_cmd(cmd)
    except CommandError as e:
        logger.debug("Printing command failed")
        raise PrintingError(
            f"Failure while running the conversion command {' '.join(cmd)}: {e}"
        )


def get_printing_queue():
    try:
        queue = run_cmd(["lpstat", "-o"])
        queue = queue.stdout
        return queue
    except CommandError as e:
        raise PrinterStatusRetrievalError(
            f"Failure while retrieving the printer status: {e}"
        )
