import telebot
import requests
import os
import uuid
import logging
from abc import ABC, abstractmethod
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ===================== Configuración y Dependencias =====================

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Cargar variables de entorno
load_dotenv()
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

if not TOKEN:
    raise ValueError("No se encontró el token del bot. Asegúrate de crear un archivo .env con TELEGRAM_BOT_TOKEN=tu_token")

# Configurar reintentos para requests
retry_strategy = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
)
adapter = HTTPAdapter(max_retries=retry_strategy)
http = requests.Session()
http.mount("https://", adapter)
http.mount("http://", adapter)

# Instanciar el bot (Singleton)
class BotSingleton:
    __instance = None

    @staticmethod
    def get_instance():
        if BotSingleton.__instance is None:
            BotSingleton.__instance = telebot.TeleBot(TOKEN)
        return BotSingleton.__instance

bot = BotSingleton.get_instance()

# ===================== Contratos y Estrategias =====================

class IContenido(ABC):
    """
    Interfaz para los tipos de contenido extraídos de TikTok.
    """
    @abstractmethod
    def enviar_contenido(self, chat_id: int):
        pass

class IExtractor(ABC):
    """
    Interfaz para la extracción de contenido de TikTok.
    """
    @abstractmethod
    def extraer(self, url: str) -> dict:
        pass

# ===================== Implementación del Extractor =====================

class TikTokExtractor(IExtractor):
    """
    Clase responsable de conectar con la API de tikwm.com y extraer los datos.
    """
    API_ENDPOINT = "https://www.tikwm.com/api/"

    def extraer(self, url: str) -> dict:
        api_url = f"{self.API_ENDPOINT}?url={url}"
        try:
            response = http.get(api_url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if not data.get("data"):
                raise ValueError("No se encontraron datos en la respuesta de la API.")
            
            video_data = data["data"]
            
            # Procesar y asignar la URL del audio
            audio_url = None
            if "music" in video_data and video_data["music"]:
                audio_url = video_data["music"]
            elif "music_url" in video_data and video_data["music_url"]:
                audio_url = video_data["music_url"]
            elif "music_info" in video_data and video_data["music_info"].get("play_url"):
                audio_url = video_data["music_info"]["play_url"]
            
            # Asegurarse de que las imágenes estén en una lista si existen
            if "images" in video_data and isinstance(video_data["images"], str):
                video_data["images"] = [video_data["images"]]
            elif "image_post_info" in video_data:
                video_data["images"] = [img["display_image"]["url_list"][0] for img in video_data["image_post_info"]]
            
            logger.info(f"Audio URL encontrada: {audio_url}")
            logger.info(f"Tipo de contenido: {'imágenes' if 'images' in video_data else 'video'}")
            
            video_data["audio"] = audio_url
            return video_data
            
        except Exception as e:
            logger.error(f"Error en extractor: {str(e)}")
            raise Exception(f"Error al conectar con la API: {str(e)}")

# ===================== Clases de Contenido =====================

class VideoContenido(IContenido):
    """
    Clase para manejar contenido de tipo video.
    """
    def __init__(self, video_url: str, audio_url: str):
        self.video_url = video_url
        self.audio_url = audio_url

    def enviar_contenido(self, chat_id: int):
        try:
            bot.send_video(chat_id, self.video_url, caption="🎥 Aquí tienes el video sin marca de agua.")
            if self.audio_url:
                self.enviar_audio(chat_id)
            else:
                logger.info("No se encontró URL de audio para este contenido")
        except Exception as e:
            logger.error(f"Error al enviar video: {str(e)}")
            bot.send_message(chat_id, f"Error al enviar el contenido: {str(e)}")

    def enviar_audio(self, chat_id: int):
        if not self.audio_url:
            return
            
        audio_path = None
        try:
            logger.info(f"Intentando descargar audio desde: {self.audio_url}")
            audio_response = http.get(self.audio_url, stream=True)
            audio_response.raise_for_status()
            
            # Generar nombre único para el archivo
            audio_filename = f"audio_{str(uuid.uuid4())[:8]}.mp3"
            audio_path = os.path.join('temp', audio_filename)
            
            # Asegurar que el directorio temp existe
            os.makedirs('temp', exist_ok=True)
            
            with open(audio_path, "wb") as f:
                for chunk in audio_response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            logger.info(f"Audio descargado en: {audio_path}")
            
            with open(audio_path, "rb") as audio:
                bot.send_audio(chat_id, audio, caption=f"🔊 Audio del video: {audio_filename}")
        except Exception as e:
            logger.error(f"Error con el audio: {str(e)}")
            bot.send_message(chat_id, f"❌ Error con el audio: {str(e)}")
        finally:
            if audio_path and os.path.exists(audio_path):
                os.remove(audio_path)
                logger.info(f"Archivo temporal {audio_path} eliminado")

class ImagenesContenido(IContenido):
    """
    Clase para manejar contenido de tipo imágenes.
    """
    def __init__(self, imagenes_urls: list, audio_url: str):
        self.imagenes_urls = imagenes_urls
        self.audio_url = audio_url

    def enviar_contenido(self, chat_id: int):
        try:
            media_group = []
            for img_url in self.imagenes_urls:
                media_group.append(telebot.types.InputMediaPhoto(img_url))
            bot.send_media_group(chat_id, media_group)
            if self.audio_url:
                self.enviar_audio(chat_id)
        except Exception as e:
            logger.error(f"Error al enviar imágenes: {str(e)}")
            bot.send_message(chat_id, f"Error al enviar el contenido: {str(e)}")

    def enviar_audio(self, chat_id: int):
        if not self.audio_url:
            return
            
        audio_path = None
        try:
            logger.info(f"Intentando descargar audio desde: {self.audio_url}")
            audio_response = http.get(self.audio_url, stream=True)
            audio_response.raise_for_status()
            
            # Generar nombre único para el archivo
            audio_filename = f"audio_{str(uuid.uuid4())[:8]}.mp3"
            audio_path = os.path.join('temp', audio_filename)
            
            # Asegurar que el directorio temp existe
            os.makedirs('temp', exist_ok=True)
            
            with open(audio_path, "wb") as f:
                for chunk in audio_response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            logger.info(f"Audio descargado en: {audio_path}")
            
            with open(audio_path, "rb") as audio:
                bot.send_audio(chat_id, audio, caption="🔊 Audio de la publicación")
        except Exception as e:
            logger.error(f"Error con el audio: {str(e)}")
            bot.send_message(chat_id, f"❌ Error con el audio: {str(e)}")
        finally:
            if audio_path and os.path.exists(audio_path):
                os.remove(audio_path)
                logger.info(f"Archivo temporal {audio_path} eliminado")

# ===================== Factory para Crear el Contenido =====================

class ContenidoFactory:
    """
    Factory para crear instancias de IContenido según el tipo detectado.
    """
    @staticmethod
    def crear_contenido(data: dict) -> IContenido:
        audio_url = data.get("audio", None)
        if "play" in data and data["play"]:
            return VideoContenido(video_url=data["play"], audio_url=audio_url)
        elif "images" in data and data["images"]:
            return ImagenesContenido(imagenes_urls=data["images"], audio_url=audio_url)
        else:
            raise ValueError("El contenido no es reconocible como video o imágenes.")

# ===================== Controlador del Bot =====================

class TikTokBotController:
    def __init__(self, extractor: IExtractor, factory: ContenidoFactory):
        self.extractor = extractor
        self.factory = factory

    def procesar_enlace(self, chat_id: int, enlace: str):
        bot.send_message(chat_id, "⏳ Procesando tu enlace...")
        try:
            data = self.extractor.extraer(enlace)
            contenido = self.factory.crear_contenido(data)
            contenido.enviar_contenido(chat_id)
        except Exception as e:
            bot.send_message(chat_id, f"❌ Error al procesar el enlace: {e}")

# ===================== Inicialización del Bot y Handlers =====================

extractor = TikTokExtractor()
factory = ContenidoFactory()
controller = TikTokBotController(extractor, factory)

@bot.message_handler(commands=['start', 'help'])
def enviar_bienvenida(message):
    bot.reply_to(message, "¡Hola! Envíame el enlace de un TikTok y te enviaré su contenido (video/imágenes) junto con el audio.")

@bot.message_handler(func=lambda m: 'tiktok.com' in m.text.lower())
def manejar_tiktok(message):
    enlace = message.text.strip()
    controller.procesar_enlace(message.chat.id, enlace)

@bot.message_handler(func=lambda m: True)
def manejar_otro(message):
    bot.send_message(message.chat.id, "Por favor, envía un enlace de TikTok.")

# ===================== Punto de Entrada =====================

def main():
    logger.info("Bot iniciado...")
    while True:
        try:
            bot.polling(none_stop=True)
        except Exception as e:
            logger.error(f"Error en el bot: {str(e)}")
            continue

if __name__ == '__main__':
    main()