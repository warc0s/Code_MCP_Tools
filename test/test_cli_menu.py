"""
Test CLI with menus and logs for validating interactive tools.
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
        print("\nInput ended. Exiting.")
        sys.exit(0)


def option_greet() -> None:
    name = prompt_input("What is your name? ")
    if not name:
        print("Empty name, using 'anonymous'.")
        name = "anonymous"
    print(f"Hello, {name}! Thanks for helping test the CLI.")


def option_choose_color() -> None:
    colors = ["red", "green", "blue", "yellow", "orange"]
    print("Available colors:")
    for idx, color in enumerate(colors, start=1):
        print(f"{idx}) {color}")
    choice = prompt_input("Choose a color by number: ")
    try:
        idx = int(choice)
        if idx < 1 or idx > len(colors):
            raise ValueError
        color = colors[idx - 1]
        print(f"You chose: {color}")
    except Exception:
        print("Invalid selection.")


def option_logs() -> None:
    steps: List[str] = [
        "Preparing resources",
        "Connecting to services",
        "Processing data",
        "Applying transformations",
        "Generating output",
    ]
    print("Several sample logs will be generated. Wait a moment...")
    for step in steps:
        logging.info("Step: %s", step)
        time.sleep(random.uniform(0.1, 0.4))
    for idx in range(3):
        value = random.randint(1, 100)
        logging.debug("Random value %s: %s", idx, value)
    logging.warning("Test warning: this is only a test.")
    logging.error("Test error: controlled simulation.")
    print("Logs generated. Review the output to validate capture.")


def option_slow_bursty_logs() -> None:
    print("Simulating a long process with bursty logs...")
    phases: List[str] = [
        "Starting workers",
        "Collecting data",
        "Calculating metrics",
        "Sending results",
    ]
    for idx, phase in enumerate(phases, start=1):
        logging.info("Phase %s: %s", idx, phase)
        time.sleep(0.8)
        if phase == "Collecting data":
            logging.warning("Message queue growing, moderate latency.")
        if phase == "Calculating metrics":
            logging.debug("Partial batch ready. Waiting for next batch.")
            time.sleep(1.5)
        time.sleep(0.6)
    logging.info("Final post-processing in progress...")
    for _ in range(3):
        logging.debug("Heartbeat %s", random.randint(10_000, 99_999))
        time.sleep(random.uniform(0.5, 1.2))
    logging.error("Simulated failure: external dependency did not respond in time.")
    print("Long process finished with simulated errors. Review the full output.")


def option_submenu() -> None:
    while True:
        print("\n--- Flow submenu ---")
        print("a) Simulate short task")
        print("b) Simulate long task")
        print("c) Back")
        choice = prompt_input("> ")
        if choice.lower() == "a":
            print("Short task in progress...")
            time.sleep(0.5)
            print("Short task completed.")
        elif choice.lower() == "b":
            print("Long task in progress (2s)...")
            time.sleep(2.0)
            print("Long task completed.")
        elif choice.lower() == "c":
            print("Returning to main menu.")
            return
        else:
            print("Invalid option in submenu.")


def main() -> None:
    configure_logging()
    print("Interactive test CLI. Use numbers to navigate.")
    while True:
        print("\n=== Main menu ===")
        print("1) Greet")
        print("2) Choose color")
        print("3) Generate sample logs")
        print("4) Flow submenu")
        print("5) Slow process with bursty logs")
        print("q) Exit")
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
            print("Goodbye and thanks for testing.")
            break
        else:
            print("Unrecognized option. Try again.")


if __name__ == "__main__":
    main()
