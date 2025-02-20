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
            # Aumentamos el timeout a 30 segundos
            response = http.get(api_url, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if not data.get("data"):
                raise ValueError("No se encontraron datos en la respuesta de la API.")
            
            video_data = data["data"]
            logger.info(f"Datos recibidos de la API: {video_data.keys()}")
            
            # Procesar y asignar la URL del audio
            audio_url = None
            if "music" in video_data and video_data["music"]:
                audio_url = video_data["music"]
            elif "music_url" in video_data and video_data["music_url"]:
                audio_url = video_data["music_url"]
            elif "music_info" in video_data and video_data["music_info"].get("play_url"):
                audio_url = video_data["music_info"]["play_url"]
            
            # Mejorada la detección de imágenes
            images = []
            if "images" in video_data and video_data.get("images"):
                if isinstance(video_data["images"], list):
                    images.extend(video_data["images"])
                elif isinstance(video_data["images"], str):
                    images.append(video_data["images"])
                logger.info(f"Imágenes detectadas (formato images): {len(images)}")
            
            if "image_post_info" in video_data:
                for img in video_data.get("image_post_info", []):
                    if isinstance(img, dict):
                        if "display_image" in img:
                            url_list = img["display_image"].get("url_list", [])
                            if url_list and isinstance(url_list, list) and url_list[0]:
                                images.append(url_list[0])
                        elif "images" in img:
                            url_list = img["images"]
                            if isinstance(url_list, list) and url_list:
                                images.extend(url_list)
                logger.info(f"Imágenes detectadas (formato image_post_info): {len(images)}")
            
            # Asegurarse de que play no esté presente en caso de imágenes
            if images:
                video_data["images"] = images
                video_data.pop("play", None)  # Eliminar play si existe para forzar el modo imagen
            
            video_data["audio"] = audio_url
            
            logger.info(f"Audio URL encontrada: {audio_url}")
            logger.info(f"Tipo de contenido final: {'imágenes' if video_data.get('images') else 'video'}")
            logger.info(f"Total de imágenes encontradas: {len(video_data.get('images', []))}")
            
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
            # Verificar primero el tamaño del video
            video_response = http.head(self.video_url, timeout=30)
            content_length = int(video_response.headers.get('content-length', 0))
            
            # 50MB (límite del servidor por defecto de Telegram)
            if content_length > 52428800:
                bot.send_message(chat_id, "⚠️ El video supera el límite de 50MB del servidor de Telegram. Te envío el enlace para que puedas descargarlo:")
                bot.send_message(chat_id, self.video_url)
            else:
                bot.send_video(chat_id, self.video_url, caption="🎥 Aquí tienes el video sin marca de agua.")
            
            if self.audio_url:
                self.enviar_audio(chat_id)
            else:
                logger.info("No se encontró URL de audio para este contenido")
        except Exception as e:
            logger.error(f"Error al enviar video: {str(e)}")
            bot.send_message(chat_id, f"❌ Error al enviar el video. Puedes intentar descargarlo directamente desde este enlace:\n{self.video_url}")

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
        if isinstance(imagenes_urls, str):
            imagenes_urls = [imagenes_urls]
        self.imagenes_urls = imagenes_urls if isinstance(imagenes_urls, list) else []
        self.audio_url = audio_url

    def enviar_contenido(self, chat_id: int):
        try:
            if not self.imagenes_urls:
                bot.send_message(chat_id, "❌ No se encontraron imágenes en este contenido.")
                return

            logger.info(f"Intentando enviar {len(self.imagenes_urls)} imágenes")
            media_group = []
            
            for img_url in self.imagenes_urls:
                logger.info(f"Procesando imagen: {img_url}")
                # Verificar que la URL no sea None o vacía
                if img_url and isinstance(img_url, str) and img_url.strip():
                    try:
                        media = telebot.types.InputMediaPhoto(img_url)
                        media_group.append(media)
                    except Exception as e:
                        logger.error(f"Error al procesar imagen {img_url}: {str(e)}")
            
            if media_group:
                bot.send_message(chat_id, "📸 Enviando imágenes...")
                # Enviar imágenes en grupos de 10 (límite de Telegram)
                for i in range(0, len(media_group), 10):
                    group = media_group[i:i+10]
                    bot.send_media_group(chat_id, group)
                    
                if self.audio_url:
                    self.enviar_audio(chat_id)
            else:
                bot.send_message(chat_id, "❌ No se pudieron procesar las imágenes.")
        except Exception as e:
            logger.error(f"Error al enviar imágenes: {str(e)}")
            bot.send_message(chat_id, f"❌ Error al enviar las imágenes: {str(e)}")

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
        logger.info(f"Creando contenido. Tiene imágenes: {'images' in data}, Tiene video: {'play' in data}")
        
        # Primero verificar si hay imágenes y son válidas
        if "images" in data and data["images"] and isinstance(data["images"], (list, str)):
            logger.info("Creando contenido de tipo imagen")
            return ImagenesContenido(imagenes_urls=data["images"], audio_url=audio_url)
        # Si no hay imágenes válidas, intentar con video
        elif "play" in data and data["play"]:
            logger.info("Creando contenido de tipo video")
            return VideoContenido(video_url=data["play"], audio_url=audio_url)
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