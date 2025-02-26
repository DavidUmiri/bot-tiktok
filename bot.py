from typing import Optional, Union
from pathlib import Path
from contextlib import contextmanager
import os
import re
import logging
import requests
import yt_dlp

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
    """
    Determina el tipo de contenido basándose en la URL final.
    Aquí, si la URL contiene /music/ la tratamos como audio.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
    }
    response = requests.get(url, headers=headers, allow_redirects=True)
    final_url = response.url

    if re.search(r'/music/', final_url):
        return "audio"
    if re.search(r'/video/', final_url):
        return "video"
    if re.search(r'/photo/|/share/', final_url):
        return "fotos"
    return "desconocido"

async def descargar_video(update: Update, url: str):
    """Descarga y envía un video (con audio) usando yt-dlp."""
    await update.message.reply_text("Descargando video...")
    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio/best[ext=mp4]/best',
        'outtmpl': str(DOWNLOADS_DIR / '%(id)s.%(ext)s'),
        'quiet': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        file_path = ydl.prepare_filename(info)
        if file_path.endswith(('.mp4', '.webm', '.m4a')):
            with cleanup_file(file_path):
                if file_path.endswith(('.mp4', '.webm')):
                    await update.message.reply_video(video=open(file_path, 'rb'),
                                                     caption='Aquí tienes tu video.')
                else:
                    await update.message.reply_audio(audio=open(file_path, 'rb'),
                                                     caption='Aquí tienes tu audio.')

async def descargar_audio(update: Update, url: str):
    """Extrae el enlace de audio usando Selenium y lo descarga."""
    await update.message.reply_text("Descargando audio...")
    options = Options()
    options.add_argument('--headless')
    # Opcional: en algunos entornos puede ser necesario agregar otros argumentos, ej. --no-sandbox
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        # Buscamos el contenedor del reproductor, identificado por el id "mse"
        try:
            container = driver.find_element(By.ID, "mse")
        except Exception as e:
            await update.message.reply_text("No se encontró el contenedor del reproductor de audio.")
            return
        
        # Dentro del contenedor, buscamos el elemento <video>
        try:
            video = container.find_element(By.TAG_NAME, "video")
        except Exception as e:
            await update.message.reply_text("No se encontró el elemento de video en el contenedor.")
            return
        
        audio_url = video.get_attribute("src")
        if not audio_url:
            await update.message.reply_text("El elemento de video no tiene atributo src.")
            return
        
        # Validamos que el recurso sea de tipo audio realizando una solicitud HEAD
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
        }
        head_resp = requests.head(audio_url, headers=headers, allow_redirects=True)
        content_type = head_resp.headers.get("Content-Type", "").lower()
        if "audio" not in content_type:
            await update.message.reply_text("El recurso obtenido no parece ser audio.")
            return
        
        # Descargamos el audio
        response = requests.get(audio_url, headers=headers)
        if response.status_code == 200:
            file_path = DOWNLOADS_DIR / 'audio_temp.m4a'
            with open(file_path, 'wb') as f:
                f.write(response.content)
            await update.message.reply_audio(audio=open(file_path, 'rb'),
                                             caption='Aquí tienes tu audio.')
            os.remove(file_path)
        else:
            await update.message.reply_text("No se pudo descargar el audio desde el enlace extraído.")
    except Exception as e:
        logger.error(f"Error en descargar_audio: {e}")
        await update.message.reply_text("Ocurrió un error al procesar el audio.")
    finally:
        driver.quit()

async def descargar_fotos(update: Update, url: str):
    """Extrae y envía fotos de una publicación de TikTok usando Selenium."""
    await update.message.reply_text("Descargando imágenes...")
    options = Options()
    options.add_argument('--headless')
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.get(url)
    driver.implicitly_wait(10)
    try:
        images = driver.find_elements(By.CSS_SELECTOR, 'img')
        image_urls = [img.get_attribute('src') for img in images if img.get_attribute('src')]
        if image_urls:
            media_group = [InputMediaPhoto(media=url) for url in image_urls[:10]]
            await update.message.reply_media_group(media=media_group)
        else:
            await update.message.reply_text("No se encontraron imágenes en este TikTok.")
    except NoSuchElementException:
        await update.message.reply_text("Error al extraer imágenes de la publicación.")
    finally:
        driver.quit()

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
    elif tipo == "audio":
        await descargar_audio(update, url)
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
    application.run_polling(poll_interval=1.0, timeout=30)

if __name__ == '__main__':
    main()
