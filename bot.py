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
    "--headless": "new",  # Use new headless mode
    "--disable-gpu": None,
    "--no-sandbox": None,
    "--disable-dev-shm-usage": None,
    "--disable-setuid-sandbox": None,
    "--window-size=1920,1080": None,
    "--disable-extensions": None,
    "--proxy-server='direct://'" : None,
    "--proxy-bypass-list=*" : None,
    "--start-maximized" : None,
    "--disable-gpu" : None,
    "--disable-dev-shm-usage" : None,
    "--no-sandbox" : None,
    "--ignore-certificate-errors": None,
    "--allow-running-insecure-content": None,
    "--disable-web-security": None,
    "--disable-client-side-phishing-detection": None,
    "--disable-notifications": None,
    "--disable-default-apps": None,
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

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=options
    )
    driver.set_page_load_timeout(BROWSER_TIMEOUT)

    try:
        driver.get(url)
        # Wait for the page to load completely
        driver.implicitly_wait(BROWSER_TIMEOUT)
        # Wait for dynamic content to load
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        # Add a small delay to ensure all images are loaded
        import time
        time.sleep(2)
        
        # Get all image elements with a more specific selector
        images = driver.find_elements(By.CSS_SELECTOR, "img[src*='tiktokcdn']")
        
        # Collect image URLs with improved filtering
        image_urls = []
        for img in images:
            try:
                src = img.get_attribute("src")
                if src and not src.endswith((".gif", ".svg")):
                    # Get image dimensions
                    width = img.get_attribute("width")
                    height = img.get_attribute("height")
                    if width and height and int(width) >= 100 and int(height) >= 100:
                        image_urls.append(src)
            except Exception as e:
                logger.warning(f"Error processing image element: {e}")
                continue
        
        # Remove duplicates while preserving order
        image_urls = list(dict.fromkeys(image_urls))

        if image_urls:
            # Dividir las imágenes en grupos de 10 (límite de Telegram para media_group)
            for i in range(0, len(image_urls), 10):
                chunk = image_urls[i : i + 10]
                media_group = [InputMediaPhoto(media=url) for url in chunk]
                await update.message.reply_media_group(media=media_group)

            total_images = len(image_urls)
            await update.message.reply_text(
                f"Se han enviado {total_images} imágenes."
            )
        else:
            raise ValueError("No se encontraron imágenes válidas")

    except Exception as e:
        logger.error(f"Error en descargar_fotos: {e}")
        await update.message.reply_text(
            "Error al extraer imágenes. Por favor, inténtalo de nuevo."
        )
    finally:
        driver.quit()


async def procesar_tiktok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa el mensaje del usuario y ejecuta la acción según el tipo de contenido."""
    url = update.message.text.strip()
    if not re.match(TIKTOK_URL_PATTERN, url):
        await update.message.reply_text("Envía un enlace válido de TikTok.")
        return

    tipo = await get_tipo_contenido(url)
    if tipo == "video":
        await descargar_video(update, url)
    elif tipo == "fotos":
        await descargar_fotos(update, url)
    elif tipo == "audio":
        await descargar_audio(update, url)
    else:
        await update.message.reply_text("No puedo manejar este enlace.")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "¡Hola! Envíame un enlace de TikTok y te descargaré el contenido."
    )


def main():
    """Inicia el bot."""
    DOWNLOADS_DIR.mkdir(exist_ok=True)
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, procesar_tiktok)
    )
    application.run_polling(poll_interval=1.0, timeout=30)


if __name__ == "__main__":
    main()
