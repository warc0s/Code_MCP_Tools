# Repository Guidelines

## Flujo de trabajo
- Antes de aplicar cualquier cambio, revisa el contexto relacionado y verifica manualmente los flujos afectados para detectar regresiones.

## Engineering Principles
- **Work doggedly.** Mantén autonomía mientras haya progreso; si paras, explica por qué.
- **Work smart.** Ante bugs, retrocede, considera causas y añade logging para validar supuestos.
- **Check your work.** Prueba cada bloque nuevo y, en procesos largos, revisa logs tras 30s para confirmar avance.
- **Be cautious with terminal commands.** Lanza solo comandos que terminen solos; los persistentes van con `nohup` u otro wrapper y evita scripts colgados.
- **Robustez total.** Cada solución debe contemplar explícitamente edge cases y fallos operativos; prioriza mensajes claros y defensivos ante dependencias, red o inputs inesperados.

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
- Una vez finalices la tarea que te ha encargado el usuario y se haya comprobado que es estable y valida, preguntale al usuario si debes hacer "git add ." y commit con un comentario aclaratorio de lo añadido. Tu jamás harás push, el usuario lo hace, solo debes add y commit. SIEMPRE ESPERANDO APROBACION DEL USUARIO.
- No ejecutes comandos git (add, commit, reset, revert, etc.) salvo que el usuario lo pida explícitamente.
- A la hora de añadir nuevas funciones y demas en 'utils', implementalas en el .py que consideres mas adecuado O BIEN escribe uno nuevo si ninguno se amolda a lo que vas a programar.
- Nunca te identifiques como responsable ni menciones nombres de agentes (p.ej., Codex); enfócate en describir acciones y resultados.
- La aplicación se ejecuta desde `app.py` y los imports estan en 'utils'. Respeta esto.
- Trata que los archivos no superen las dos mil lineas de codigo
