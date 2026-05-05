# agent/main.py — Servidor FastAPI + Webhook de WhatsApp
# Generado por AgentKit — Transportes Arroyo

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

from agent.brain import generar_respuesta
from agent.memory import inicializar_db, guardar_mensaje, obtener_historial
from agent.providers import obtener_proveedor

load_dotenv()

PALABRAS_CLAVE = [
    'mudanza', 'traslado', 'flete', 'transporte', 'mueble', 'sofa', 'sofá',
    'camion', 'camión', 'precio', 'cotizacion', 'cotización', 'costo',
    'cuanto', 'cuánto', 'informacion', 'información', 'info',
    'hola', 'buenas', 'buenos', 'quiero', 'necesito', 'ayuda',
    'servicio', 'despacho', 'carga', 'articulo', 'artículo'
]

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
log_level = logging.DEBUG if ENVIRONMENT == "development" else logging.INFO
logging.basicConfig(level=log_level)
logger = logging.getLogger("agentkit")

proveedor = obtener_proveedor()
PORT = int(os.getenv("PORT", 8000))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa la base de datos al arrancar el servidor."""
    await inicializar_db()
    logger.info("Base de datos inicializada")
    logger.info(f"Servidor AgentKit corriendo en puerto {PORT}")
    logger.info(f"Proveedor de WhatsApp: {proveedor.__class__.__name__}")
    yield


app = FastAPI(
    title="Transportes Arroyo — WhatsApp AI Agent",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def health_check():
    """Endpoint de salud para Railway/monitoreo."""
    return {"status": "ok", "service": "transportes-arroyo-agentkit"}


@app.get("/webhook")
async def webhook_verificacion(request: Request):
    """Verificación GET del webhook."""
    resultado = await proveedor.validar_webhook(request)
    if resultado is not None:
        return PlainTextResponse(str(resultado))
    return {"status": "ok"}


@app.post("/webhook")
async def webhook_handler(request: Request):
    """
    Recibe mensajes de WhatsApp via Whapi.cloud.
    Procesa el mensaje, genera respuesta con Claude y la envía de vuelta.
    """
    try:
        mensajes = await proveedor.parsear_webhook(request)

        for msg in mensajes:
            if msg.es_propio or not msg.texto or "@g.us" in msg.telefono:
                continue

            # Audio que llegó pero no se pudo transcribir (sin API key de OpenAI)
            if msg.texto == "__audio_sin_transcripcion__":
                await proveedor.enviar_mensaje(
                    msg.telefono,
                    "Recibí su audio, pero por el momento solo proceso mensajes de texto. "
                    "¿Podría escribirme lo que necesita?"
                )
                continue

            # Obtener historial ANTES de guardar el mensaje actual
            historial = await obtener_historial(msg.telefono)

            # Filtro: responder solo si hay conversación previa o el mensaje tiene palabras clave
            tiene_clave = any(p in msg.texto.lower() for p in PALABRAS_CLAVE)
            if not historial and not tiene_clave:
                logger.debug(f"Ignorado (sin palabras clave): {msg.telefono}: {msg.texto}")
                continue

            logger.info(f"Mensaje de {msg.telefono}: {msg.texto}")

            # Generar respuesta con Claude (texto, imagen si aplica, y teléfono para alertas)
            respuesta = await generar_respuesta(
                msg.texto,
                historial,
                telefono_cliente=msg.telefono,
                imagen_base64=msg.imagen_base64,
                imagen_mime=msg.imagen_mime,
            )

            # En memoria guardamos el texto (o una descripción si era imagen)
            texto_memoria = msg.texto if not msg.imagen_base64 else f"[Imagen] {msg.texto}"
            await guardar_mensaje(msg.telefono, "user", texto_memoria)
            await guardar_mensaje(msg.telefono, "assistant", respuesta)


            # Enviar respuesta por WhatsApp
            await proveedor.enviar_mensaje(msg.telefono, respuesta)

            logger.info(f"Respuesta a {msg.telefono}: {respuesta}")

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error en webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))
