import os
import shutil
import subprocess

from bot.exceptions import CommandError, FileConversionError


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


def convert_to_pdf(input_path: str) -> str:
    """Converts a document to PDF using LibreOffice.

    Args:
        input_path (str): A path to the file to be converted.

    Raises:
        FileNotFoundError: Raised if the file was not found by the specified path.
        FileConversionError: Raised if file conversion fails.

    Returns:
        str: A path to the converted PDF file.
    """
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"File not found: {input_path}")

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


def print_file(file_path: str, printer_name: str | None) -> None:
    """Send file to printer using lp."""
    pass


def is_allowed(user_id: int, allowed_users: tuple[int] | None) -> bool:
    pass
