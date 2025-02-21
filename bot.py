from telegram.ext import Application, CommandHandler, MessageHandler, filters
import requests
import re
import yt_dlp
import os
import logging
from telegram.error import NetworkError
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
# Configuración de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
# Configuración del bot
TOKEN = os.getenv("BOT_TOKEN")
# Función para obtener imágenes de TikTok usando Selenium
async def get_images_from_tiktok(url):
    options = Options()
    options.add_argument('--headless')  # Ejecutar en modo sin cabeza (sin GUI)
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.get(url)
    driver.implicitly_wait(10)  # Esperar hasta 10 segundos
    # Busca el contenedor de imágenes
    photo_container = driver.find_element(By.CLASS_NAME, 'css-kgj69c-DivPhotoVideoContainer')
    image_urls = set()  # Usar un conjunto para evitar duplicados
    if photo_container:
        images = photo_container.find_elements(By.CSS_SELECTOR, 'img.css-brxox6-ImgPhotoSlide')
        logging.info(f'Número total de imágenes encontradas: {len(images)}')
        for img in images:
            img_url = img.get_attribute('src')
            logging.info(f'URL de imagen encontrada: {img_url}')  # Log de la URL encontrada
            # Filtrar URLs basadas en un patrón más general
            if re.search(r'tiktokcdn.*?\.jpeg', img_url):
                image_urls.add(img_url)
    else:
        logging.error("No se encontró el contenedor de imágenes.")
        
    driver.quit()
    return list(image_urls)
async def start(update, context):
    """Maneja el comando /start"""
    await update.message.reply_text('¡Hola! Envíame un enlace de TikTok y descargaré el contenido para ti.')
async def download_tiktok(update, context):
    """Maneja los enlaces de TikTok"""
    url = update.message.text
    # Verifica si es un enlace de TikTok
    if not re.match(r'https?://(?:www\.)?(?:vm\.)?tiktok\.com/', url):
        await update.message.reply_text('Por favor, envía un enlace válido de TikTok.')
        return
    try:
        # Manejo de enlaces acortados
        response = requests.get(url, allow_redirects=True)
        final_url = response.url  # Obtiene la URL final después de la redirección
        logging.info(f'URL final después de redirección: {final_url}')
        # Verifica si el enlace es de un video o audio
        if re.search(r'/video/', final_url):
            # Configuración de yt-dlp
            ydl_opts = {
                'format': 'best',
                'outtmpl': 'downloads/%(id)s.%(ext)s',
                'quiet': True
            }
            await update.message.reply_text('Descargando contenido de video o audio...')
            # Descarga el contenido
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(final_url, download=True)
                file_path = ydl.prepare_filename(info)
            # Envía el archivo según su tipo
            if file_path.endswith(('.mp4', '.webm')):
                await update.message.reply_video(
                    video=open(file_path, 'rb'),
                    caption='Aquí tienes tu video de TikTok'
                )
            elif file_path.endswith(('.mp3', '.m4a', '.wav')):
                await update.message.reply_audio(
                    audio=open(file_path, 'rb'),
                    caption='Aquí tienes tu audio de TikTok'
                )
            # Limpia el archivo descargado
            os.remove(file_path)
        # Si el enlace es de una foto o álbum de fotos
        elif re.search(r'/photo/', final_url) or re.search(r'/share/', final_url):
            await update.message.reply_text('Descargando contenido de imágenes...')
            image_urls = await get_images_from_tiktok(final_url)  # Llama a la función para obtener imágenes
            if image_urls:
                for img_url in image_urls:
                    await update.message.reply_photo(photo=img_url, caption='Aquí tienes una imagen de TikTok')
            else:
                await update.message.reply_text('No se encontraron imágenes en el enlace proporcionado.')
        else:
            await update.message.reply_text('Lo siento, no puedo manejar este tipo de enlace.')
    except requests.exceptions.RequestException as e:
        logging.error(f'Error en la solicitud HTTP: {str(e)}')
        await update.message.reply_text('Hubo un problema al acceder al enlace. Intenta de nuevo más tarde.')
    except Exception as e:
        logging.error(f'Error inesperado: {str(e)}')
        await update.message.reply_text(f'Lo siento, hubo un error al descargar el contenido: {str(e)}')
def main():
    """Función principal del bot"""
    # Crea el directorio de descargas si no existe
    if not os.path.exists('downloads'):
        os.makedirs('downloads')
    # Configura y inicia el bot
    application = Application.builder().token(TOKEN).build()
    # Añade los manejadores
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_tiktok))
    # Inicia el bot con manejo de errores
    try:
        application.run_polling(poll_interval=1.0, timeout=30)
    except NetworkError as e:
        logging.error(f"Error de red: {e}")
    except Exception as e:
        logging.error(f"Error inesperado: {e}")
if __name__ == '__main__':
    main()