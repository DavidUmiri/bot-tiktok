# TikTok Downloader Bot

Bot de Telegram que permite descargar contenido de TikTok sin marca de agua.

## Características

- Descarga videos de TikTok sin marca de agua
- Descarga imágenes de publicaciones
- Extrae audio de videos
- Manejo automático de diferentes tipos de contenido

## Requisitos

- Python 3.12+
- Token de bot de Telegram
- Las dependencias listadas en `requirements.txt`

## Configuración Local

1. Crear un archivo `.env` en el directorio raíz con:
```
TELEGRAM_BOT_TOKEN=tu_token_aqui
```

2. Instalar dependencias:
```bash
pip install -r requirements.txt
python -m playwright install
```

3. Ejecutar el bot:
```bash
python bot.py
```

## Despliegue en Railway

1. Fork o clona este repositorio
2. Crea una cuenta en Railway.app
3. Crea un nuevo proyecto en Railway seleccionando el repositorio
4. Configura las variables de entorno en Railway:
   - `TELEGRAM_BOT_TOKEN`: Tu token de bot de Telegram
   - `PYTHON_VERSION`: 3.12.x

5. Railway detectará automáticamente que es una aplicación Python y la desplegará

### Notas para el despliegue en Railway:
- El bot se iniciará automáticamente después del despliegue
- Railway reinstalará las dependencias automáticamente
- El sistema de archivos es efímero, por lo que los archivos temporales se limpiarán automáticamente
- Los logs están disponibles en el dashboard de Railway

## Despliegue en Heroku

El bot está configurado para ser desplegado en Heroku:

1. Asegúrate de tener el CLI de Heroku instalado
2. Crear una nueva aplicación en Heroku
3. Configurar las variables de entorno en Heroku:
   - TELEGRAM_BOT_TOKEN
4. Desplegar usando Git:
```bash
git init
git add .
git commit -m "Initial commit"
heroku git:remote -a tu-app-name
git push heroku main
```

## Notas importantes

- El bot utiliza una carpeta temporal `temp/` para almacenar archivos durante la descarga
- Los archivos se eliminan automáticamente después de ser enviados
- Se requiere una conexión estable a internet para el funcionamiento correcto
- El bot está optimizado para funcionar en Railway con recursos limitados