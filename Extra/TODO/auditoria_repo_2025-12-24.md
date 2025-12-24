# Auditoría del repo `Auto_MCP_Tools` (MCP + UI) — 2025-12-24

Este documento recoge hallazgos tras revisar estructura, configuración, backend (FastAPI/MCP), frontend (JS/CSS) y tests.

## Alcance y supuestos (local-only)
- Uso **single-user** (solo tú), en **localhost**, sin exposición intencional a LAN/Internet (sin reverse proxy ni port-forward).
- Con este modelo, los apartados de “seguridad” se interpretan como:
  - **hardening opcional** (por si en el futuro se expone o para evitar sustos si se indexan páginas externas), y/o
  - **footguns** (riesgos de pegarse un tiro accidental ejecutando herramientas potentes).
- Si algún día se expone fuera de localhost (Docker publish, `APP_HOST=0.0.0.0`, túneles, etc.), conviene **re-evaluar severidades**.

## Estado rápido
- `python -m compileall -q .`: OK.
- `pytest -q`: **87 passed, 5 skipped**, 2 warnings (`PydanticDeprecatedSince20`).
- Skips (`pytest -q -rs`): 5 tests de CLI omitidos por **PTY no disponible** en este entorno.

## Resolución aplicada (local-only)
- ✅ 1.1 UI: eliminado `innerHTML` para datos dinámicos (toast/sample URLs/docs/projects); tests `test/test_ui_js_safety.py`.
- ✅ 1.2 Bind default a `127.0.0.1`; test `test/test_host_binding.py`.
- ✅ 1.3 `python_call_function` deshabilitado por defecto + allowlist + `workdir` dentro del repo; test `test/test_python_call_function.py`.
- ✅ 1.4 Validación de rutas en `python_cli_start`: `Path.is_relative_to`; test `test/test_toolset_python_cli.py`.
- ✅ 2.1/2.2 DuckDB: conexiones RO por request + evitar uso cross-thread; test `test/test_duckdb_readonly_connection.py`.
- ✅ 2.3 `/ui/api/restart` con timeout y detalle útil; test `test/test_ui_restart_endpoint.py`.
- ✅ 2.4 Rebuild url-file con validación anti-traversal; test `test/test_ui_rebuild_url_file_validation.py`.
- ✅ 3.1 Eliminado `policy.force_english_queries` (queda solo en `retrieval`); test `test/test_config_policy_removed.py`.
- ✅ 3.4 JSON Schema: `type` correlaciona `typed/meta` (y `fields.type` como hint en update); tests `test/test_toolset_schema.py`, `test/test_items_update_type_hint.py`.
- ✅ 3.5 Añadidos `requirements-lock.txt` y `requirements-dev.txt`.
- ✅ 4.1/4.2 Higiene: `.gitignore` cubre artefactos; en git solo `static/uploads/.gitkeep`.

## Hallazgos (priorizados)

### 1) Seguridad (hardening / footguns) — **BAJO en local-only (ALTO si se expone)**

#### 1.1 XSS en UI por `innerHTML` con datos no escapados
**Impacto:** ejecución de JS en el navegador del usuario si se renderiza contenido malicioso (p. ej. URLs/títulos procedentes del crawl o mensajes de error que incluyen input de usuario).

**En local-only:** normalmente es **hardening opcional** (no bloqueante) si controlas qué indexas y no abres el panel a terceros; aun así, el origen de datos incluye contenido web crawleado, así que el vector existe “por diseño” si alguna página devuelve strings raras/maliciosas.

**Evidencias (antes de corregir):**
- `static/js/core/toast.js:9` — `toast.innerHTML = ... ${message} ...` sin escape.
- `static/js/tabs/rag.js:86-87` y `static/js/tabs/dashboard.js:112-116` — se renderizan `sample_urls` con `innerHTML` y `${u}` sin escape.
- `static/js/tabs/rag.js:135-136` — tabla Docs: `doc.title` y `doc.url` en `innerHTML` sin escape.
- `static/js/tabs/config.js:63-67` — lista Projects: `p.name` (campo libre) en `innerHTML` sin escape.

**Por qué es especialmente crítico aquí:**
- `sample_urls`, `doc.title`, `doc.url` vienen de `docs` (crawled web) → **input no confiable**.
- errores del backend pueden incluir valores del usuario (slug, url, etc.) y acaban en `showToast()`.

**Mejoras recomendadas:**
- Evitar `innerHTML` para datos dinámicos: usar `textContent`/`innerText` o `escapeHtml()` sistemáticamente.
- En `showToast`, construir nodos DOM (`document.createElement('span')`) y asignar `textContent` al mensaje.
- Para enlaces (screenshots/urls), aplicar allowlist (`http/https`) y, si no pasa, renderizar como texto.
- Opcional “cinturón y tirantes”: añadir cabecera CSP (p. ej. `default-src 'self'`) y eliminar inline handlers (`onclick="..."`) para poder endurecer CSP.

**Estado:** ✅ Resuelto. Se eliminaron los usos de `innerHTML` con datos dinámicos en `static/js/core/toast.js`, `static/js/tabs/rag.js`, `static/js/tabs/dashboard.js` y `static/js/tabs/config.js` (regresión cubierta por `test/test_ui_js_safety.py`).

#### 1.2 Servidor sin autenticación + bind por defecto a `0.0.0.0`
**Impacto:** si se ejecuta en una máquina accesible por red (LAN/WiFi/VPS), cualquiera podría:
- invocar tools MCP (incluidas de ejecución de Python),
- operar sobre la UI,
- disparar crawls/rebuilds (consumo y/o SSRF),
- borrar proyectos/items.

**En local-only:** si realmente sólo lo usas tú en localhost, esto es **riesgo bajo** (más bien prevención ante exposición accidental).

**Evidencia:**
- `app.py:272-277` — `_resolve_host_binding()` usa `0.0.0.0` por defecto.

**Mejoras recomendadas:**
- Cambiar el default a `127.0.0.1` (y usar `APP_HOST=0.0.0.0` explícitamente en Docker).
- Añadir una auth simple (token por cabecera) para endpoints UI y MCP cuando `APP_HOST` no sea loopback.
- Documentar de forma muy visible en README el riesgo si se expone fuera de localhost.

**Estado:** ✅ Resuelto. El binding por defecto pasa a `127.0.0.1` (con override explícito para Docker/entornos que lo requieran); cubierto por `test/test_host_binding.py`.

#### 1.3 `python_call_function`: ejecución arbitraria de código (RCE) y no impone “solo repo”
**Impacto:** permite importar cualquier módulo accesible por el intérprete y ejecutar cualquier callable con `args/kwargs`, además de permitir `workdir` arbitrario → superficie de RCE muy alta si el servidor se expone.

**En local-only:** más que “ataque”, es un **footgun** potente: una llamada mal planteada puede ejecutar código no deseado o apuntar a `workdir` inesperado. Si confías en tus propios flujos/agentes, puede valer; si quieres reducir sustos, conviene limitarlo.

**Evidencias:**
- `mcp_server/toolset.py:271-287` — tool expuesta en schema.
- `utils/call_function.py:26-51` — ejecuta `python -m utils.function_runner` con payload (incluye `workdir` sin validación de “dentro del repo”).
- `utils/function_runner.py:68-76` — `importlib.import_module(module_name)` + `getattr` + ejecución directa.

**Mejoras recomendadas:**
- Deshabilitarla por defecto en `config.yaml` (solo habilitar explícitamente).
- Restringir `module` a prefijos allowlist (p. ej. `utils.*`, `scripts.*`).
- Validar `workdir` para que sea relativo y dentro del repo (misma política que `python_cli_start`).
- Considerar ejecutar con entorno “capado” (env minimal) o en un subproceso con restricciones adicionales.

**Estado:** ✅ Resuelto. `python_call_function` está deshabilitada por defecto, con allowlist de módulos y `workdir` validado dentro del repo; cubierto por `test/test_python_call_function.py`.

#### 1.4 Validación de rutas en `python_cli_start` vulnerable por uso de `startswith`
**Impacto:** el check actual permite bypass por “prefix confusion” (p. ej. `../Auto_MCP_Tools_evil` comparte prefijo de string con el repo). En combinación con `python_cli_start` podría ejecutarse un script fuera del repo.

**En local-only:** sigue siendo un bug real (validación incorrecta) y un **footgun** si se acaba pasando un `workdir/script_path` raro.

**Evidencia:**
- `mcp_server/toolset.py:533-546` — `str(path).startswith(str(repo_root))` para `workdir` y `script`.

**Mejoras recomendadas:**
- Usar `Path.is_relative_to()` (Py3.9+) o `os.path.commonpath` para validar pertenencia real al repo:
  - `workdir_abs.is_relative_to(repo_root)`
  - `candidate.is_relative_to(repo_root)`

**Estado:** ✅ Resuelto. La validación de rutas ya no usa `startswith` y pasa a checks de `Path.is_relative_to` (con fallback); cubierto por `test/test_toolset_python_cli.py`.

---

### 2) Robustez / Concurrencia — **MEDIO**

#### 2.1 Posible uso cross-thread de la conexión DuckDB por `asyncio.to_thread`
**Impacto:** DuckDB (y otras DBs) suelen no ser seguras si una conexión se usa desde distintos hilos. Hay varios puntos donde se pasa una conexión a otro hilo o se crea en un hilo y se usa en otro.

**Evidencias:**
- `app.py:293-297` — `refresh_retriever()` crea `connection` en un thread y la guarda en `state.connection`.
- `app.py:497` — `api_status()` llama a `_get_db_overview` en thread pasando `state.connection`.

**Mejoras recomendadas:**
- Evitar pasar conexiones entre hilos; abrir conexión “local” dentro del thread que la usa (para overview/status).
- Alternativa: proteger el uso de DuckDB con un lock y mantener todas las llamadas de DB en el mismo contexto (o abrir conexiones por request).

**Estado:** ✅ Resuelto. Se evita compartir conexiones DuckDB entre hilos y el servidor usa conexiones RO por request donde aplica; cubierto por `test/test_duckdb_readonly_connection.py`.

#### 2.2 Inconsistencia “read-only” vs `read_only=False`
**Impacto:** discrepancia entre documentación y realidad del runtime; además `_open_ro_connection()` induce a error.

**Evidencia:**
- `app.py:91-103` — `_open_ro_connection()` usa `duckdb.connect(..., read_only=False)`.

**Mejoras recomendadas:**
- Si se pretende RO: usar `read_only=True` y separar el paso de `INSTALL/LOAD` (que requiere RW).
- Si se pretende RW: renombrar helper y actualizar guía (`Extra/Guias/rag_mcp.md`) para no afirmar “solo lectura”.

**Estado:** ✅ Resuelto. El servidor abre DuckDB en `read_only=True` para operaciones de lectura y separa el paso RW necesario para extensiones; cubierto por `test/test_duckdb_readonly_connection.py`.

#### 2.3 `POST /ui/api/restart` sin timeout y sin devolver detalle útil
**Impacto:** `docker restart` podría colgar o tardar mucho; en error no se retorna `stderr` al usuario (solo log).

**Evidencia:**
- `app.py:887-907` — `subprocess.run([...], check=True)` sin `timeout=...`.

**Mejoras recomendadas:**
- Añadir `timeout` y propagar parte de `stderr` en el `detail` cuando falle (redactado si hiciera falta).

**Estado:** ✅ Resuelto. Endpoint con timeout configurable y devuelve detalle útil (stderr/stdout truncado) en caso de error; cubierto por `test/test_ui_restart_endpoint.py`.

#### 2.4 `rebuild/url-file`: validación de filename sin “anti traversal”
**Impacto:** permite `../...` (si existe un fichero) y leerlo como lista de URLs. No exfiltra contenido directamente, pero es una superficie extra.

**Evidencia:**
- `app.py:451-476` — `path = Path("txt") / filename` + `.is_file()` sin `resolve()` + `is_relative_to`.

**Mejoras recomendadas:**
- Rechazar `filename` con separadores (`/`, `\\`) o usar `resolve()` + `is_relative_to(Path("txt").resolve())`.

**Estado:** ✅ Resuelto. Se valida el filename con resolución y pertenencia real a `txt/` antes de leer; cubierto por `test/test_ui_rebuild_url_file_validation.py`.

---

### 3) Diseño / Config / DX — **MEDIO / BAJO**

#### 3.1 `policy.force_english_queries` no se usa
**Impacto:** duplicidad/confusión: el enforcement real está en `RetrievalConfig.force_english_queries`.

**Evidencia (antes de corregir):**
- `utils/config.py:112-114` (PolicyConfig) y `config.yaml:50` están presentes pero no hay uso en el código (`rg force_english_queries` solo toca retrieval).

**Mejoras recomendadas:**
- Eliminar `policy` si no aporta valor, o hacer que `Retriever` lea policy (y quitar el duplicado de retrieval).

**Estado:** ✅ Resuelto. Se elimina `policy` de `utils/config.py` y `config.yaml`; queda un único flag `retrieval.force_english_queries` (cubierto por `test/test_config_policy_removed.py`).

#### 3.2 Flags de chunking declarados pero no aplicados
**Impacto:** `chunking.preserve_code_blocks` y `chunking.respect_headings` existen pero no cambian el comportamiento, lo que induce a error al ajustar config.

**Evidencia:**
- `utils/config.py:76-77` y `config.yaml:27-28`, pero `utils/chunking.py` no consulta esos flags.

**Mejoras recomendadas:**
- Implementar el comportamiento condicionado, o retirar los flags para evitar falsa sensación de control.

**Estado:** ✅ Resuelto. Los flags `chunking.preserve_code_blocks` y `chunking.respect_headings` afectan al chunking real; cubierto por `test/test_chunking_flags.py`.

#### 3.3 Pipeline: `EmbeddingProvider` default ignora `config.main.mode` cuando `embedder` es `None`
**Impacto:** si en el futuro se llama `rebuild_rag_from_*` sin pasar `embedder`, se usará modo `local` aunque el config sea `cloud`.

**Evidencia:**
- `utils/pipeline.py:202` y `utils/pipeline.py:213` — `EmbeddingProvider(config.embeddings)` sin `mode=config.main.mode`.

**Mejora recomendada:**
- `EmbeddingProvider(config.embeddings, mode=config.main.mode)` en ambos helpers.

**Estado:** ✅ Resuelto. El pipeline respeta `config.main.mode` al crear el embedder por defecto; cubierto por `test/test_pipeline_embedder_mode.py`.

#### 3.4 JSON Schema de `typed`/`meta` no correlaciona con `type`
**Impacto:** clientes pueden construir payload “válido” por schema (oneOf) pero incompatible con el `type` real; fallará luego por validación backend. No es bug funcional, pero empeora UX de integradores.

**Evidencia:**
- `utils/item_meta.py:118-173` (oneOf), consumido por `mcp_server/toolset.py` en `store_item/update_item`.

**Mejoras recomendadas:**
- Si se quiere afinar: usar `if/then/else` en JSON Schema para atar `type` → `typed/meta`.

**Estado:** ✅ Resuelto. `store_item` correlaciona `type` → `typed/meta` en su schema y `update_item` soporta `fields.type` como hint (además, el backend rechaza mismatches); cubierto por `test/test_toolset_schema.py` y `test/test_items_update_type_hint.py`.

#### 3.5 Dependencias sin lock y `requirements.txt` poco reproducible
**Impacto:** builds no deterministas (especialmente `transformers`, `sentence-transformers`, `crawl4ai`). Torch está pinneado, el resto no.

**Mejoras recomendadas:**
- Pin de versiones o `requirements-lock.txt` (y opcional `requirements-dev.txt` con `pytest`).

**Estado:** ✅ Resuelto. Se añadió `requirements-lock.txt` (freeze del entorno) y `requirements-dev.txt` con dependencias de test.

---

### 4) Higiene del repo — **BAJO**

#### 4.1 Artefactos locales presentes en el working tree
**Observación:** existen carpetas como `__pycache__/`, `.pytest_cache/`, `.cache/`, `.duckdb/`, `data/` y logs (`app.log`, `app_ui.log`).
- La mayoría están cubiertas por `.gitignore`, pero conviene revisar que no se estén versionando accidentalmente.

**Estado:** ✅ Confirmado. No se detectan artefactos de runtime versionados (más allá de los ficheros intencionales del repo).

#### 4.2 `static/uploads/bugs/*.png` aparece aunque `static/uploads/*` está ignorado
**Observación:** el repo lista imágenes en `static/uploads/bugs/` pese al ignore; si están trackeadas, no las ignorará.

**Mejora recomendada:** confirmar que sólo quede `static/uploads/.gitkeep` versionado.

**Estado:** ✅ Confirmado. En git sólo está `static/uploads/.gitkeep`; las capturas `.png` permanecen ignoradas.

---

## Tests y warnings (detalle)
- `pytest -q -rs`:
  - Skipped:
    - `test/test_cli_repl_prompt.py:21` — PTY no disponible.
    - `test/test_cli_ring_buffer.py:23` — PTY no disponible (2 tests).
    - `test/test_cli_stdin_preinject.py:21` — PTY no disponible.
    - `test/test_cli_timeouts.py:21` — PTY no disponible.
  - Warnings:
    - `PydanticDeprecatedSince20` (`pydantic/_internal/_config.py:323`), típico de dependencias que aún usan config “class-based”.
