"""
CLI que simula respuestas largas/lentas de un LLM para probar tools interactivas.
"""

from __future__ import annotations

import random
import sys
import textwrap
import time
from typing import Iterable, List


def prompt_input(message: str) -> str:
    try:
        return input(message).strip()
    except EOFError:
        print("\nEntrada terminada. Saliendo.")
        sys.exit(0)


def _print_blocks(blocks: Iterable[str], min_delay: float, max_delay: float) -> None:
    for block in blocks:
        print(block)
        time.sleep(random.uniform(min_delay, max_delay))


def short_answer() -> None:
    paragraphs = [
        "Modelo: he recibido tu pregunta. Voy a darte un resumen conciso y directo.",
        "Respuesta breve: la herramienta MCP permite orquestar flujos llamando a servers externos y devolviendo datos estructurados.",
        "Si necesitas más detalle, lanza la opción de respuesta larga.",
    ]
    _print_blocks(paragraphs, 0.2, 0.6)


def slow_long_answer() -> None:
    print("Generando respuesta extensa (~30s). No se requiere input adicional...")
    long_text: List[str] = [
        "1/6 Contexto: este bloque simula la fase inicial de un LLM que recopila hechos relevantes.",
        "2/6 Razonamiento: combinando las fuentes, el modelo empieza a estructurar una respuesta coherente.",
        "3/6 Desarrollo: se añaden matices, ejemplos y consideraciones sobre limitaciones y supuestos.",
        "4/6 Contrastando: se revisan alternativas, riesgos y pasos siguientes recomendados.",
        "5/6 Redacción: el modelo ajusta tono, claridad y formato para consumo humano.",
        "6/6 Cierre: se devuelven recomendaciones accionables y enlaces a referencias clave.",
    ]
    _print_blocks(long_text, 4.0, 6.0)
    print("Respuesta larga completada.")


def streaming_chunks() -> None:
    print("Enviando respuesta en fragmentos, como si fueran tokens...")
    chunks = [
        textwrap.fill(
            "Este primer fragmento marca el arranque de la salida. Todavía faltan más ideas por desarrollar.",
            width=80,
        ),
        textwrap.fill(
            "Seguimos construyendo la respuesta. La herramienta debería permitir leer este bloque sin que la sesión expire.",
            width=80,
        ),
        textwrap.fill(
            "Último fragmento: se concluye el mensaje y se invita a enviar nuevas instrucciones si hace falta.",
            width=80,
        ),
    ]
    _print_blocks(chunks, 1.5, 3.0)
    print("Respuesta fragmentada completada.")


def main() -> None:
    print("CLI de simulación LLM. Ajusta los timeouts de la tool si quieres capturar toda la salida.")
    while True:
        print("\n=== Menú principal (LLM sim) ===")
        print("1) Respuesta corta")
        print("2) Respuesta larga y lenta (~30s)")
        print("3) Respuesta en fragmentos (streaming)")
        print("q) Salir")
        choice = prompt_input("> ")
        if choice == "1":
            short_answer()
        elif choice == "2":
            slow_long_answer()
        elif choice == "3":
            streaming_chunks()
        elif choice.lower() in {"q", "quit", "exit"}:
            print("Fin de la simulación LLM. Gracias.")
            break
        else:
            print("Opción no reconocida. Intenta de nuevo.")


if __name__ == "__main__":
    main()
