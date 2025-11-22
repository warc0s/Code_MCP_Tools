# Repository Guidelines

## Flujo de trabajo
- Antes de aplicar cualquier cambio, revisa el contexto relacionado y verifica manualmente los flujos afectados para detectar regresiones.

## Engineering Principles
- **Work doggedly.** Mantén autonomía mientras haya progreso; si paras, explica por qué.
- **Work smart.** Ante bugs, retrocede, considera causas y añade logging para validar supuestos.
- **Check your work.** Prueba cada bloque nuevo y, en procesos largos, revisa logs tras 30s para confirmar avance.
- **Be cautious with terminal commands.** Lanza solo comandos que terminen solos; los persistentes van con `nohup` u otro wrapper y evita scripts colgados.
- **Robustez total.** Cada solución debe contemplar explícitamente edge cases y fallos operativos; prioriza mensajes claros y defensivos ante dependencias, red o inputs inesperados.
 - **Evita parches.** No desactives integridad referencial ni otras garantías del motor como solución rápida. Prefiere invariantes de esquema y cambios de esquema explícitos.
 - **Desarrollo sin apego a datos.** En esta fase no mantenemos compatibilidad con BDs antiguas. Si un cambio de esquema lo requiere, recrea la BD y el índice (se asume que no hay datos relevantes que conservar).
 - **Migraciones claras.** Cuando sea oportuno, añade migraciones idempotentes; mientras estemos en desarrollo, prioriza la simplicidad: recrear artefactos antes que introducir toggles o soluciones frágiles.

## Validación y pruebas
- Por cada funcionalidad nueva añade un test en `test/` que la cubra y ejecútalo con `pytest`.
- Validación dual obligatoria: además de `pytest`, lanza un navegador real vía MCP Chrome DevTools y recorre los flujos tocados (UI). No des por concluido el trabajo hasta tener verde en pruebas y verificación manual en Chrome.
- Itera hasta funcional: si algo falla en tests o en la UI, corrige y repite ciclo (code → pytest → UI con DevTools) hasta conseguir estabilidad.
- Cobertura mínima esperada: incluir al menos un test que cubra el happy path y un edge case relevante; documenta en `memory` o `doc` los pasos de verificación manual si son no triviales.
 - Si detectas un bug, captura siempre que sea posible logs y/o una screenshot en PNG: ver sección de Memoria operativa para campos y cómo guardar la imagen.

## Memoria operativa (items)
- `memory`: decisiones de diseño, invariantes, convenciones duras (naming, patrones que no se rompen), razones de arquitectura, mapas mentales breves y antipatrones detectados. Úsalo para atajos que el agente debe recordar antes de tocar código.
- `doc`: manuales o flujos largos (arquitectura, APIs, protocolos, pasos de despliegue), ejemplos reproducibles, listas de comandos; edita con `patch_doc` (diffs) para mantener historia limpia.
- `bug`: incidencias reproducibles o P0 sospechados; documenta entorno, pasos exactos y comportamiento esperado/observado; añade meta con:
  - `severity` (`high|medium|low`), `reproduction` (pasos exactos), `expected`, `root_cause`
  - opcionales: `logs_excerpt`, `fix_summary`, `fixed_in_commit`, `resolution_criteria` (lista), `screenshots` (lista de URLs), `related_files` (lista)
  - MUY recomendado añadir logs y/o una screenshot (PNG) cuando sea posible
- `todo`: tareas accionables; meta con `kind` (`bug_fix|refactor|feature|chore`), `acceptance_criteria` (lista), `dependencies` (lista), `priority` (`p0|p1|p2`). Divide si la tarea crece.
  - opcional: `related_files` (lista de rutas/URLs)

### Screenshots y logs (recomendación)
- Screenshot (PNG) local para bugs: guarda el archivo dentro del repositorio, por ejemplo en `static/uploads/bugs/<slug>.png`.
- Sirve la imagen desde la app en `http://127.0.0.1:8000/static/uploads/bugs/<slug>.png` y añade esa URL a `meta.screenshots`.
- Puedes tomar la captura con MCP Chrome DevTools (viewport) y guardarla como PNG en esa ruta; si no procede captura, adjunta al menos `logs_excerpt` y describe los pasos de reproducción.

## Coding Style & Naming Conventions
- Usa indentación de 4 espacios, snake_case y constantes en mayúsculas; mantén logs concisos.
- Añade typing y docstrings orientados; extrae helpers antes de anidar lógica.
- Configura vía YAML o entorno; evita secretos hardcodeados.

## Commit & Pull Request Guidelines
- Alinea commits con el historial: resúmenes breves en presente y en español sin puntuación final (ej. `mayor higiene`).
- Agrupa cambios cohesivos por commit, incluyendo configs o artefactos necesarios.
- Las PRs describen problema, solución, pruebas y riesgos (env vars, rebuild del índice) e involucran al owner de RAG cuando aplique.
- Si falta conectividad con el remoto, no reescribas ni enmiendes commits locales: detente y avisa al usuario antes de intentar pulls o pushes.

## Normas y recordatorios finales
- Respondes siempre en español
- Estas en un entorno conda asi que deberias ser capaz de ejecutar la aplicacion sin problemas. Si añades un nuevo import que deba usar la aplicacion, puedes instalarlo pero recuerda añadirlo al requirements.txt. Si ves que faltan demasiados paquetes, igual el usuario se olvido de activar el entorno conda antes de llamarte, puedes preguntarle en dicho caso
- Crea o edita las guias actuales (Extra/Guias/...), o bien genera nuevas si es algo demasiado diferente, con cada cambio que implementes que consideres digno de anotar
- Antes de empezar cualquier tarea, recopila toda la información disponible sobre el repositorio: revisa, lee **todas** las guías de `Extra/Guias/`, inspecciona los archivos relevantes y confirma el estado actual antes de proponer o ejecutar cambios.
- Itera siempre guiandote por las validaciones manuales y no te detengas hasta que sea completamente funcional. En caso de duda o problemas, consulta al usuario.
- Cada implementación debe ir acompañada de un test nuevo en la carpeta `test/` y no se considera lista hasta que las pruebas pasen en verde (ejecuta `pytest`)
- Una vez finalices la tarea que te ha encargado el usuario y se haya comprobado que es estable y valida, preguntale al usuario si debes hacer "git add ." y commit con un comentario aclaratorio de lo añadido. Tu jamás harás push, el usuario lo hace, solo debes add y commit. SIEMPRE ESPERANDO APROBACION DEL USUARIO.
- No ejecutes comandos git (add, commit, reset, revert, etc.) salvo que el usuario lo pida explícitamente.
- A la hora de añadir nuevas funciones y demas en 'utils', implementalas en el .py que consideres mas adecuado O BIEN escribe uno nuevo si ninguno se amolda a lo que vas a programar.
- Nunca te identifiques como responsable ni menciones nombres de agentes (p.ej., Codex); enfócate en describir acciones y resultados.
- La aplicación se ejecuta desde `app.py` y los imports estan en 'utils'. Respeta esto.
- Trata que los archivos no superen las dos mil lineas de codigo
- Cuando añadas textos visibles en la UI o comentarios en el código, escribe en inglés (los documentos de guía pueden seguir en español).
 - Soluciones robustas, no parches: no aceptes desactivar FKs para operar; si algo requiere limpieza, actualiza el esquema, recrea la BD si es necesario y valida con pruebas.
 - No ejecutes `python app.py` ni levantes la aplicación tú: asume que el usuario la tiene corriendo. Para validaciones manuales, usa MCP Chrome DevTools apuntando a la URL base sin prefijos adicionales (p. ej., `http://127.0.0.1:8000/`).
