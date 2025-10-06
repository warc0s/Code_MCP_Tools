# Guía operativa para desarrollar con AI Refinery SDK

## 1. Instalación y requisitos

* Requisitos de sistema: Python 3.12 o superior y `pip`. 
* Instalación del SDK desde PyPI:

  ```bash
  pip install airefinery-sdk
  ```

  Esta orden figura en el registro de versiones legado. 

> El documento recomienda entornos virtuales y muestra cómo crearlos y desactivarlos, pero la activación aparece incompleta. Comandos válidos presentes:
> creación `python3 -m venv venv` y salida `deactivate`. La activación por plataforma no se detalla en el texto. 

---

## 2. Credenciales y autenticación

1. Genera tu API key en el portal de AI Refinery. Pasos documentados: iniciar sesión con Entra ID, ir a “API Key Management” y pulsar “Generate New API Key”. El valor se muestra una sola vez, guárdalo de forma segura. 

2. Crea un fichero `.env` con tu clave:

```env
API_KEY=<your_api_key>
```



3. Carga la clave y crea clientes del SDK:

```python
import os
from dotenv import load_dotenv
from air import AsyncAIRefinery, DistillerClient  # módulo y clases según doc

load_dotenv()
api_key = str(os.getenv("API_KEY"))

# Cliente unificado asincrónico
client = AsyncAIRefinery(api_key=api_key)

# Cliente Distiller (multiagente)
distiller_client = DistillerClient(api_key=api_key)
```



---

## 3. Esquema de configuración de proyectos (YAML)

La configuración de un proyecto Distiller se define en un YAML con secciones raíz: `base_config`, `utility_agents`, `super_agents`, `orchestrator`, `memory_config`. Todo lo no marcado como “Required” es opcional y hereda valores por defecto. 

### 3.1 `base_config`

```yaml
base_config:
  llm_config:
    model: <modelo LLM del catálogo>        # por defecto "meta-llama/Llama-3.1-70B-Instruct"
    temperature: <float>                    # por defecto 0.5
    top_p: <float>                          # por defecto 1
    max_tokens: <int>                       # por defecto 2048

  vlm_config:
    model: <modelo VLM del catálogo>        # por defecto "meta-llama/Llama-3.2-90B-Vision-Instruct"
    temperature: <float>                    # por defecto 0.5
    top_p: <float>                          # por defecto 1
    max_tokens: <int>                       # por defecto 2048

  reranker_config:
    model: "<reranker del catálogo>"        # por defecto "nvidia/llama-3.2-nv-rerankqa-1b-v2"

  compression_config:
    model: "<modelo de compresión>"         # por defecto "llmlingua/bert"

  embedding_config:
    model: "Qwen/Qwen3-Embedding-0.6B"      # valor por defecto indicado
```



### 3.2 `utility_agents`

Lista **obligatoria** con agentes disponibles, tanto integrados como personalizados. La clave `agent_class` determina el tipo. Para `CustomAgent`, el `agent_name` debe existir como clave en `executor_dict` en el código Python. 

Ejemplo genérico con dos agentes:

```yaml
utility_agents:
  - agent_class: CustomAgent                  # para agentes definidos por ti
    agent_name: "CustomAgentName"
    agent_description: "Descripción opcional"
    config: {}                                # parámetros arbitrarios para pasar a tu función
  - agent_class: SearchAgent                  # ejemplo de integrado
    agent_name: "SearchAgent"
    agent_description: "..."
    config: {}
```



### 3.3 `super_agents`

Para orquestación avanzada de tareas complejas. Se listan por nombre e incluyen configuración opcional y, si aplica, objetivos o requisitos previos.

```yaml
super_agents:
  - agent_class: SuperAgent
    agent_name: "MySupervisor"
    requirements:
      - <Task 1>
      - <Task 2>
    llm_config:
      model: <model_name>
```



### 3.4 `orchestrator`

Sección **obligatoria**. Lista de agentes accesibles por el orquestador y parámetros opcionales de enrutado y descomposición.

```yaml
orchestrator:
  agent_list:
    - agent_name: "CustomAgentName"           # debe existir en utility_agents
    - agent_name: "SearchAgent"
  enable_routing: true                        # opcional, por defecto true
  decompose: true                             # opcional, por defecto true
  rai_config: null                            # opcional
  config: null                                # opcional, pasa al agente de reserva
```



### 3.5 `memory_config`

Módulos de memoria opcionales para chat e variables de entorno.

```yaml
memory_config:
  memory_modules:
    - memory_name: chat_history
      memory_class: ChatMemoryModule
      kwargs:
        n_rounds: <int>
    - memory_name: env_variable
      memory_class: VariableMemoryModule
      kwargs:
        variables:
          <ENV_KEY_1>: <value>
          <ENV_KEY_2>: <value>
```



---

## 4. Creación del proyecto y conexión

### 4.1 Registro del proyecto en el servicio

Dos alternativas documentadas.

* Con `DistillerClient` síncrono:

  ```python
  from air import DistillerClient
  client = DistillerClient(api_key=api_key)
  client.create_project(config_path="example.yaml", project="example")
  ```



* Con `AsyncAIRefinery` vía `client.distiller.create_project` (síncrono):

  ```python
  from air import AsyncAIRefinery
  client = AsyncAIRefinery(api_key=api_key)
  client.distiller.create_project(config_path="example.yaml", project="example")
  ```

  Versionado automático a partir de la versión 0; por omisión se conecta a la última versión. 

> Cuando se crea el proyecto, la configuración queda almacenada en la nube de AI Refinery, con control de versiones. 

### 4.2 Conexión y consulta en sesión asíncrona

Patrón con **context manager**:

```python
from air import DistillerClient
client = DistillerClient(api_key=api_key)

executor_dict = {"Custom Agent Example": your_custom_agent}

import asyncio

async def run_query():
    async with client(
        project="example",
        uuid="test_user",
        executor_dict=executor_dict
    ) as dc:
        responses = await dc.query(query="hi")
        async for response in responses:
            print(response["content"])

asyncio.run(run_query())
```

El nombre del proyecto y `uuid` admiten letras, dígitos, guiones y guiones bajos. 

> Recomendación del doc: una vez creado el proyecto, no vuelvas a llamar a `create_project` para cada usuario que se conecte. Usa solo la conexión. 

---

## 5. Agentes personalizados (`CustomAgent`)

### 5.1 Interfaz mínima y parámetros opcionales

La función debe ser `async` y devolver `str`. Puede aceptar parámetros opcionales inyectados por memoria:

```python
from typing import Optional, Any

async def your_custom_agent(
    query: str,
    env_variable: Optional[dict] = None,
    chat_history: Optional[str] = None,
    relevant_chat_history: Optional[str] = None,
    # <any_arbitrary_config>: Optional[Any] = None
) -> str:
    return f"This is a custom response to: {query}"
```



> Desde la versión 1.5.1, si usas `kwargs` en agentes personalizados, debes **declarar explícitamente** los argumentos requeridos en la firma. 

### 5.2 Registro en `executor_dict` y correspondencia con YAML

```python
executor_dict = {
    "CustomAgentName": your_custom_agent
}
```

La clave debe **coincidir** con `agent_name` en el YAML del proyecto. 

### 5.3 Ejemplo simple con Chat Completions

```python
from air import AsyncAIRefinery

async def simple_agent(query: str) -> str:
    client = AsyncAIRefinery(api_key=api_key)
    prompt = (
        "Your task is to generate synthetic data that can help answer the user "
        "question below. Do not mention that this is synthetic data.\n\n"
        f"{query}"
    )
    response = await client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="meta-llama/Llama-3.1-70B-Instruct",
    )
    return response.choices[0].message.content
```



---

## 6. Agentes integrados frecuentes

### 6.1 PlanningAgent

Plantilla YAML:

```yaml
agent_class: PlanningAgent
agent_name: <name>
agent_description: <desc>
config:
  output_style: "markdown"        # o "conversational" o "html"
  contexts:
    - "date"
    - "chat_history"
    - "env_variable"
    - "relevant_chat_history"
self_reflection_config:
  self_reflection: false
  max_attempts: 2
  response_selection_mode: "auto"
  return_internal_reflection_msg: false
```



### 6.2 ImageUnderstandingAgent

Configuración mínima y plantilla de opciones:

```yaml
utility_agents:
  - agent_class: ImageUnderstandingAgent
    agent_name: "ImageUnderstandingAgent"
    agent_description: "This agent can help you understand and analyze an image."
    config:
      output_style: "conversational"
      contexts: ["date", "chat_history"]

orchestrator:
  agent_list:
    - agent_name: "ImageUnderstandingAgent"
```

Plantilla completa de opciones incluida en la doc. 

### 6.3 GoogleAgent (Vertex AI Agent Builder)

Requisitos: `GOOGLE_APPLICATION_CREDENTIALS=creds.json` y `resource_name` del agente de Vertex AI.

```bash
export GOOGLE_APPLICATION_CREDENTIALS=creds.json
```

```yaml
orchestrator:
  agent_list:
    - agent_name: "GoogleTrendsAgent"

utility_agents:
  - agent_class: GoogleAgent
    agent_name: "GoogleTrendsAgent"
    agent_description: "Uses Google Search tool to find trending terms."
    config:
      resource_name: "projects/<project_id>/locations/<location>/resources/<type>/<id>"
    # contexts: ["date", "chat_history"]
```



### 6.4 A2AClientAgent

Permite conectar con agentes expuestos por servidores A2A. Deben estar en ejecución y accesibles en puertos independientes si locales. Se añade como `utility_agent` y se referencia en `orchestrator.agent_list`. 

### 6.5 AnalyticsAgent

Dos modos documentados.

* **Con Pandas (CSV) vía auto‑instanciación**:

  ```yaml
  orchestrator:
    agent_list:
      - agent_name: "AnalyticsAgent"

  utility_agents:
    - agent_class: AnalyticsAgent
      agent_name: "AnalyticsAgent"
      agent_description: "..."
      config:
        visualization: false
        executor_config:
          type: PandasExecutor
          tables:
            - name: "world_cities"
              desc: "Global city data..."
              file_path: "data/world_cities.csv"
              columns:
                - name: "city_name"
                - name: "area_km2"
            - name: "city_mayors"
              file_path: "data/city_mayors.csv"
            - name: "attractions"
              file_path: "data/attractions.csv"
        output_style: "markdown"
        contexts: ["date", "chat_history"]
  ```



* **Con PostgreSQL vía executor manual**:
  YAML sin credenciales y Python con `PostgresAPI` y `executor_dict["PostgresExecutor"] = callable`:

  ```yaml
  orchestrator:
    agent_list:
      - agent_name: "AnalyticsAgent"

  utility_agents:
    - agent_class: AnalyticsAgent
      agent_name: "AnalyticsAgent"
      agent_description: "An agent that performs data analytics"
      config:
        contexts: ["date", "chat_history"]
        executor_config:
          type: PostgresExecutor
          tables:
            - name: "world_cities"
              desc: "Global city data..."
              schema_name: "public"
            - name: "city_mayors"
              schema_name: "public"
            - name: "attractions"
              schema_name: "city_tourism"
  ```

  ```python
  from air import DistillerClient
  from air.api import PostgresAPI

  analytics_db_config = {
      "host": "localhost", "port": "5432", "user": "myuser",
      "password": "mypassword", "database": "city_information",
  }
  analytics_db_client = PostgresAPI(analytics_db_config)

  executor_dict = {
      "Analytics Agent": {
          "PostgresExecutor": analytics_db_client.execute_query
      }
  }
  ```



> El documento también define un bloque `db_config` detallado cuando se quiere declarar conexión Postgres en YAML, con campos `host`, `port`, `user`, `password`, `database`, etc. 

### 6.6 SnowflakeAgent

Plantilla YAML con servicios Cortex “search” y “analyst”, parámetros de cuenta, modelo y opciones.

```yaml
orchestrator:
  agent_list:
    - agent_name: "SnowflakeAgent"

utility_agents:
  - agent_class: SnowflakeAgent
    agent_name: "SnowflakeAgent"
    agent_description: "..."
    config:
      snowflake_password: "SNOWFLAKE_PASSWORD"    # nombre de variable de entorno
      snowflake_services:
        search:
          - name: <svc>
            database: <db>
            db_schema: <schema>
            service_name: <cortex_search_name>
        analyst:
          - name: <svc>
            database: <db>
            db_schema: <schema>
            stage: <stage>
            file_name: <file>
            warehouse: <warehouse>
            user_role: <role>
      snowflake_model: <LLM>
      snowflake_base_url: <base_url>
      sql_timeout: 10
      system_prompt: <instrucciones>
      snowflake_experimental: {}
      snowflake_tool_choice: "auto"
      thought_process_tracing: false
      contexts: ["date", "chat_history"]
```



### 6.7 WriterAIAgent

Requiere un `WRITER_AUTH_TOKEN` y `application_id` de Writer.com. Se configura `api_key_env_var` y `application_id` en YAML. 

---

## 7. Memoria y contexto

* Añadir memoria en tiempo de ejecución vía sesión Distiller:

  ```python
  async with distiller_client(project="memory_tutorial", uuid="test_user", executor_dict=executor_dict) as dc:
      await dc.add_memory(
          source="env_variable",
          variables_dict={"match_location": "Qatar", "fan_experience": "High excitement and engagement"},
      )
      responses = await dc.query(query="Which country is hosting the tournament?")
      async for r in responses:
          print(r["content"])
  ```



* El documento describe explícitamente los módulos `ChatMemoryModule` y `VariableMemoryModule`, coherentes con el esquema `memory_config`. 

---

## 8. Compresión de prompts y reranking con ResearchAgent

Configuración de ejemplo con *reranker* y *compression* y un `WebSearchRetriever`:

```yaml
base_config:
  reranker_config:
    model: "BAAI/bge-reranker-large"
  compression_config:
    model: "microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank"

orchestrator:
  agent_list:
    - agent_name: "ResearchAgent"

utility_agents:
  - agent_class: ResearchAgent
    agent_name: "ResearchAgent"
    agent_description: "..."
    config:
      reranker_top_k: 15         # <0 para omitir
      compression_rate: 0.4      # 1 implica no comprimir
      retriever_config_list:
        - retriever_name: "InternetSearch"
          retriever_class: WebSearchRetriever
          description: "..."     # opcional
```



---

## 9. Chat Completions API síncrona

Además de la variante asíncrona, el cliente `AIRefinery` expone `chat.completions.create(...)` síncrono con mismos parámetros y estructura de respuesta:

```python
from air import AIRefinery

def generate_response(query: str) -> str:
    client = AIRefinery(api_key=api_key)
    response = client.chat.completions.create(
        messages=[{"role": "user", "content": f"Your task is to generate a response.\n\n{query}"}],
        model="meta-llama/Llama-3.1-70B-Instruct",
    )
    return response.choices[0].message.content
```



---

## 10. Versionado y descarga de configuración

* Versionado de proyectos: comienza en 0 y se incrementa al volver a crear el mismo nombre. Conexión por defecto a la última versión; se puede fijar `project_version="1"` en la conexión. 
* Descarga de configuración:

  ```python
  project_config = client.distiller.download_project(project="example", project_version="1")
  ```



---

## 11. Estructura mínima de proyecto y ejecución

Estructura indicada en la guía de inicio rápido:

```
example/
├── example.py
├── example.yaml
├── .env
```

Ejecución:

```bash
cd example/
python example.py
```

La guía establece que estos comandos crean el proyecto en el servidor y permiten interactuar con agentes desde el terminal. 

---

## 12. Recetas frecuentes

### 12.1 Proyecto básico con un CustomAgent y un agente integrado

* YAML:

  ```yaml
  orchestrator:
    agent_list:
      - agent_name: "DataScientistAgent"
      - agent_name: "SearchAgent"

  utility_agents:
    - agent_class: CustomAgent
      agent_name: "DataScientistAgent"
      agent_description: "An agent for generating synthetic data."
      config: {}
    - agent_class: SearchAgent
      agent_name: "SearchAgent"
  ```



* Python, conexión y consulta con `executor_dict`: ver patrón de la sección 4.2. 

### 12.2 Integrar PlanningAgent con tu CustomAgent

YAML del tutorial “party planner”: `RecommenderAgent` (custom) y `PlanningAgent` con `contexts: ["chat_history"]`. 

### 12.3 Conectar a una versión concreta de proyecto

Añade `project_version="1"` al `async with DistillerClient(...)`. 

---

## 13. Convenciones de nombres

* Proyecto y `uuid` deben usar solo letras, números, guiones y guiones bajos. El documento lo especifica expresamente. 

---

## 14. Módulos y utilidades adicionales

* **PII Masking**: posibilidad de mantener múltiples YAML con combinaciones de entidades, operadores y configuración de agentes; se selecciona con `create_project(config_path=...)`. Incluye tabla de casos de uso por entorno. 
* **Memoria compartida, compresión, reranking, auto‑reflexión**: descritas como capacidades avanzadas de la plataforma y agentes. 

---

## 15. Contradicciones, lagunas y resolución mínima

1. **Instalación paso a paso incompleta**
   En “SDK Installation Steps” aparecen fragmentos con comandos truncados (`mkdirpython[name]`, `pip` sin paquete). Resolución mínima: usar la orden explícita documentada en el registro de versiones `pip install airefinery-sdk` y omitir los pasos truncados.

2. **Activación de entorno virtual no detallada**
   El doc muestra creación y desactivación, pero no aporta comandos de activación por sistema. Resolución mínima: señalar la carencia y no inventar comandos. 

3. **Cortes y pegados con espacios ausentes en imports y `from air import ...`**
   Los ejemplos muestran tokens pegados (`importos`, `fromairimport`). Resolución mínima: normalizar espacios y saltos de línea sin alterar símbolos ni clases. Todos los bloques de esta guía se han corregido solo a ese nivel. Evidencia en múltiples ejemplos.

4. **Mención errónea en WriterAIAgent**
   La sección de uso y “Quickstart” para WriterAIAgent incluye la instrucción de “añadir un SalesforceAgent” en `utility_agents`, lo que no concuerda con el contexto. Resolución mínima: tratarlo como error de edición y configurar `WriterAIAgent` tal como indican los requisitos de credenciales y parámetros del propio apartado. 

5. **Convenciones de nombres referenciadas sin detalle en otros apartados**
   En Quickstart se dice “project name & uuid must conform to our naming conventions”, pero el detalle solo aparece en otra sección. Resolución mínima: aplicar la regla documentada de caracteres permitidos.

6. **Uso mixto de API Distiller**
   Se documentan tanto `DistillerClient.create_project(...)` como `client.distiller.create_project(...)`, así como `distiller_client.interactive(...)` y el patrón `async with distiller_client(...)`. Resolución mínima: ambos están documentados; esta guía recomienda el **context manager asíncrono**, que se muestra completo en la doc. 

---

## 16. Checklist mínimo de ejecución

1. Instala el SDK: `pip install airefinery-sdk`. 
2. Crea `.env` con `API_KEY`. 
3. Escribe `example.yaml` con `utility_agents`, `orchestrator` y, si aplica, `memory_config`. Usa plantillas anteriores. 
4. Escribe `example.py` que:

   * Cargue `API_KEY`.
   * Cree el proyecto con `create_project(config_path="example.yaml", project="example")`.
   * Declare `executor_dict` si hay `CustomAgent`.
   * Abra sesión asíncrona y haga `dc.query(...)`. 
5. Ejecuta `python example.py`. Confirmar respuestas en terminal. 

---

### Apéndice A. Ejemplo completo mínimo

`example.yaml`

```yaml
orchestrator:
  agent_list:
    - agent_name: "DataScientistAgent"

utility_agents:
  - agent_class: CustomAgent
    agent_name: "DataScientistAgent"
    agent_description: "An agent for generating synthetic data."
    config: {}
```



`example.py`

```python
import os
import asyncio
from dotenv import load_dotenv
from air import AsyncAIRefinery, DistillerClient

load_dotenv()
api_key = str(os.getenv("API_KEY"))

async def simple_agent(query: str) -> str:
    client = AsyncAIRefinery(api_key=api_key)
    prompt = (
        "Your task is to generate synthetic data that can help answer the user "
        "question below. Do not mention that this is synthetic data.\n\n"
        f"{query}"
    )
    resp = await client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="meta-llama/Llama-3.1-70B-Instruct",
    )
    return resp.choices[0].message.content

async def main():
    client = DistillerClient(api_key=api_key)
    client.create_project(config_path="example.yaml", project="example")
    executor_dict = {"DataScientistAgent": simple_agent}
    async with client(project="example", uuid="test_user", executor_dict=executor_dict) as dc:
        responses = await dc.query(query="Who won the FIFA world cup 2022?")
        async for r in responses:
            print(r["content"])

if __name__ == "__main__":
    asyncio.run(main())
```