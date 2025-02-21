import telebot
import os
import logging
from dotenv import load_dotenv
from TikTokApi import TikTokApi
import asyncio
from typing import List, Union
import traceback
import sys
import time
from telebot.handler_backends import State, StatesGroup
from telebot.storage import StateMemoryStorage
from flask import Flask, request
import nest_asyncio  # Agregar este import

# Modificar la configuración de logging para ser compatible con Railway
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log', mode='a')
    ]
)
logger = logging.getLogger(__name__)

# Cargar variables de entorno
load_dotenv()
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# Modificar la configuración para Railway
PORT = int(os.getenv('PORT', 8080))
WEBHOOK_URL = os.getenv('WEBHOOK_URL')
WEBHOOK_HOST = os.getenv('WEBHOOK_HOST', '0.0.0.0')

if not TOKEN:
    raise ValueError("No se encontró el token del bot. Asegúrate de configurar TELEGRAM_BOT_TOKEN")

# Instanciar el bot con manejo de estados y reintentos
state_storage = StateMemoryStorage()
bot = telebot.TeleBot(TOKEN, state_storage=state_storage)
bot.threaded = True  # Habilitar modo threaded para mejor rendimiento

# Crear la aplicación Flask
app = Flask(__name__)

# Permitir nested event loops
nest_asyncio.apply()

class TikTokDownloader:
    def __init__(self):
        self.temp_dir = 'temp'
        os.makedirs(self.temp_dir, exist_ok=True)
        self._api = None
        self._initialization_lock = asyncio.Lock()
        self._session_retry_count = 0
        self._max_retries = 3
        self._loop = None

    async def _ensure_api_initialized(self):
        if self._api is None:
            async with self._initialization_lock:
                if self._api is None:
                    while self._session_retry_count < self._max_retries:
                        try:
                            self._api = TikTokApi()
                            # La nueva versión no necesita create_sessions
                            break
                        except Exception as e:
                            self._session_retry_count += 1
                            logger.error(f"Intento {self._session_retry_count} fallido: {str(e)}")
                            if self._session_retry_count >= self._max_retries:
                                raise
                            await asyncio.sleep(5)

    async def download_content(self, url: str) -> List[str]:
        """
        Descarga cualquier tipo de contenido de TikTok (video, imágenes, audio)
        Args:
            url (str): URL del contenido de TikTok
        Returns:
            List[str]: Lista de rutas a los archivos descargados
        """
        try:
            await self._ensure_api_initialized()
            
            # Obtener el ID del contenido de la URL
            content_id = url.split('/')[-1].split('?')[0]
            
            # Obtener información del post usando la nueva API
            video = await self._api.video(id=content_id)
            downloaded_files = []
            
            # Si es un video
            video_path = os.path.join(self.temp_dir, f'tiktok_{content_id}.mp4')
            # Descargar video con reintentos
            for _ in range(3):
                try:
                    video_data = await video.bytes()
                    with open(video_path, 'wb') as f:
                        f.write(video_data)
                    downloaded_files.append(video_path)
                    break
                except Exception as e:
                    logger.warning(f"Reintentando descarga de video: {str(e)}")
                    await asyncio.sleep(1)
            
            # Si el video tiene música
            try:
                music = video.music
                if music and music.play_url:
                    audio_path = os.path.join(self.temp_dir, f'tiktok_{content_id}_audio.mp3')
                    audio_data = await music.bytes()
                    with open(audio_path, 'wb') as f:
                        f.write(audio_data)
                    downloaded_files.append(audio_path)
            except Exception as e:
                logger.warning(f"No se pudo descargar el audio: {str(e)}")
            
            if not downloaded_files:
                raise Exception("No se pudo descargar ningún contenido después de varios intentos")
                
            return downloaded_files
            
        except Exception as e:
            logger.error(f"Error al descargar el contenido: {str(e)}\n{traceback.format_exc()}")
            raise

    async def cleanup(self):
        """Limpia recursos cuando se cierra la aplicación"""
        if self._api:
            try:
                await self._api.close()
            except:
                pass
        # Limpiar archivos temporales
        try:
            for file in os.listdir(self.temp_dir):
                os.remove(os.path.join(self.temp_dir, file))
        except:
            pass

downloader = TikTokDownloader()

@bot.message_handler(commands=['start', 'help'])
def enviar_bienvenida(message):
    bot.reply_to(message, 
                "¡Hola! Envíame cualquier enlace de TikTok y te enviaré su contenido sin marca de agua.\n"
                "Puedo descargar:\n"
                "- Videos\n"
                "- Audio\n"
                "Solo envía el enlace y yo me encargo del resto.")

@bot.message_handler(func=lambda m: 'tiktok.com' in m.text.lower())
def manejar_tiktok(message):
    enlace = message.text.strip()
    msg = bot.reply_to(message, "⏳ Descargando contenido... Por favor, espera un momento.")
    
    try:
        # Usar el loop existente o crear uno nuevo
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Descargar el contenido con timeout
        try:
            archivos = loop.run_until_complete(asyncio.wait_for(
                downloader.download_content(enlace),
                timeout=300  # 5 minutos máximo
            ))
        except asyncio.TimeoutError:
            bot.edit_message_text(
                "❌ La descarga está tardando demasiado. Por favor, intenta de nuevo.",
                message.chat.id,
                msg.message_id
            )
            return
        
        if not archivos:
            bot.edit_message_text(
                "❌ No se encontró ningún contenido para descargar.",
                message.chat.id,
                msg.message_id
            )
            return
        
        # Enviar cada archivo descargado
        for archivo in archivos:
            try:
                if archivo.endswith('.mp4'):
                    with open(archivo, 'rb') as f:
                        bot.send_video(message.chat.id, f, timeout=60)
                elif archivo.endswith('.mp3'):
                    with open(archivo, 'rb') as f:
                        bot.send_audio(message.chat.id, f, timeout=60)
            except Exception as e:
                logger.error(f"Error enviando archivo {archivo}: {str(e)}")
                continue
            finally:
                # Eliminar el archivo temporal
                try:
                    os.remove(archivo)
                except Exception as e:
                    logger.warning(f"No se pudo eliminar el archivo temporal {archivo}: {str(e)}")
        
        bot.edit_message_text(
            "✅ ¡Contenido descargado y enviado con éxito!",
            message.chat.id,
            msg.message_id
        )
        
    except Exception as e:
        error_msg = f"❌ Error al procesar el contenido: {str(e)}"
        logger.error(error_msg)
        bot.edit_message_text(
            error_msg,
            message.chat.id,
            msg.message_id
        )

@bot.message_handler(func=lambda m: True)
def manejar_otro(message):
    bot.send_message(message.chat.id, "Por favor, envía un enlace de TikTok.")

def cleanup_resources():
    """Limpia recursos al cerrar la aplicación"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(downloader.cleanup())
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")

def init_webhook():
    """Inicializa el webhook del bot"""
    if os.getenv('RAILWAY_STATIC_URL'):
        webhook_base = os.getenv('RAILWAY_STATIC_URL')
        webhook_url = f"https://{webhook_base}/{TOKEN}"
        logger.info(f"Setting webhook for {webhook_url}")
        bot.remove_webhook()
        time.sleep(0.2)
        bot.set_webhook(url=webhook_url)

@app.route('/' + TOKEN, methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return 'ok'
    return 'error', 403

@app.route('/')
def health():
    return 'Bot is running'

def start_bot():
    try:
        logger.info("Starting bot...")
        
        if os.getenv('RAILWAY_STATIC_URL'):
            # Modo producción - usar webhook
            init_webhook()
            logger.info(f"Starting Flask server on port {PORT}")
            app.run(host='0.0.0.0', port=PORT)
        else:
            # Modo local - usar polling
            bot.remove_webhook()
            time.sleep(0.2)
            logger.info("Starting polling...")
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
            
    except Exception as e:
        logger.error(f"Bot initialization error: {e}")
        raise

if __name__ == "__main__":
    # Si se ejecuta directamente, iniciar en modo polling
    logger.info("Initializing bot...")
    retry_count = 0
    max_retries = 5
    
    while True:
        try:
            if retry_count > 0:
                logger.info(f"Retrying connection ({retry_count}/{max_retries})...")
                time.sleep(min(30, 5 * retry_count))
            
            start_bot()
            
        except Exception as e:
            logger.error(f"Polling error: {str(e)}")
            retry_count += 1
            
            if retry_count >= max_retries:
                logger.error("Maximum retries reached. Restarting process...")
                cleanup_resources()
                sys.exit(1)
            
            continue
        finally:
            cleanup_resources()
else:
    # Si se importa (por gunicorn), inicializar webhook
    init_webhook()