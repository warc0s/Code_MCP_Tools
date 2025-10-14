from __future__ import annotations

import os
from pathlib import Path

import duckdb

from mcp.server import run_server
from mcp.toolset import RAGToolset
from utils.config import AppConfig
from utils.database import read_metadata
from utils.embeddings import DEFAULT_CLOUD_EMBED_MODEL, EmbeddingProvider
from utils.env import load_env_file
from utils.pipeline import rebuild_rag_from_sitemap
from utils.retrieval import Retriever
from utils.reranker import CLOUD_RERANKER_MODEL, PassageReranker


def ensure_extension_directory() -> Path:
    base = Path(".duckdb/extensions")
    base.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("DUCKDB_EXTENSION_DIRECTORY", str(base.resolve()))
    return base


def resolve_model_names(config: AppConfig) -> dict[str, str]:
    mode = config.main.mode
    embedding_model = (
        config.embeddings.model_name
        if mode == "local"
        else config.embeddings.cloud_model_name or DEFAULT_CLOUD_EMBED_MODEL
    )
    reranker_model = (
        config.reranker.model_name
        if mode == "local"
        else config.reranker.cloud_model_name or CLOUD_RERANKER_MODEL
    )
    return {"embedding": embedding_model, "reranker": reranker_model}


def rebuild_rag(config: AppConfig) -> None:
    sitemap_url = input("Introduce la URL del sitemap a indexar: ").strip()
    if not sitemap_url:
        print("No se proporcionó URL. Operación cancelada.")
        return
    ensure_extension_directory()
    embedder = EmbeddingProvider(config.embeddings, mode=config.main.mode)
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
    models = resolve_model_names(config)
    print(f"- Modo de ingestión: {config.main.mode}")
    print(f"- Embeddings utilizados: {models['embedding']}")


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

    metadata = read_metadata(connection)
    current_models = resolve_model_names(config)
    stored_mode = metadata.get("runtime_mode")
    stored_dim = metadata.get("embedding_dim")

    if stored_mode and stored_mode != config.main.mode:
        print("")
        print("Advertencia: la base de datos se generó en un modo distinto al configurado actualmente.")
        print(f"- Modo en BD: {stored_mode}")
        print(f"- Modo actual: {config.main.mode}")
        stored_embed = metadata.get("embedding_model_name")
        stored_reranker = metadata.get("reranker_model_name")
        print(f"- Embeddings actuales: {current_models['embedding']}")
        if stored_embed:
            print(f"- Embeddings en BD: {stored_embed}")
        if stored_dim:
            print(f"- Dimensión embeddings en BD: {stored_dim}")
        configured_dim = config.embeddings.embedding_dim
        if configured_dim:
            print(f"- Dimensión configurada actual: {configured_dim}")
        else:
            print("- Dimensión configurada actual: desconocida (se resolverá al generar embeddings)")
        print(f"- Reranker actual: {current_models['reranker']}")
        if stored_reranker:
            print(f"- Reranker en BD: {stored_reranker}")
        answer = input("Las dimensiones podrían no coincidir. ¿Deseas continuar? [s/N]: ").strip().lower()
        if answer not in {"s", "si", "sí", "y", "yes"}:
            print("Operación cancelada.")
            connection.close()
            return

    embedder = EmbeddingProvider(config.embeddings, mode=config.main.mode)
    reranker = (
        PassageReranker(config.reranker, mode=config.main.mode)
        if config.retrieval.enable_rerank
        else None
    )
    retriever = Retriever(connection, config.retrieval, embedder, reranker=reranker)
    toolset = RAGToolset(
        retriever=retriever,
        force_english_queries=config.policy.force_english_queries,
    )

    default_port = "8000"
    print(
        f"Modo de operación: {config.main.mode} | "
        f"Embeddings: {current_models['embedding']} | "
        f"Reranker: {current_models['reranker']}"
    )
    port_input = input(f"Puerto para el servidor MCP [{default_port}]: ").strip()
    port = int(port_input) if port_input else int(default_port)
    host = "127.0.0.1"
    print(f"Iniciando servidor MCP en http://{host}:{port}")
    try:
        run_server(toolset, host=host, port=port)
    finally:
        connection.close()


def main() -> None:
    load_env_file()
    try:
        config = AppConfig.load("config.yaml")
    except Exception as exc:
        print(f"No se pudo cargar config.yaml: {exc}")
        return

    while True:
        print("")
        print("=== RAG Plug & Play ===")
        models = resolve_model_names(config)
        print(f"Modo actual: {config.main.mode}")
        print(f"Embeddings en uso: {models['embedding']}")
        print(f"Reranker en uso: {models['reranker']}")
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
