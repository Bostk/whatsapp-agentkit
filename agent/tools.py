# agent/tools.py — Herramientas del agente Transportes Arroyo
# Generado por AgentKit

import os
import httpx
import yaml
import logging
from datetime import datetime

logger = logging.getLogger("agentkit")

# Número de Leonardo (dueño) para recibir alertas
TELEFONO_DUENO = os.getenv("TELEFONO_DUENO", "56935231643")


def cargar_info_negocio() -> dict:
    """Carga la información del negocio desde business.yaml."""
    try:
        with open("config/business.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logger.error("config/business.yaml no encontrado")
        return {}


def obtener_horario() -> dict:
    """Retorna el horario de atención del negocio."""
    info = cargar_info_negocio()
    hora_actual = datetime.now().hour
    esta_abierto = 8 <= hora_actual < 22
    return {
        "horario": info.get("negocio", {}).get("horario", "Lunes a Domingo 8:00am a 10:30pm"),
        "esta_abierto": esta_abierto,
    }


def verificar_ruta(origen: str, destino: str) -> dict:
    """
    Verifica si Transportes Arroyo opera una ruta.
    Cubrimos TODO el corredor Santiago – Puerto Montt, incluyendo todas las ciudades intermedias.
    """
    # Siempre disponible dentro del corredor — el agente nunca debe rechazar una ruta
    return {
        "disponible": True,
        "mensaje": f"Sí operamos esa ruta. Podemos coordinar el traslado de {origen} a {destino}.",
    }


def calificar_lead_b2b(texto_cliente: str) -> dict:
    """
    Analiza el mensaje del cliente para detectar si es un potencial lead B2B.
    """
    palabras_clave_b2b = [
        "fabricante", "fábrica", "fabrica", "manufactura", "producción",
        "muebles", "sofás", "sofas", "sillones", "tapizados",
        "despacho", "distribución", "proveedor", "factura", "empresa",
        "lote", "carga", "volumen", "mensual", "frecuente",
    ]
    texto_lower = texto_cliente.lower()
    coincidencias = [p for p in palabras_clave_b2b if p in texto_lower]

    if len(coincidencias) >= 2:
        return {"es_b2b": True, "confianza": "alta",
                "accion": "Ofrecer servicio B2B con factura y conectar con equipo comercial"}
    elif len(coincidencias) == 1:
        return {"es_b2b": True, "confianza": "media",
                "accion": "Preguntar si son empresa o fabricante para calificar mejor"}
    return {"es_b2b": False, "confianza": "baja", "accion": "Atender como cliente particular"}


async def notificar_dueno(nombre_cliente: str, telefono_cliente: str, motivo: str) -> dict:
    """
    Envía un WhatsApp de alerta a Leonardo (dueño) cuando un cliente necesita atención directa.
    Por ejemplo: cuando pide hablar con el dueño o escalar la conversación.
    """
    token = os.getenv("WHAPI_TOKEN")
    if not token:
        logger.warning("WHAPI_TOKEN no configurado — alerta no enviada")
        return {"enviado": False, "error": "Token no configurado"}

    mensaje_alerta = (
        f"ALERTA Transportes Arroyo\n"
        f"Cliente: {nombre_cliente}\n"
        f"Teléfono: +{telefono_cliente}\n"
        f"Motivo: {motivo}\n"
        f"Requiere atención directa."
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                "https://gate.whapi.cloud/messages/text",
                json={"to": TELEFONO_DUENO, "body": mensaje_alerta},
                headers=headers,
                timeout=10,
            )
            if r.status_code == 200:
                logger.info(f"Alerta enviada a dueño: {nombre_cliente} / {motivo}")
                return {"enviado": True}
            else:
                logger.error(f"Error enviando alerta: {r.status_code} {r.text}")
                return {"enviado": False, "error": r.text}
    except Exception as e:
        logger.error(f"Excepción enviando alerta: {e}")
        return {"enviado": False, "error": str(e)}


def registrar_coordinacion(telefono: str, nombre: str, ruta: str, descripcion_carga: str) -> dict:
    """
    Registra una solicitud de coordinación/cotización.
    """
    logger.info(
        f"NUEVA COORDINACIÓN — Tel: {telefono} | Nombre: {nombre} | "
        f"Ruta: {ruta} | Carga: {descripcion_carga}"
    )
    return {
        "registrado": True,
        "mensaje": (
            f"Coordinación registrada para {nombre}. "
            "El equipo de Transportes Arroyo le contactará pronto."
        ),
    }
