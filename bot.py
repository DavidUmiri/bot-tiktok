from telegram.ext import Application, CommandHandler, MessageHandler, filters
import requests
import re
import yt_dlp
import os
import logging
from telegram.error import NetworkError

# Configuración de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Configuración del bot
TOKEN = os.getenv("BOT_TOKEN")  # Reemplaza con tu token de Telegram

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
        # Configuración de yt-dlp
        ydl_opts = {
            'format': 'best',
            'outtmpl': 'downloads/%(id)s.%(ext)s',
            'quiet': True
        }

        await update.message.reply_text('Descargando contenido...')

        # Descarga el contenido
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)

        # Envía el archivo según su tipo
        if file_path.endswith(('.mp4', '.webm')):
            await update.message.reply_video(
                video=open(file_path, 'rb'),
                caption='Aquí tienes tu video de TikTok'
            )
        elif file_path.endswith(('.jpg', '.jpeg', '.png')):
            await update.message.reply_photo(
                photo=open(file_path, 'rb'),
                caption='Aquí tienes tu imagen de TikTok'
            )
        elif file_path.endswith(('.mp3', '.m4a', '.wav')):
            await update.message.reply_audio(
                audio=open(file_path, 'rb'),
                caption='Aquí tienes tu audio de TikTok'
            )

        # Limpia el archivo descargado
        os.remove(file_path)

    except Exception as e:
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