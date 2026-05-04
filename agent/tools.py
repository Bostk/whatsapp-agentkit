# agent/tools.py — Herramientas del agente Transportes Arroyo
# Generado por AgentKit

import os
import yaml
import logging
from datetime import datetime

logger = logging.getLogger("agentkit")

# Rutas que opera Transportes Arroyo
RUTAS_DISPONIBLES = [
    "Santiago → Concepción",
    "Concepción → Santiago",
    "Concepción → Puerto Montt",
    "Puerto Montt → Concepción",
    "Santiago → Puerto Montt",
    "Puerto Montt → Santiago",
]


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
    esta_abierto = 8 <= hora_actual < 22  # 8am a 10pm aprox
    return {
        "horario": info.get("negocio", {}).get("horario", "Lunes a Domingo 8:00am a 10:30pm"),
        "esta_abierto": esta_abierto,
    }


def verificar_ruta(origen: str, destino: str) -> dict:
    """
    Verifica si Transportes Arroyo opera una ruta específica.
    Retorna si la ruta está disponible y las ciudades intermedias.
    """
    ciudades_validas = ["santiago", "concepción", "concepcion", "puerto montt"]
    origen_ok = any(c in origen.lower() for c in ciudades_validas)
    destino_ok = any(c in destino.lower() for c in ciudades_validas)

    if origen_ok and destino_ok:
        return {
            "disponible": True,
            "mensaje": f"Sí operamos la ruta {origen} → {destino}. Podemos coordinar tu traslado.",
        }
    return {
        "disponible": False,
        "mensaje": "Actualmente operamos en el eje Santiago – Concepción – Puerto Montt.",
    }


def calificar_lead_b2b(texto_cliente: str) -> dict:
    """
    Analiza el mensaje del cliente para detectar si es un potencial lead B2B
    (fabricante de muebles o sofás).
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
        return {
            "es_b2b": True,
            "confianza": "alta",
            "accion": "Ofrecer servicio B2B con factura y conectar con equipo comercial",
        }
    elif len(coincidencias) == 1:
        return {
            "es_b2b": True,
            "confianza": "media",
            "accion": "Preguntar si son empresa o fabricante para calificar mejor",
        }
    return {
        "es_b2b": False,
        "confianza": "baja",
        "accion": "Atender como cliente particular",
    }


def registrar_coordinacion(telefono: str, nombre: str, ruta: str, descripcion_carga: str) -> dict:
    """
    Registra una solicitud de coordinación/cotización.
    En producción esto podría conectarse a un CRM o enviar un email al equipo.
    """
    logger.info(
        f"NUEVA COORDINACIÓN — Tel: {telefono} | Nombre: {nombre} | "
        f"Ruta: {ruta} | Carga: {descripcion_carga}"
    )
    return {
        "registrado": True,
        "mensaje": (
            f"Coordinación registrada para {nombre}. "
            "El equipo de Transportes Arroyo te contactará pronto."
        ),
    }
