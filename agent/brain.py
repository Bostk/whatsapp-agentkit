# agent/brain.py — Cerebro del agente: conexión con Claude API
# Generado por AgentKit — Transportes Arroyo

import os
import yaml
import json
import logging
from anthropic import AsyncAnthropic
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("agentkit")

client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Definición de herramientas disponibles para Claude
TOOLS = [
    {
        "name": "notificar_dueno",
        "description": (
            "Envía una alerta de WhatsApp al equipo de Transportes Arroyo cuando un cliente "
            "quiere contacto humano directo. Usar SIEMPRE que el cliente mencione: "
            "'Leonardo', 'el dueño', 'el encargado', 'una persona real', 'un humano', "
            "'alguien de verdad', 'no quiero hablar con un bot', o cualquier alusión "
            "a querer hablar con una persona en lugar del agente."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre_cliente": {
                    "type": "string",
                    "description": "Nombre del cliente si lo proporcionó, o 'Desconocido'."
                },
                "telefono_cliente": {
                    "type": "string",
                    "description": "Número de teléfono del cliente (sin el +)."
                },
                "motivo": {
                    "type": "string",
                    "description": "Breve descripción de por qué el cliente solicita atención directa."
                }
            },
            "required": ["nombre_cliente", "telefono_cliente", "motivo"]
        }
    }
]


def cargar_config_prompts() -> dict:
    """Lee toda la configuración desde config/prompts.yaml."""
    try:
        with open("config/prompts.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.error("config/prompts.yaml no encontrado")
        return {}


def cargar_knowledge() -> str:
    """
    Lee los archivos de conocimiento de la carpeta /knowledge y los devuelve
    como texto adicional para incluir en el system prompt.
    Solo carga archivos .txt — sin datos personales (chats exportados se excluyen por .gitignore).
    """
    archivos_permitidos = ["conversaciones_ejemplo.txt", "estilo_leonardo.txt"]
    knowledge_dir = "knowledge"
    secciones = []

    for nombre in archivos_permitidos:
        ruta = os.path.join(knowledge_dir, nombre)
        if not os.path.exists(ruta):
            continue
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                contenido = f.read().strip()
            if contenido:
                secciones.append(f"### {nombre}\n{contenido}")
                logger.debug(f"Knowledge cargado: {nombre} ({len(contenido)} chars)")
        except Exception as e:
            logger.warning(f"No se pudo leer {nombre}: {e}")

    if not secciones:
        return ""

    return (
        "\n\n---\n"
        "## Material de referencia — Conversaciones reales y estilo de venta\n"
        "Usa estos ejemplos para calibrar exactamente el tono, las frases y el flujo "
        "de ventas que funciona con los clientes de Transportes Arroyo. "
        "NO los repitas literalmente, pero sí aprende el estilo.\n\n"
        + "\n\n".join(secciones)
    )


def cargar_system_prompt() -> str:
    """Lee el system prompt desde config/prompts.yaml y añade el knowledge base."""
    config = cargar_config_prompts()
    base = config.get("system_prompt", "Eres un asistente útil. Responde en español.")
    knowledge = cargar_knowledge()
    return base + knowledge


def obtener_mensaje_error() -> str:
    config = cargar_config_prompts()
    return config.get("error_message", "Lo siento, estoy teniendo problemas técnicos. Por favor intenta de nuevo.")


def obtener_mensaje_fallback() -> str:
    config = cargar_config_prompts()
    return config.get("fallback_message", "Disculpa, no entendí su mensaje. ¿Podría repetirlo?")


async def generar_respuesta(
    mensaje: str,
    historial: list[dict],
    telefono_cliente: str = "",
    imagen_base64: str = "",
    imagen_mime: str = ""
) -> str:
    """
    Genera una respuesta usando Claude API con soporte de herramientas y visión.

    Args:
        mensaje: El mensaje nuevo del usuario (o transcripción de audio)
        historial: Lista de mensajes anteriores [{"role": "user/assistant", "content": "..."}]
        telefono_cliente: Número del cliente para incluir en alertas
        imagen_base64: Imagen en base64 si el cliente mandó una foto
        imagen_mime: MIME type de la imagen (image/jpeg, image/png, etc.)

    Returns:
        La respuesta generada por Claude
    """
    if not mensaje or not mensaje.strip():
        return obtener_mensaje_fallback()

    system_prompt = cargar_system_prompt()

    # Historial previo (solo texto — las imágenes no se guardan en memoria)
    mensajes = []
    for msg in historial:
        mensajes.append({"role": msg["role"], "content": msg["content"]})

    # Mensaje actual — puede ser texto solo o texto + imagen
    if imagen_base64 and imagen_mime:
        # Mensaje multimodal: Claude ve la imagen y el texto juntos
        contenido_usuario = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": imagen_mime,
                    "data": imagen_base64,
                }
            },
            {
                "type": "text",
                "text": mensaje or "El cliente envió esta foto. Analízala en el contexto del servicio de mudanzas."
            }
        ]
    else:
        contenido_usuario = mensaje

    mensajes.append({"role": "user", "content": contenido_usuario})

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system_prompt,
            tools=TOOLS,
            messages=mensajes
        )

        logger.info(f"Respuesta generada ({response.usage.input_tokens} in / {response.usage.output_tokens} out)")

        # Verificar si Claude quiere usar una herramienta
        if response.stop_reason == "tool_use":
            tool_results = []

            for block in response.content:
                if block.type == "tool_use" and block.name == "notificar_dueno":
                    inputs = block.input
                    # Si no tenemos el teléfono del cliente en los inputs, usamos el real
                    if not inputs.get("telefono_cliente") or inputs["telefono_cliente"] == "Desconocido":
                        inputs["telefono_cliente"] = telefono_cliente

                    from agent.tools import notificar_dueno
                    resultado = await notificar_dueno(
                        nombre_cliente=inputs.get("nombre_cliente", "Desconocido"),
                        telefono_cliente=inputs.get("telefono_cliente", telefono_cliente),
                        motivo=inputs.get("motivo", "Solicita hablar con el dueño")
                    )

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(resultado)
                    })

            # Continuar la conversación con el resultado de la herramienta
            mensajes_con_tool = mensajes + [
                {"role": "assistant", "content": response.content},
                {"role": "user", "content": tool_results}
            ]

            response2 = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=512,
                system=system_prompt,
                tools=TOOLS,
                messages=mensajes_con_tool
            )

            texto_final = ""
            for block in response2.content:
                if hasattr(block, "text"):
                    texto_final += block.text
            return texto_final.strip() if texto_final else obtener_mensaje_fallback()

        # Respuesta normal sin herramientas
        texto = ""
        for block in response.content:
            if hasattr(block, "text"):
                texto += block.text
        return texto.strip() if texto else obtener_mensaje_fallback()

    except Exception as e:
        logger.error(f"Error Claude API: {e}")
        return obtener_mensaje_error()
