import os
import sys
import json
import random
import logging
import zipfile
import shutil
import stat
import requests

from termcolor import colored

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _normalize_path(path: str) -> str:
    return os.path.abspath(os.path.expanduser(os.path.expandvars(path)))


def resolve_imagemagick_binary() -> str | None:
    """
    Resolve a valid ImageMagick binary path for the current OS.

    Returns:
        str | None: Absolute path to a usable ImageMagick binary, if found.
    """
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    candidates: list[str] = []
    env_value = os.getenv("IMAGEMAGICK_BINARY")
    if env_value:
        candidates.append(env_value)
        if not os.path.isabs(env_value):
            candidates.append(os.path.join(repo_root, env_value))
    local_candidates = [
        os.path.join(repo_root, "magick"),
        os.path.join(repo_root, "magick.AppImage"),
    ]
    if os.name == "nt":
        local_candidates.append(os.path.join(repo_root, "magick.exe"))

    for path in local_candidates:
        if path not in candidates:
            candidates.append(path)

    path_binary = shutil.which("magick")
    if path_binary:
        candidates.append(path_binary)
    if os.name == "nt":
        path_binary = shutil.which("magick.exe")
        if path_binary:
            candidates.append(path_binary)

    for candidate in candidates:
        if not candidate:
            continue
        normalized = _normalize_path(candidate)
        if os.name != "nt" and normalized.lower().endswith(".exe"):
            continue
        if os.path.isfile(normalized):
            if os.name != "nt" and not os.access(normalized, os.X_OK):
                try:
                    st = os.stat(normalized)
                    os.chmod(normalized, st.st_mode | stat.S_IXUSR)
                except Exception:
                    logger.warning(
                        colored(
                            f"ImageMagick binary is not executable: {normalized}",
                            "yellow",
                        )
                    )
            if os.name == "nt" or os.access(normalized, os.X_OK):
                os.environ["IMAGEMAGICK_BINARY"] = normalized
                logger.info(
                    colored(f"Using ImageMagick binary: {normalized}", "green")
                )
                return normalized

    return None


def clean_dir(path: str) -> None:
    """
    Removes every file in a directory.

    Args:
        path (str): Path to directory.

    Returns:
        None
    """
    try:
        if not os.path.exists(path):
            os.mkdir(path)
            logger.info(f"Created directory: {path}")

        for file in os.listdir(path):
            file_path = os.path.join(path, file)
            os.remove(file_path)
            logger.info(f"Removed file: {file_path}")

        logger.info(colored(f"Cleaned {path} directory", "green"))
    except Exception as e:
        logger.error(f"Error occurred while cleaning directory {path}: {str(e)}")

def fetch_songs(zip_url: str) -> None:
    """
    Downloads songs into songs/ directory to use with geneated videos.

    Args:
        zip_url (str): The URL to the zip file containing the songs.

    Returns:
        None
    """
    try:
        logger.info(colored(f" => Fetching songs...", "magenta"))

        files_dir = "../Songs"
        if not os.path.exists(files_dir):
            os.mkdir(files_dir)
            logger.info(colored(f"Created directory: {files_dir}", "green"))
        else:
            # Skip if songs are already downloaded
            return

        # Download songs
        response = requests.get(zip_url)

        # Save the zip file
        with open("../Songs/songs.zip", "wb") as file:
            file.write(response.content)

        # Unzip the file
        with zipfile.ZipFile("../Songs/songs.zip", "r") as file:
            file.extractall("../Songs")

        # Remove the zip file
        os.remove("../Songs/songs.zip")

        logger.info(colored(" => Downloaded Songs to ../Songs.", "green"))

    except Exception as e:
        logger.error(colored(f"Error occurred while fetching songs: {str(e)}", "red"))

def choose_random_song() -> str:
    """
    Chooses a random song from the songs/ directory.

    Returns:
        str: The path to the chosen song.
    """
    try:
        songs = os.listdir("../Songs")
        song = random.choice(songs)
        logger.info(colored(f"Chose song: {song}", "green"))
        return f"../Songs/{song}"
    except Exception as e:
        logger.error(colored(f"Error occurred while choosing random song: {str(e)}", "red"))


def check_env_vars() -> None:
    """
    Checks if the necessary environment variables are set.

    Returns:
        None

    Raises:
        SystemExit: If any required environment variables are missing.
    """
    try:
        required_vars = ["PEXELS_API_KEY", "TIKTOK_SESSION_ID"]
        missing_vars = [
            var for var in required_vars if os.getenv(var) is None or len(os.getenv(var)) == 0
        ]

        imagemagick_binary = resolve_imagemagick_binary()
        if not imagemagick_binary:
            missing_vars.append("IMAGEMAGICK_BINARY")

        if missing_vars:
            missing_vars_str = ", ".join(missing_vars)
            logger.error(colored(f"The following environment variables are missing: {missing_vars_str}", "red"))
            if "IMAGEMAGICK_BINARY" in missing_vars:
                logger.error(
                    colored(
                        "On Linux, set IMAGEMAGICK_BINARY to the AppImage path (for example: ./magick) and ensure it is executable (chmod +x magick).",
                        "yellow",
                    )
                )
            logger.error(colored("Please consult 'EnvironmentVariables.md' for instructions on how to set them.", "yellow"))
            sys.exit(1)  # Aborts the program
    except Exception as e:
        logger.error(f"Error occurred while checking environment variables: {str(e)}")
        sys.exit(1)  # Aborts the program if an unexpected error occurs
