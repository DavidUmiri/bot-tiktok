from typing import Optional, Union
from pathlib import Path
from contextlib import contextmanager
import os
import re
import logging
import requests
import tempfile
import yt_dlp
import asyncio

from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from telegram import Update, InputMediaPhoto
from telegram.ext import ContextTypes

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException, WebDriverException

# Cargar variables de entorno
load_dotenv()

# Configuración del bot
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN no está configurado en las variables de entorno")

# Usar directorio temporal en lugar de local
DOWNLOADS_DIR = Path(tempfile.gettempdir()) / "tiktok_downloads"
TIKTOK_URL_PATTERN = r'https?://(?:www\.)?(?:vm\.)?tiktok\.com/'

# Configuración de logs
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
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
    """Determina el tipo de contenido basado en la URL final."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, allow_redirects=True)
        response.raise_for_status()
        final_url = response.url

        if "/music/" in final_url:
            return "audio"
        elif "/video/" in final_url:
            return "video"
        elif any(keyword in final_url for keyword in ["/photo/", "/share/"]):
            return "fotos"
    except requests.RequestException as e:
        logger.exception("Error al obtener tipo de contenido:", exc_info=e)
    return "desconocido"

async def descargar_video(update: Update, url: str):
    """Descarga y envía un video usando yt-dlp."""
    await update.message.reply_text("Descargando video...")
    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio/best[ext=mp4]/best',
        'outtmpl': str(DOWNLOADS_DIR / '%(id)s.%(ext)s'),
        'quiet': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)
            with cleanup_file(file_path):
                with open(file_path, 'rb') as file:
                    if file_path.endswith(('.mp4', '.webm')):
                        await update.message.reply_video(video=file, caption='Aquí tienes tu video.')
                    else:
                        await update.message.reply_audio(audio=file, caption='Aquí tienes tu audio.')
    except Exception as e:
        logger.exception("Error en descargar_video:", exc_info=e)
        await update.message.reply_text("Ocurrió un error al descargar el video.")

async def descargar_fotos(update: Update, url: str):
    """Extrae y envía fotos de una publicación de TikTok usando Selenium."""
    await update.message.reply_text("Descargando imágenes...")
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.binary_location = os.getenv("GOOGLE_CHROME_BIN", "/usr/bin/google-chrome")
    
    try:
        driver = webdriver.Chrome(
            service=Service(os.getenv("CHROMEDRIVER_PATH", "/usr/local/bin/chromedriver")),
            options=options
        )
        driver.get(url)
        driver.implicitly_wait(10)
        images = driver.find_elements(By.CSS_SELECTOR, 'img')
        image_urls = [img.get_attribute('src') for img in images if img.get_attribute('src')]
        driver.quit()

        if image_urls:
            media_group = [InputMediaPhoto(media=url) for url in image_urls[:10]]
            await update.message.reply_media_group(media=media_group)
        else:
            await update.message.reply_text("No se encontraron imágenes en este TikTok.")
    except WebDriverException as e:
        logger.exception("Error en descargar_fotos:", exc_info=e)
        await update.message.reply_text("Error al extraer imágenes.")

async def procesar_tiktok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa el mensaje del usuario y ejecuta la acción según el tipo de contenido."""
    url = update.message.text.strip()
    if not re.match(TIKTOK_URL_PATTERN, url):
        await update.message.reply_text('Envía un enlace válido de TikTok.')
        return

    tipo = await get_tipo_contenido(url)
    if tipo == "video":
        await descargar_video(update, url)
    elif tipo == "fotos":
        await descargar_fotos(update, url)
    else:
        await update.message.reply_text('No puedo manejar este enlace.')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('¡Hola! Envíame un enlace de TikTok y te descargaré el contenido.')

def main():
    """Inicia el bot."""
    DOWNLOADS_DIR.mkdir(exist_ok=True)
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, procesar_tiktok))
    
    # Usar PORT de Railway si está disponible
    port = int(os.getenv("PORT", 8443))
    
    # Si estamos en Railway (PORT está definido), usar webhooks
    if "PORT" in os.environ:
        application.run_webhook(
            listen="0.0.0.0",
            port=port,
            webhook_url=os.getenv("WEBHOOK_URL"),
            cert=None,
            key=None
        )
    else:
        # En desarrollo local usar polling
        application.run_polling(poll_interval=1.0, timeout=30)

if __name__ == '__main__':
    main()
