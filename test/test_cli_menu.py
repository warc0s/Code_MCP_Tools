"""
CLI de prueba con menús y logs para validar tools interactivas.
"""

from __future__ import annotations

import logging
import random
import sys
import time
from typing import List


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def prompt_input(message: str) -> str:
    try:
        return input(message).strip()
    except EOFError:
        print("\nEntrada terminada. Saliendo.")
        sys.exit(0)


def option_greet() -> None:
    name = prompt_input("¿Cómo te llamas? ")
    if not name:
        print("Nombre vacío, usando 'anónimo'.")
        name = "anónimo"
    print(f"Hola, {name}! Gracias por ayudar a probar la CLI.")


def option_choose_color() -> None:
    colors = ["rojo", "verde", "azul", "amarillo", "naranja"]
    print("Colores disponibles:")
    for idx, color in enumerate(colors, start=1):
        print(f"{idx}) {color}")
    choice = prompt_input("Elige un color por número: ")
    try:
        idx = int(choice)
        if idx < 1 or idx > len(colors):
            raise ValueError
        color = colors[idx - 1]
        print(f"Elegiste: {color}")
    except Exception:
        print("Selección inválida.")


def option_logs() -> None:
    steps: List[str] = [
        "Preparando recursos",
        "Conectando con servicios",
        "Procesando datos",
        "Aplicando transformaciones",
        "Generando salida",
    ]
    print("Se generarán varios logs de ejemplo. Espera un momento...")
    for step in steps:
        logging.info("Paso: %s", step)
        time.sleep(random.uniform(0.1, 0.4))
    for idx in range(3):
        value = random.randint(1, 100)
        logging.debug("Valor aleatorio %s: %s", idx, value)
    logging.warning("Advertencia de prueba: esto es solo un test.")
    logging.error("Error de prueba: simulación controlada.")
    print("Logs generados. Revisa la salida para validar captura.")


def option_slow_bursty_logs() -> None:
    print("Simulando proceso largo con logs a trompicones...")
    phases: List[str] = [
        "Arrancando workers",
        "Recopilando datos",
        "Calculando métricas",
        "Enviando resultados",
    ]
    for idx, phase in enumerate(phases, start=1):
        logging.info("Fase %s: %s", idx, phase)
        time.sleep(0.8)
        if phase == "Recopilando datos":
            logging.warning("Cola de mensajes creciendo, latencia moderada.")
        if phase == "Calculando métricas":
            logging.debug("Batch parcial listo. Esperando siguiente lote.")
            time.sleep(1.5)
        time.sleep(0.6)
    logging.info("Postprocesado final en curso...")
    for _ in range(3):
        logging.debug("Pulso de vida %s", random.randint(10_000, 99_999))
        time.sleep(random.uniform(0.5, 1.2))
    logging.error("Fallo simulado: dependencia externa no respondió a tiempo.")
    print("Proceso largo finalizado con errores simulados. Revisa la salida completa.")


def option_submenu() -> None:
    while True:
        print("\n--- Submenú de flujo ---")
        print("a) Simular tarea corta")
        print("b) Simular tarea larga")
        print("c) Volver")
        choice = prompt_input("> ")
        if choice.lower() == "a":
            print("Tarea corta en progreso...")
            time.sleep(0.5)
            print("Tarea corta completada.")
        elif choice.lower() == "b":
            print("Tarea larga en progreso (2s)...")
            time.sleep(2.0)
            print("Tarea larga completada.")
        elif choice.lower() == "c":
            print("Regresando al menú principal.")
            return
        else:
            print("Opción no válida en submenú.")


def main() -> None:
    configure_logging()
    print("CLI de prueba interactiva. Usa números para navegar.")
    while True:
        print("\n=== Menú principal ===")
        print("1) Saludar")
        print("2) Elegir color")
        print("3) Generar logs de ejemplo")
        print("4) Submenú de flujo")
        print("5) Proceso lento con logs a trompicones")
        print("q) Salir")
        choice = prompt_input("> ")
        if choice == "1":
            option_greet()
        elif choice == "2":
            option_choose_color()
        elif choice == "3":
            option_logs()
        elif choice == "4":
            option_submenu()
        elif choice == "5":
            option_slow_bursty_logs()
        elif choice.lower() in {"q", "quit", "exit"}:
            print("Hasta luego y gracias por probar.")
            break
        else:
            print("Opción no reconocida. Intenta de nuevo.")


if __name__ == "__main__":
    main()
