# agent/providers/whapi.py — Adaptador para Whapi.cloud
# Generado por AgentKit

import os
import io
import base64
import logging
import httpx
from fastapi import Request
from agent.providers.base import ProveedorWhatsApp, MensajeEntrante

logger = logging.getLogger("agentkit")

# Tipos de mensaje de audio/voz en WhatsApp
TIPOS_AUDIO = {"audio", "voice", "ptt"}
# Tipos de imagen soportados por Claude Vision
TIPOS_IMAGEN = {"image"}
# MIME types válidos para Claude (solo estos acepta)
MIME_VALIDOS = {"image/jpeg", "image/png", "image/gif", "image/webp"}


class ProveedorWhapi(ProveedorWhatsApp):
    """Proveedor de WhatsApp usando Whapi.cloud (REST API simple)."""

    def __init__(self):
        self.token = os.getenv("WHAPI_TOKEN")
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.url_envio = "https://gate.whapi.cloud/messages/text"
        self.url_media = "https://gate.whapi.cloud/media"

    async def parsear_webhook(self, request: Request) -> list[MensajeEntrante]:
        """Parsea el payload de Whapi.cloud. Maneja texto y audios."""
        body = await request.json()
        mensajes = []

        for msg in body.get("messages", []):
            tipo = msg.get("type", "text")

            if tipo == "text":
                texto = msg.get("text", {}).get("body", "")

            elif tipo in TIPOS_AUDIO:
                texto = await self._transcribir_audio(msg)
                if not texto:
                    texto = "__audio_sin_transcripcion__"

            elif tipo in TIPOS_IMAGEN:
                imagen_b64, imagen_mime, caption = await self._descargar_imagen(msg)
                # El caption es el texto que el cliente escribió junto a la foto (si lo hay)
                texto = caption or "El cliente envió una foto."
                mensajes.append(MensajeEntrante(
                    telefono=msg.get("chat_id", ""),
                    texto=texto,
                    mensaje_id=msg.get("id", ""),
                    es_propio=msg.get("from_me", False),
                    imagen_base64=imagen_b64,
                    imagen_mime=imagen_mime,
                ))
                continue  # Ya agregamos el mensaje, saltar al final del loop

            else:
                # Video, documento, sticker — ignorar por ahora
                continue

            mensajes.append(MensajeEntrante(
                telefono=msg.get("chat_id", ""),
                texto=texto,
                mensaje_id=msg.get("id", ""),
                es_propio=msg.get("from_me", False),
            ))

        return mensajes

    async def _transcribir_audio(self, msg: dict) -> str:
        """
        Descarga el audio desde Whapi y lo transcribe con OpenAI Whisper.
        Retorna el texto transcrito, o "" si falla.
        """
        # En Whapi, el endpoint de descarga usa el ID del mensaje completo
        audio_data = msg.get("audio") or msg.get("voice") or {}
        media_id = msg.get("id", "")  # ID del mensaje, no del campo audio

        if not media_id:
            logger.warning("Audio recibido sin media_id — no se puede descargar")
            return ""

        if not self.openai_key:
            logger.warning("OPENAI_API_KEY no configurado — no se puede transcribir audio")
            return ""

        headers_whapi = {"Authorization": f"Bearer {self.token}"}

        try:
            # 1. Descargar el audio desde Whapi
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.get(
                    f"{self.url_media}/{media_id}",
                    headers=headers_whapi
                )
                if r.status_code != 200:
                    logger.error(f"Error descargando audio de Whapi: {r.status_code}")
                    return ""
                audio_bytes = r.content

            logger.info(f"Audio descargado: {len(audio_bytes)} bytes")

            # 2. Enviar a OpenAI Whisper para transcripción
            async with httpx.AsyncClient(timeout=60) as client:
                r = await client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self.openai_key}"},
                    files={
                        "file": ("audio.ogg", io.BytesIO(audio_bytes), "audio/ogg"),
                        "model": (None, "whisper-1"),
                        "language": (None, "es"),
                    }
                )
                if r.status_code != 200:
                    logger.error(f"Error Whisper API: {r.status_code} — {r.text}")
                    return ""

                transcripcion = r.json().get("text", "").strip()
                logger.info(f"Audio transcrito: {transcripcion[:100]}")
                return transcripcion

        except Exception as e:
            logger.error(f"Error transcribiendo audio: {e}")
            return ""

    async def _descargar_imagen(self, msg: dict) -> tuple[str, str, str]:
        """
        Descarga la imagen desde Whapi y la retorna en base64.
        Retorna: (base64_string, mime_type, caption)
        """
        image_data = msg.get("image", {})
        media_id = image_data.get("id", "")
        caption = image_data.get("caption", "")
        mime_type = image_data.get("mime_type", "image/jpeg")

        # Normalizar MIME type — Claude solo acepta jpeg, png, gif, webp
        if mime_type not in MIME_VALIDOS:
            mime_type = "image/jpeg"

        if not media_id:
            logger.warning("Imagen recibida sin media_id")
            return "", "", caption

        headers_whapi = {"Authorization": f"Bearer {self.token}"}

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.get(
                    f"{self.url_media}/{media_id}",
                    headers=headers_whapi
                )
                if r.status_code != 200:
                    logger.error(f"Error descargando imagen de Whapi: {r.status_code}")
                    return "", "", caption

                imagen_b64 = base64.b64encode(r.content).decode("utf-8")
                logger.info(f"Imagen descargada y convertida a base64 ({len(r.content)} bytes)")
                return imagen_b64, mime_type, caption

        except Exception as e:
            logger.error(f"Error descargando imagen: {e}")
            return "", "", caption

    async def enviar_mensaje(self, telefono: str, mensaje: str) -> bool:
        """Envía mensaje via Whapi.cloud."""
        if not self.token:
            logger.warning("WHAPI_TOKEN no configurado — mensaje no enviado")
            return False
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(
                self.url_envio,
                json={"to": telefono, "body": mensaje},
                headers=headers,
            )
            if r.status_code != 200:
                logger.error(f"Error Whapi: {r.status_code} — {r.text}")
            return r.status_code == 200
