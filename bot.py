from typing import Optional, Union
from pathlib import Path
from contextlib import contextmanager
import os
import re
import logging
import requests
import yt_dlp
import uuid

from telegram.ext import Application, CommandHandler, MessageHandler, filters
from telegram import Update, InputMediaPhoto
from telegram.ext import ContextTypes

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

# Configuración del bot
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN no está configurado en las variables de entorno")

DOWNLOADS_DIR = Path("downloads")
TIKTOK_URL_PATTERN = r"https?://(?:www\.)?(?:vm\.)?tiktok\.com/"

# Configuración de timeouts y opciones del navegador
BROWSER_TIMEOUT = 15  # segundos
REQUEST_TIMEOUT = 10  # segundos
BROWSER_OPTIONS = {
    "--headless": None,
    "--disable-gpu": None,
    "--no-sandbox": None,
    "--disable-dev-shm-usage": None,
    "--disable-extensions": None,
    "--disable-logging": None,
    "--disable-notifications": None,
    "--disable-default-apps": None,
    "--disable-popup-blocking": None,
    "--use-gl=swiftshader": None,
    "--disable-software-rasterizer": None,
    "--ignore-gpu-blocklist": None,
    "--enable-webgl": None,
    "--memory-pressure-off": None,
    "--js-flags=--max-old-space-size=2048": None,
}

# Configuración de logs
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


@contextmanager
def cleanup_file(file_path: Union[str, Path]):
    try:
        yield
    finally:
        try:
            os.remove(file_path)
        except OSError:
            logger.warning(f"No se pudo eliminar el archivo: {file_path}")

# Add instance management
BOT_INSTANCE_LOCK_FILE = Path("bot.lock")

def check_instance():
    """Check if another instance is running and manage the lock file."""
    try:
        if BOT_INSTANCE_LOCK_FILE.exists():
            # Check if the process is actually running
            try:
                with open(BOT_INSTANCE_LOCK_FILE, 'r') as f:
                    pid = int(f.read().strip())
                os.kill(pid, 0)  # Check if process exists
                return False  # Process is running
            except (OSError, ValueError):
                # Process not running, clean up stale lock
                BOT_INSTANCE_LOCK_FILE.unlink(missing_ok=True)
        
        # Create new lock file
        with open(BOT_INSTANCE_LOCK_FILE, 'w') as f:
            f.write(str(os.getpid()))
        return True
    except Exception as e:
        logger.error(f"Error checking instance: {e}")
        return False

def cleanup_instance():
    """Remove the lock file when the bot stops."""
    try:
        BOT_INSTANCE_LOCK_FILE.unlink(missing_ok=True)
    except Exception as e:
        logger.error(f"Error cleaning up instance: {e}")

async def get_tipo_contenido(url: str) -> str:
    """Determina el tipo de contenido basándose en la URL final."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(
            url, headers=headers, allow_redirects=True, timeout=REQUEST_TIMEOUT
        )
        final_url = response.url

        if re.search(r"/music/", final_url):
            return "audio"
        if re.search(r"/video/", final_url):
            return "video"
        if re.search(r"/photo/|/share/", final_url):
            return "fotos"
        return "desconocido"
    except requests.Timeout:
        logger.error(f"Timeout al obtener el tipo de contenido para: {url}")
        raise TimeoutError("La solicitud ha tardado demasiado tiempo")


async def descargar_video(update: Update, url: str):
    """Descarga y envía un video (con audio) usando yt-dlp."""
    await update.message.reply_text("Descargando video...")
    ydl_opts = {
        "format": "bestaudio[ext=m4a]/bestaudio/best[ext=mp4]/best",
        "outtmpl": str(DOWNLOADS_DIR / "%(id)s.%(ext)s"),
        "quiet": True,
        "socket_timeout": REQUEST_TIMEOUT,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)
            if file_path.endswith((".mp4", ".webm", ".m4a")):
                with cleanup_file(file_path):
                    if file_path.endswith((".mp4", ".webm")):
                        await update.message.reply_video(
                            video=open(file_path, "rb"), caption="Aquí tienes tu video."
                        )
                    else:
                        await update.message.reply_audio(
                            audio=open(file_path, "rb"), caption="Aquí tienes tu audio."
                        )
    except Exception as e:
        logger.error(f"Error al descargar video: {e}")
        await update.message.reply_text(
            "Error al descargar el video. Por favor, inténtalo de nuevo."
        )


async def descargar_audio(update: Update, url: str):
    """Extrae el enlace de audio usando Selenium y lo descarga."""
    await update.message.reply_text("Descargando audio...")
    options = Options()
    for option, value in BROWSER_OPTIONS.items():
        options.add_argument(option)

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=options
    )
    driver.set_page_load_timeout(BROWSER_TIMEOUT)

    try:
        driver.get(url)
        driver.implicitly_wait(BROWSER_TIMEOUT)
        container = driver.find_element(By.ID, "mse")
        video = container.find_element(By.TAG_NAME, "video")
        audio_url = video.get_attribute("src")

        if not audio_url:
            raise ValueError("No se encontró la URL del audio")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        }
        response = requests.get(audio_url, headers=headers, timeout=REQUEST_TIMEOUT)

        if response.status_code == 200:
            unique_filename = f"audio_{uuid.uuid4().hex[:8]}.m4a"
            file_path = DOWNLOADS_DIR / unique_filename
            with open(file_path, "wb") as f:
                f.write(response.content)
            await update.message.reply_audio(
                audio=open(file_path, "rb"), caption="Aquí tienes tu audio."
            )
            os.remove(file_path)
        else:
            raise ValueError(f"Error al descargar audio: {response.status_code}")

    except Exception as e:
        logger.error(f"Error en descargar_audio: {e}")
        await update.message.reply_text(
            "Error al procesar el audio. Por favor, inténtalo de nuevo."
        )
    finally:
        driver.quit()


async def descargar_fotos(update: Update, url: str):
    """Extrae y envía fotos de una publicación de TikTok usando Selenium."""
    await update.message.reply_text("Descargando imágenes...")
    options = Options()
    for option, value in BROWSER_OPTIONS.items():
        options.add_argument(option)
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=options
    )
    driver.set_page_load_timeout(BROWSER_TIMEOUT)

    try:
        driver.get(url)
        driver.implicitly_wait(BROWSER_TIMEOUT)
        
        # Try multiple selectors for images
        image_selectors = [
            "img.swiper-image",
            "img.tiktok-image",
            "div[class*='image-container'] img",
            "div[class*='slide-container'] img"
        ]
        
        images = []
        for selector in image_selectors:
            try:
                found_images = driver.find_elements(By.CSS_SELECTOR, selector)
                if found_images:
                    images = found_images
                    logger.info(f"Found images using selector: {selector}")
                    break
            except Exception as e:
                logger.debug(f"Selector {selector} failed: {e}")
                continue

        if not images:
            raise ValueError("No se encontraron imágenes")

        media_group = []
        for i, img in enumerate(images):
            try:
                img_url = img.get_attribute("src")
                if not img_url:
                    continue

                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
                    "Referer": url
                }
                response = requests.get(img_url, headers=headers, timeout=REQUEST_TIMEOUT)

                if response.status_code == 200:
                    unique_filename = f"image_{uuid.uuid4().hex[:8]}.jpg"
                    file_path = DOWNLOADS_DIR / unique_filename
                    with open(file_path, "wb") as f:
                        f.write(response.content)

                    media_group.append(
                        InputMediaPhoto(
                            media=open(file_path, "rb"),
                            caption="Aquí tienes tu imagen." if i == 0 else "",
                        )
                    )
            except Exception as e:
                logger.warning(f"Error processing image {i}: {e}")
                continue

        if media_group:
            await update.message.reply_media_group(media=media_group)
            for media in media_group:
                media.media.close()
                os.remove(media.media.name)
        else:
            raise ValueError("No se pudieron descargar las imágenes")

    except Exception as e:
        logger.error(f"Error en descargar_fotos: {e}")
        await update.message.reply_text(
            "Error al procesar las imágenes. Por favor, inténtalo de nuevo."
        )
    finally:
        driver.quit()


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja los enlaces de TikTok recibidos."""
    try:
        url = update.message.text
        if not re.search(TIKTOK_URL_PATTERN, url):
            await update.message.reply_text(
                "Por favor, envía un enlace válido de TikTok."
            )
            return

        tipo_contenido = await get_tipo_contenido(url)

        if tipo_contenido == "video":
            await descargar_video(update, url)
        elif tipo_contenido == "audio":
            await descargar_audio(update, url)
        elif tipo_contenido == "fotos":
            await descargar_fotos(update, url)
        else:
            await update.message.reply_text(
                "No se pudo determinar el tipo de contenido. Por favor, verifica el enlace."
            )

    except TimeoutError:
        await update.message.reply_text(
            "La solicitud ha tardado demasiado tiempo. Por favor, inténtalo de nuevo."
        )
    except Exception as e:
        logger.error(f"Error en handle_url: {e}")
        await update.message.reply_text(
            "Ha ocurrido un error. Por favor, inténtalo de nuevo más tarde."
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el comando /start."""
    await update.message.reply_text(
        "¡Hola! Envíame un enlace de TikTok y te ayudaré a descargar su contenido."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el comando /help."""
    await update.message.reply_text(
        "Para usar este bot, simplemente envía un enlace de TikTok y automáticamente "
        "detectaré si es un video, audio o imagen para descargarlo por ti."
    )


def main():
    """Función principal del bot."""
    if not check_instance():
        logger.error("Another instance is already running")
        return

    try:
        # Crear el directorio de descargas si no existe
        DOWNLOADS_DIR.mkdir(exist_ok=True)

        # Inicializar el bot
        application = Application.builder().token(TOKEN).build()

        # Agregar manejadores
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))

        # Iniciar el bot
        application.run_polling()

    except Exception as e:
        logger.error(f"Error en main: {e}")
    finally:
        cleanup_instance()


if __name__ == "__main__":
    main()
