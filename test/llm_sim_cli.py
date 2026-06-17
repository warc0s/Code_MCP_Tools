"""
CLI that simulates long/slow LLM responses for testing interactive tools.
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
        print("\nInput ended. Exiting.")
        sys.exit(0)


def _print_blocks(blocks: Iterable[str], min_delay: float, max_delay: float) -> None:
    for block in blocks:
        print(block)
        time.sleep(random.uniform(min_delay, max_delay))


def short_answer() -> None:
    paragraphs = [
        "Model: I received your question. I will give you a concise, direct summary.",
        "Short answer: the MCP tool can orchestrate flows by calling external servers and returning structured data.",
        "If you need more detail, launch the long-answer option.",
    ]
    _print_blocks(paragraphs, 0.2, 0.6)


def slow_long_answer() -> None:
    print("Generating extended response (~30s). No additional input is required...")
    long_text: List[str] = [
        "1/6 Context: this block simulates the initial phase of an LLM collecting relevant facts.",
        "2/6 Reasoning: combining sources, the model starts structuring a coherent response.",
        "3/6 Development: nuance, examples, and considerations about limits and assumptions are added.",
        "4/6 Contrast: alternatives, risks, and recommended next steps are reviewed.",
        "5/6 Drafting: the model adjusts tone, clarity, and format for human consumption.",
        "6/6 Closing: actionable recommendations and links to key references are returned.",
    ]
    _print_blocks(long_text, 4.0, 6.0)
    print("Long answer completed.")


def streaming_chunks() -> None:
    print("Sending response in fragments, as if they were tokens...")
    chunks = [
        textwrap.fill(
            "This first fragment marks the start of the output. More ideas still need to be developed.",
            width=80,
        ),
        textwrap.fill(
            "We keep building the response. The tool should allow this block to be read without the session expiring.",
            width=80,
        ),
        textwrap.fill(
            "Final fragment: the message concludes and invites new instructions if needed.",
            width=80,
        ),
    ]
    _print_blocks(chunks, 1.5, 3.0)
    print("Fragmented response completed.")


def main() -> None:
    print("LLM simulation CLI. Tune tool timeouts if you want to capture the full output.")
    while True:
        print("\n=== Main menu (LLM sim) ===")
        print("1) Short answer")
        print("2) Long slow answer (~30s)")
        print("3) Fragmented answer (streaming)")
        print("q) Exit")
        choice = prompt_input("> ")
        if choice == "1":
            short_answer()
        elif choice == "2":
            slow_long_answer()
        elif choice == "3":
            streaming_chunks()
        elif choice.lower() in {"q", "quit", "exit"}:
            print("LLM simulation ended. Thanks.")
            break
        else:
            print("Unrecognized option. Try again.")


if __name__ == "__main__":
    main()
