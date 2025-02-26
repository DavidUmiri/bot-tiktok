# Bot de Telegram para Descargar Contenido de TikTok

Este es un bot de Telegram que permite a los usuarios enviar enlaces de TikTok y descargar el contenido, ya sea videos, audios o imágenes.

## Características

- Descarga videos y audios de TikTok.
- Obtiene imágenes de álbumes de fotos de TikTok.
- Responde a comandos de usuario de manera interactiva.

## Requisitos

Puedes instalar todas las dependencias necesarias ejecutando:

```bash
pip install -r requirements.txt
```

## Configuración

1. **Clonar el repositorio**

   Clona este repositorio en tu máquina local:

   ```bash
   git clone https://github.com/davidumiri/bot-tiktok
   cd tu_repositorio
   ```

2. **Configuración del Token de Telegram**

   Crea un archivo `.env` en la raíz del proyecto y agrega tu token de bot de Telegram:

   ```plaintext
   BOT_TOKEN=tu_token_aqui
   ```

3. **Ejecutar el bot**

   Para ejecutar el bot, utiliza el siguiente comando:

   ```bash
   python bot.py
   ```

## Uso

Envía un enlace de TikTok al bot y este descargará el contenido correspondiente. Puedes usar enlaces de videos, audios o fotos.