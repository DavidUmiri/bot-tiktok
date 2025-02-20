# Bot de TikTok para Telegram

Este bot de Telegram permite descargar videos e imágenes de TikTok sin marca de agua, además de extraer el audio de las publicaciones.

## Características

- 🎥 Descarga videos de TikTok sin marca de agua
- 🖼️ Extrae imágenes de publicaciones de TikTok
- 🔊 Extrae y envía el audio de las publicaciones
- ♻️ Sistema de reintentos automáticos para mayor estabilidad
- 🔒 Manejo seguro de tokens mediante variables de entorno

## Requisitos

- Python 3.x
- Las siguientes bibliotecas de Python (instalables via pip):
  - python-telegram-bot
  - requests
  - python-dotenv

## Configuración

1. Crea un archivo `.env` en la raíz del proyecto con la siguiente variable:
   ```
   TELEGRAM_BOT_TOKEN=tu_token_de_telegram
   ```

2. Instala las dependencias:
   ```
   pip install -r requirements.txt
   ```

## Uso

1. Inicia el bot con:
   ```
   python bot.py
   ```

2. En Telegram:
   - Envía `/start` o `/help` para ver las instrucciones
   - Envía cualquier enlace de TikTok y el bot responderá con el contenido sin marca de agua

## Estructura del Proyecto

El proyecto utiliza un diseño orientado a objetos con:
- Patrón Singleton para la instancia del bot
- Patrón Factory para la creación de contenido
- Interfaces abstractas para extensibilidad
- Sistema de logging para monitoreo

## Despliegue

El proyecto incluye archivos necesarios para despliegue en Heroku:
- Procfile
- requirements.txt
- runtime.txt

## Soporte

El bot puede manejar:
- Videos de TikTok
- Publicaciones con imágenes
- Extracción de audio