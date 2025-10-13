from __future__ import annotations

import os
from pathlib import Path

import duckdb

from mcp.server import run_server
from mcp.toolset import RAGToolset
from utils.config import AppConfig
from utils.embeddings import EmbeddingProvider
from utils.pipeline import rebuild_rag_from_sitemap
from utils.retrieval import Retriever
from utils.reranker import PassageReranker


def ensure_extension_directory() -> Path:
    base = Path(".duckdb/extensions")
    base.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("DUCKDB_EXTENSION_DIRECTORY", str(base.resolve()))
    return base


def rebuild_rag(config: AppConfig) -> None:
    sitemap_url = input("Introduce la URL del sitemap a indexar: ").strip()
    if not sitemap_url:
        print("No se proporcionó URL. Operación cancelada.")
        return
    ensure_extension_directory()
    embedder = EmbeddingProvider(config.embeddings)
    try:
        summary = rebuild_rag_from_sitemap(sitemap_url, config, embedder)
    except Exception as exc:
        print(f"Error reconstruyendo el RAG: {exc}")
        return
    print("")
    print("RAG reconstruido correctamente.")
    print(f"- Documentos indexados: {summary.documents}")
    print(f"- Chunks almacenados: {summary.chunks}")
    print(f"- Base de datos: {Path(config.database.path).resolve()}")


def start_server(config: AppConfig) -> None:
    db_path = Path(config.database.path)
    if not db_path.exists():
        print("La base de datos no existe. Ejecuta primero la opción 1 para construir el RAG.")
        return

    ensure_extension_directory()
    # Se instala con conexión RW y luego se sirve con conexión RO para permitir lecturas concurrentes.
    install_connection = duckdb.connect(db_path.as_posix())
    try:
        for extension in ("vss", "fts"):
            try:
                install_connection.execute(f"LOAD {extension};")
            except Exception:
                try:
                    install_connection.execute(f"INSTALL {extension};")
                    install_connection.execute(f"LOAD {extension};")
                except Exception as exc:
                    raise RuntimeError(f"No se pudo cargar la extensión {extension}: {exc}") from exc
    finally:
        install_connection.close()

    connection = duckdb.connect(db_path.as_posix(), read_only=True)
    for extension in ("vss", "fts"):
        try:
            connection.execute(f"LOAD {extension};")
        except Exception as exc:
            connection.close()
            raise RuntimeError(f"No se pudo cargar la extensión {extension} en modo lectura: {exc}") from exc

    embedder = EmbeddingProvider(config.embeddings)
    reranker = PassageReranker(config.reranker) if config.retrieval.enable_rerank else None
    retriever = Retriever(connection, config.retrieval, embedder, reranker=reranker)
    toolset = RAGToolset(
        retriever=retriever,
        force_english_queries=config.policy.force_english_queries,
    )

    default_port = "8000"
    port_input = input(f"Puerto para el servidor MCP [{default_port}]: ").strip()
    port = int(port_input) if port_input else int(default_port)
    host = "127.0.0.1"
    print(f"Iniciando servidor MCP en http://{host}:{port}")
    try:
        run_server(toolset, host=host, port=port)
    finally:
        connection.close()


def main() -> None:
    try:
        config = AppConfig.load("config.yaml")
    except Exception as exc:
        print(f"No se pudo cargar config.yaml: {exc}")
        return

    while True:
        print("")
        print("=== RAG Plug & Play ===")
        print("1) Crear/Sustituir nuevo RAG")
        print("2) Ejecutar servidor MCP")
        print("q) Salir")
        choice = input("> ").strip().lower()
        if choice == "1":
            rebuild_rag(config)
        elif choice == "2":
            try:
                start_server(config)
            except Exception as exc:
                print(f"Error al iniciar el servidor MCP: {exc}")
        elif choice in {"q", "quit", "exit"}:
            print("Hasta luego.")
            break
        else:
            print("Opción no reconocida.")


if __name__ == "__main__":
    main()
