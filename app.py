from __future__ import annotations

import os
from pathlib import Path
import warnings

import duckdb

from rag_mcp.server import DEFAULT_HTTP_PATH, build_server, run_server
from pydantic.warnings import PydanticDeprecatedSince20

# Filtra el warning de Pydantic generado por crawl4ai (Config en BaseModel).
warnings.filterwarnings(
    "ignore",
    category=PydanticDeprecatedSince20,
    module="pydantic._internal._config",
)
from utils.config import AppConfig
from utils.database import read_metadata
from utils.embeddings import DEFAULT_CLOUD_EMBED_MODEL, EmbeddingProvider
from utils.env import load_env_file
from utils.pipeline import rebuild_rag_from_sitemap, rebuild_rag_from_urls
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


def rebuild_rag_from_file(config: AppConfig) -> None:
    txt_dir = Path("txt")
    txt_dir.mkdir(parents=True, exist_ok=True)
    txt_files = sorted(p for p in txt_dir.glob("*.txt") if p.is_file())
    if not txt_files:
        print("No se encontraron ficheros .txt en la carpeta 'txt'.")
        print("Crea un fichero con una URL por línea dentro de 'txt/' y vuelve a intentarlo.")
        return
    print("Ficheros de URLs disponibles en 'txt/':")
    for idx, path in enumerate(txt_files, start=1):
        print(f"{idx}) {path.name}")
    choice = input("Selecciona el fichero de URLs (número) o pulsa Enter para cancelar: ").strip()
    if not choice:
        print("Operación cancelada.")
        return
    try:
        index = int(choice)
    except ValueError:
        print("Selección no válida. Operación cancelada.")
        return
    if index < 1 or index > len(txt_files):
        print("Selección fuera de rango. Operación cancelada.")
        return
    path = txt_files[index - 1]
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as exc:
        print(f"No se pudo leer el fichero de URLs: {exc}")
        return
    urls: list[str] = []
    for line in content.splitlines():
        candidate = line.strip()
        if not candidate or candidate.startswith("#"):
            continue
        urls.append(candidate)
    if not urls:
        print("El fichero no contiene URLs válidas. Operación cancelada.")
        return
    ensure_extension_directory()
    embedder = EmbeddingProvider(config.embeddings, mode=config.main.mode)
    try:
        summary = rebuild_rag_from_urls(urls, config, embedder)
    except Exception as exc:
        print(f"Error reconstruyendo el RAG desde fichero de URLs: {exc}")
        return
    print("")
    print("RAG reconstruido correctamente desde fichero de URLs.")
    print(f"- Documentos indexados: {summary.documents}")
    print(f"- Chunks almacenados: {summary.chunks}")
    print(f"- Base de datos: {Path(config.database.path).resolve()}")
    models = resolve_model_names(config)
    print(f"- Modo de ingestión: {config.main.mode}")
    print(f"- Embeddings utilizados: {models['embedding']}")


def describe_current_database(config: AppConfig) -> None:
    db_path = Path(config.database.path)
    if not db_path.exists():
        print("BD actual: no existe todavía. Ejecuta una opción 1.x para construirla.")
        return
    try:
        connection = duckdb.connect(db_path.as_posix(), read_only=True)
    except Exception as exc:
        print(f"BD actual: no se pudo abrir {db_path}: {exc}")
        return
    try:
        try:
            row = connection.execute("SELECT COUNT(*) FROM docs;").fetchone()
            docs_count = int(row[0]) if row else 0
        except Exception:
            print(f"BD actual: {db_path} (estructura desconocida, tabla 'docs' no encontrada)")
            return
        urls: list[str] = []
        try:
            rows = connection.execute(
                "SELECT url FROM docs ORDER BY created_at ASC LIMIT 3;"
            ).fetchall()
            urls = [r[0] for r in rows if r and r[0]]
        except Exception:
            urls = []
        print(f"BD actual: {db_path} | documentos: {docs_count}")
        if urls:
            print("- URLs de referencia:")
            for url in urls:
                print(f"  · {url}")
    finally:
        connection.close()


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
    enabled_tools = None
    tools_config = getattr(config, "mcp", None)
    if tools_config and tools_config.tools:
        enabled_tools = [name for name, enabled in tools_config.tools.items() if enabled]
    server = build_server(
        retriever=retriever,
        enabled_tools=enabled_tools,
    )

    http_path = os.getenv("MCP_HTTP_PATH", DEFAULT_HTTP_PATH)
    if not http_path.startswith("/"):
        http_path = f"/{http_path}"

    default_port = "8001"
    print(
        f"Modo de operación: {config.main.mode} | "
        f"Embeddings: {current_models['embedding']} | "
        f"Reranker: {current_models['reranker']}"
    )
    port_input = input(f"Puerto para el servidor MCP [{default_port}]: ").strip()
    port = int(port_input) if port_input else int(default_port)
    host = "127.0.0.1"
    print(f"Iniciando servidor MCP en http://{host}:{port}{http_path}")
    try:
        run_server(server, host=host, port=port, path=http_path)
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
        describe_current_database(config)
        models = resolve_model_names(config)
        print(f"Modo actual: {config.main.mode}")
        print(f"Embeddings en uso: {models['embedding']}")
        print(f"Reranker en uso: {models['reranker']}")
        print("1) Crear/Sustituir RAG")
        print("   1.1) Desde sitemap")
        print("   1.2) Desde fichero de URLs (carpeta txt/)")
        print("   AVISO: cualquier opción 1.x eliminará y recreará la base de datos actual.")
        print("2) Ejecutar servidor MCP")
        print("q) Salir")
        choice = input("> ").strip().lower()
        if choice == "1":
            while True:
                subchoice = input("Elige 1.1 (sitemap), 1.2 (txt) o q para volver: ").strip().lower()
                if subchoice in {"1.1", "11", "s", "sitemap"}:
                    rebuild_rag(config)
                    break
                if subchoice in {"1.2", "12", "t", "txt"}:
                    rebuild_rag_from_file(config)
                    break
                if subchoice in {"q", "quit", "exit"}:
                    print("Volviendo al menú principal.")
                    break
                print("Opción de submenú no reconocida.")
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
