# Asesor financiero multi-agente (demo funcional)

Implementación funcional en **LangChain + LangGraph** del ejemplo de la
presentación "Multiagentes en producción": un cliente pregunta, el triage
decide qué agente responde, y **compliance** es la única puerta que puede
disparar una compra — y siempre pide confirmación explícita antes de hacerlo.

Los agentes especialistas (research de mercado, análisis de portafolio,
ejecución de órdenes) son agentes reales de LangChain con **tool-calling**:
es el LLM quien decide cuándo llamar a cada tool, no código que ya sabe qué
tool usar. Toda la memoria (conversación, portafolio, órdenes, y el log de
auditoría de qué tool llamó cada agente) vive en una única base **SQLite**
persistente. Una **UI en Streamlit** muestra, en vivo, cada tool que se llama
y cuánto cuesta cada llamada al LLM.

No es asesoramiento financiero real. **Sí se conecta a una cuenta real de
PPI (Portfolio Personal Inversiones)**: el portafolio y el efectivo que ves
son los reales de la cuenta, y las compras de `GGAL` y `YPF` son órdenes
reales de mercado — revisá siempre el mensaje de confirmación antes de
responder "confirmo". El resto de los tickers del demo (AAPL, MSFT, MELI,
etc.) siguen teniendo research real vía Yahoo Finance, pero la compra se
rechaza explícitamente: todavía no están mapeados a un instrumento operable
en PPI (ver "Alcance del broker real" más abajo).

> ⚠️ **Esto puede gastar plata de verdad.** `compliance` es la única puerta
> que ejecuta `buy_stock`, y solo después de que el cliente escribe
> "confirmo" — pero esa confirmación dispara una orden real a mercado en tu
> cuenta de PPI. No corras este demo con `.env` apuntando a una cuenta real
> a menos que entiendas y aceptes eso.

## Cómo correrlo con Hermes Agent (modo principal)

Este demo corre como un agente de **[Hermes Agent](https://hermes-agent.nousresearch.com)**
(Nous Research, agente autónomo open-source con memoria persistente y CLI
propio) en vez de necesitar la app LangGraph/Streamlit de abajo. Un **MCP
server local** (`mcp_server/server.py`) expone las mismas tools de
research/portafolio/órdenes que usa la implementación de referencia, y una
**skill** (`asesor-financiero`) le da a Hermes el mismo guion de
conversación (research → armar orden → confirmar → ejecutar). La
visibilidad en tiempo real de qué tool se está llamando la da el streaming
nativo de la TUI/CLI de Hermes — no hace falta ninguna UI adicional.

### 1. Instalar Hermes

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
source ~/.zshrc      # o el rc de tu shell
hermes setup         # elegí proveedor/modelo de LLM (OpenRouter, etc.)
```

### 2. Preparar el MCP server del demo

El SDK `mcp` necesita **Python 3.10+**; el `.venv` de este proyecto puede
seguir en una versión anterior (así se armó originalmente, con 3.9) — el
MCP server corre en un venv aparte:

```bash
python3.11 -m venv .venv-mcp
.venv-mcp/bin/pip install -r requirements.txt
```

Registralo en Hermes apuntando al Python de ese venv:

```bash
hermes mcp add asesor_financiero \
  --command "$(pwd)/.venv-mcp/bin/python" \
  --args "$(pwd)/mcp_server/server.py"
```

Confirmá que levantó los 6 tools (`get_market_snapshot`,
`get_market_overview`, `get_macro_series`, `get_portfolio_summary`,
`propose_pending_order`, `buy_stock`):

```bash
hermes mcp test asesor_financiero
```

La skill `asesor-financiero` ya queda instalada en
`~/.hermes/skills/asesor-financiero/SKILL.md` (persona del asesor + la
secuencia obligatoria `awaiting_details → ready → confirmed` antes de poder
comprar).

### 3. Variable nueva en `.env`

- `ALLOW_REAL_TRADES` (default `false`): con Hermes, `buy_stock` corre en
  **dry-run** (simula, no toca PPI) salvo que pongas esto en `true` a
  propósito — ver `.env.example`.

### 4. Charlar con el asesor

```bash
hermes
```

Cada tool call (`get_market_snapshot`, `propose_pending_order`,
`buy_stock`, etc.) se ve **en vivo** en la TUI mientras Hermes responde. El
whitelist de tickers (GGAL/YPF), la re-cotización contra PPI y el chequeo
de saldo de `buy_stock` siguen aplicando sin cambios — el MCP server
reutiliza esa lógica tal cual desde `src/tools/trading.py`. El gate de
"solo ejecutar si ya hubo una propuesta confirmada" (que en LangGraph
resuelve el nodo de compliance) se reimplementa dentro del MCP server, ya
que Hermes no tiene ese grafo de nodos — ver el docstring de
`mcp_server/server.py` para el detalle.

Todas las llamadas quedan auditadas en la misma tabla `tool_calls` de
`data/memory.db` que usa la implementación LangGraph (`thread_id="hermes"`),
así el registro de auditoría es uno solo sin importar qué orquestador se
usó.

> ⚠️ **Este MCP server está pensado para usarse solo desde el CLI local de
> Hermes** (`hermes`). No lo sumes a un gateway de mensajería
> (Telegram/Discord/WhatsApp/etc.) sin pensar antes en quién más podría
> terminar disparando una compra real por ese canal.

## Implementación de referencia (LangGraph + Streamlit)

Todo lo de acá abajo es la implementación original del demo — LangGraph
como orquestador, con una UI en Streamlit. El MCP server de Hermes de
arriba reutiliza directamente estas mismas tools (`src/tools/*.py`,
`src/broker/ppi_broker.py`); esta sección documenta esa lógica y sigue
siendo una forma válida de correr el demo (standalone, sin Hermes).

### Arquitectura

```
Cliente → Triage → Research de mercado (Yahoo Finance)
                 → Análisis de portafolio (mock)
                 → Ejecución de órdenes (arma la compra, pide confirmación)
                                              ↓
                                        Compliance
                              (agrega disclaimer, o si la orden
                               ya está confirmada, la ejecuta)
```

- **Triage** (`src/agents/triage.py`): clasifica la intención por reglas
  (mercado / portafolio / operar / cancelar / otro) — determinístico y
  auditable a propósito, sin depender de un LLM para decidir qué hacer con
  el dinero del cliente.
- **Research de mercado** (`src/agents/market_research.py`): un agente
  LangChain (`create_react_agent`) con la tool `get_market_snapshot` (Yahoo
  Finance real, vía `yfinance`). La heurística de oportunidad
  (`detect_opportunity`, precio cerca del mínimo anual o retroceso frente al
  promedio de 50 días en tendencia alcista) es una función Python pura — un
  cálculo numérico, no un juicio para dejarle a un LLM — que el nodo calcula
  y le pasa al agente como contexto antes de que redacte la respuesta. Si hay
  una señal, el agente **no compra nada solo**: llama a la tool
  `propose_pending_order` y le pide al cliente el ticker y la cantidad.
  También resuelve preguntas por **variables macroeconómicas** (inflación,
  IPC, dólar oficial/blue) con la tool `get_macro_series` (histórico mensual
  real vía [ArgentinaDatos](https://api.argentinadatos.com), sin auth), que
  devuelve la serie de datos junto con un gráfico de barras en texto (ASCII)
  ya armado — el agente lo pega tal cual en la respuesta, dentro de un
  bloque de código, así se ve alineado en cualquier terminal (Hermes,
  consola, o el chat de Streamlit).
- **Análisis de portafolio** (`src/agents/portfolio_analysis.py`): agente
  LangChain con la tool `get_portfolio_summary`.
- **Ejecución de órdenes** (`src/agents/order_execution.py`): agente
  LangChain con las tools `get_market_snapshot` y `propose_pending_order`.
  Interpreta si el cliente está dando la cantidad o confirmando, y arma la
  orden (ticker, cantidad, precio de referencia) dejándola en estado
  `"ready"`, pidiendo confirmación explícita. Nunca la ejecuta él mismo.
- **Compliance** (`src/agents/compliance.py`): revisa frases que suenen a
  recomendación directa, agrega el disclaimer, y es el único nodo que llama
  a la tool `buy_stock` — y solo cuando el estado de la orden es
  `"confirmed"`. Sin LLM, por la misma razón que el triage.

Cada agente especialista mantiene, además, su implementación original por
reglas como **fallback**: si no hay ninguna API key de LLM configurada, el
demo sigue funcionando end-to-end sin generación de lenguaje natural (ver
"Modo con LLM y modo offline" más abajo).

### Tools y skills

El registro único de agentes, su "skill" (rol + alcance) y las tools que
tiene permitido usar cada uno vive en `src/agents/registry.py` — es la fuente
de verdad que usan tanto los nodos (para construir su agente LangChain) como
la UI (para mostrar, en el sidebar, qué puede hacer cada agente).

| Agente | Skill | Tools | ¿LLM? |
|---|---|---|---|
| `triage` | Clasifica la intención por reglas | — | No |
| `market_research` | Cotización real + detecta oportunidades + variables macro (inflación/dólar) con gráfico | `get_market_snapshot`, `get_macro_series`, `propose_pending_order` | Sí |
| `portfolio_analysis` | Resume posiciones y efectivo | `get_portfolio_summary` | Sí |
| `order_execution` | Arma la orden y pide confirmación | `get_market_snapshot`, `propose_pending_order` | Sí |
| `cancelar` | Descarta la orden pendiente | — | No |
| `otro` | Conversación general / fuera de alcance | — | Sí (opcional) |
| `compliance` | Única puerta que ejecuta la compra real | `buy_stock` | No |

| Tool | Archivo | Qué hace |
|---|---|---|
| `get_market_snapshot` | `src/tools/market_data.py` | Cotización real vía Yahoo Finance (precio, variación, medias móviles, rango anual) |
| `get_macro_series` | `src/tools/macro_data.py` | Histórico mensual real de inflación o dólar (ArgentinaDatos), con gráfico de barras en texto (ASCII) listo para mostrar |
| `get_portfolio_summary` | `src/tools/portfolio.py` | Posiciones y efectivo reales de la cuenta de PPI (`src/broker/ppi_broker.py`); `client_id`/`risk_profile` locales |
| `propose_pending_order` | `src/tools/orders_state.py` | No ejecuta nada: registra el estado propuesto de la orden pendiente (ticker, cantidad, status). El nodo lee el `tool_call` para actualizar el estado del grafo — así la transición sigue siendo determinística y auditable aunque la decisión de *cuándo* proponerla sea del LLM. |
| `buy_stock` | `src/tools/trading.py` | Compra REAL contra la cuenta de PPI para `GGAL`/`YPF` (cualquier otro ticker se rechaza sin tocar PPI); registra la orden en `data/memory.db`. Exclusiva de `compliance`. |

### Alcance del broker real

El portafolio (`get_portfolio_summary`) siempre muestra el efectivo y las
posiciones reales de la cuenta de PPI conectada — no hay modo mockeado, a
diferencia del LLM. La compra real está limitada, por ahora, a `GGAL` y
`YPF`: son acciones argentinas que PPI opera 1 a 1 en ARS (`ACCIONES` /
`BYMA`). El resto de `DEMO_TICKERS` (AAPL, MSFT, GOOGL, AMZN, TSLA, NVDA,
META, MELI, KO, DIS) cotiza en PPI como CEDEAR — un instrumento distinto,
con precio en ARS y un ratio de conversión frente a la acción real, que no
tiene nada que ver con el precio en USD que devuelve Yahoo Finance — así
que pedir comprarlos da un rechazo explícito en vez de una compra simulada
o, peor, una compra real al precio equivocado. Ver
`src/broker/ppi_broker.py:REAL_TRADING_TICKERS`.

El precio que se muestra durante la conversación (Yahoo Finance) es solo
informativo: al confirmar, `buy_stock` siempre vuelve a cotizar contra PPI
antes de enviar la orden, así que el costo final puede diferir del precio
de referencia que viste en el chat.

Credenciales (`.env`, ver `.env.example`): `PPI_PUBLIC_KEY` / `PPI_PRIVATE_KEY`
(un par de API keys que se generan en la web de PPI, en Configuración → API
— no es el usuario/contraseña con el que entrás a la web) y
`PPI_ACCOUNT_NUMBER`.

### Memoria

Todo vive en una única base **SQLite** (`data/memory.db`), en vez de JSON
sueltos + memoria en RAM:

- **Corto plazo**: checkpointer de LangGraph (`SqliteSaver`, por
  `thread_id`, ver `src/memory.py`) — persiste la conversación y el
  `pending_order` **entre corridas**, no solo entre turnos.
- **Largo plazo**: tabla `portfolio` (solo `client_id`/`risk_profile` — el
  efectivo y las posiciones reales vienen siempre de PPI, no de acá) y
  `orders` (historial de compras, reales para GGAL/YPF).
- **Auditoría/observabilidad**: tablas `tool_calls` (qué tool llamó cada
  agente, con qué argumentos y qué devolvió) y `token_usage` (tokens y costo
  estimado de cada llamada al LLM) — ver `src/observability/tracing.py`.

La primera vez que corre, `data/memory.db` se siembra con el portafolio de
ejemplo de `data/portfolio.json`. `data/orders.json` queda como referencia
histórica del formato original — ya no se lee ni se escribe.

### Modo con LLM y modo offline

Los agentes especialistas usan tool-calling real de LangChain, así que para
la experiencia completa necesitás una API key de LLM en `.env`:

```bash
cp .env.example .env
# y completá OPENAI_API_KEY o ANTHROPIC_API_KEY
pip install langchain-openai   # o langchain-anthropic
```

`src/config.py` elige automáticamente el proveedor disponible. **Sin ninguna
key configurada**, cada agente especialista cae a su implementación original
por reglas (determinística, sin generación de lenguaje natural) — el demo
sigue funcionando de punta a punta con datos reales (Yahoo Finance, portafolio
y compra reales contra PPI), solo que sin un LLM redactando ni decidiendo
tool-calls. El broker, a diferencia del LLM, no tiene modo offline: sin
credenciales de PPI válidas en `.env`, el portafolio y la compra no
funcionan (ver "Alcance del broker real" arriba).

### Instalación

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# completá PPI_PUBLIC_KEY / PPI_PRIVATE_KEY / PPI_ACCOUNT_NUMBER (obligatorias)
```

### Uso

#### Por consola

```bash
python main.py            # nueva conversación
python main.py <thread_id> # retoma una conversación guardada en data/memory.db
```

Cada tool-call y cada llamada al LLM se imprime en vivo (`🔧 [agente]
tool(args) → resultado`, `💬 [agente] modelo: tokens in/out (costo)`), además
de la respuesta del asesor.

Conversación de ejemplo:

```
Vos: ¿cómo está AAPL?
🔧 [market_research] get_market_snapshot(ticker='AAPL') → {...}
💬 [market_research] claude-sonnet-5: 1552 tokens in / 288 tokens out ($0.00898)
Asesor: AAPL: $187.3 (-1.2% hoy).
        Promedio 50 días: $198.4 · Promedio 200 días: $190.1.
        Rango de las últimas 52 semanas: $178.9 – $237.5.
        Fuente: Yahoo Finance.

        Noto una posible oportunidad: el precio está a menos de un 5% de su
        mínimo de las últimas 52 semanas.
        ¿Querés que evalúe comprar AAPL? Decime el ticker y la cantidad
        (por ejemplo: "comprar 5 AAPL").

        Esto es una demo educativa — no es asesoramiento financiero real.
        Este agente sí puede enviar órdenes reales a tu cuenta de PPI para
        GGAL/YPF: revisá siempre antes de confirmar.

Vos: comprar 5 AAPL
Asesor: La compra real todavía no está disponible para AAPL — por ahora
        solo opero compras reales de GGAL y YPF.

Vos: comprar 5 GGAL
🔧 [order_execution] propose_pending_order(...) → {...}
Asesor: Vas a comprar 5 acciones de GGAL (precio de referencia $X, orden
        REAL a tu cuenta de PPI — el costo final se recalcula con la
        cotización del momento). Respondé "confirmo" para enviarla o
        "cancelar" para dejarla sin efecto.

Vos: confirmo
🔧 [compliance] buy_stock(...) → {...}
Asesor: Listo: compré 5 GGAL a $X (costo $Y, orden real de PPI #12345).
        Quedó registrada en data/memory.db.

        Esto es una demo educativa — no es asesoramiento financiero real.
        Este agente sí puede enviar órdenes reales a tu cuenta de PPI para
        GGAL/YPF: revisá siempre antes de confirmar.
```

Otros ejemplos: `"¿cómo va mi portafolio?"`, `"cancelar"` (para descartar una
orden pendiente).

#### UI en tiempo real (Streamlit)

```bash
streamlit run ui/app.py
```

Chat con el asesor, un panel en vivo que muestra cada tool llamada mientras
se procesa el mensaje (mismo formato que la consola), y un sidebar con:
tokens/costo acumulados del thread actual, y el registro completo de
agentes/skills/tools (`src/agents/registry.py`). El campo `thread_id` permite
retomar una conversación guardada entre sesiones del navegador.

### Costos

Cada llamada al LLM se loguea con sus tokens de entrada/salida
(`usage_metadata`, estándar de LangChain para OpenAI/Anthropic) y un costo
estimado según `src/observability/pricing.py` — una tabla de precios **local
y manual** (no se consulta ninguna API de precios en vivo). Si el modelo
configurado no está en la tabla, se sigue guardando el conteo de tokens pero
sin costo, en vez de inventar un número; actualizá `MODEL_PRICING` cuando
cambien los precios del proveedor o agregues un modelo nuevo.

Todo el historial de tokens/costo por `thread_id` y por agente queda en la
tabla `token_usage` de `data/memory.db`.

### Tests

```bash
pip install -r requirements-dev.txt
pytest
```

- `tests/test_tools.py`: las tools solas (Yahoo Finance real + compra/portafolio
  contra una base SQLite aislada), sin LLM.
- `tests/test_graph_smoke.py`: el grafo completo de punta a punta. La mayoría
  de los tests fuerza el fallback por reglas (fixture `no_llm`) para seguir
  siendo gratis y determinísticos aunque haya una API key real en el
  entorno; un par de tests aparte ejercitan el camino con LLM real usando un
  chat model falso con tool-calling scripteado
  (`FakeToolCallingLLM`/`GenericFakeChatModel`) — ninguno pega a una API real.

## Qué falta para que esto sea un producto real (no solo un demo)

- **Ampliar el broker real más allá de GGAL/YPF**: `buy_stock` ya opera
  contra la cuenta real de PPI, pero solo para esos dos tickers (ver
  "Alcance del broker real"). Sumar el resto de `DEMO_TICKERS` requiere
  mapear cada uno a su CEDEAR en PPI (ratio de conversión, precio en ARS) en
  vez de asumir que el ticker de Yahoo Finance es directamente operable.
  También falta manejo más fino de errores de mercado (rechazos parciales,
  reintentos) y una capa de auditoría más seria que una tabla SQLite.
- **Triage por LLM**: las reglas actuales cubren el caso de demo; con más
  variedad de consultas conviene un clasificador con LLM (o híbrido:
  reglas primero, LLM como respaldo) — se mantuvo por reglas a propósito por
  ser la puerta de decisión sobre dinero.
- **Observabilidad**: el tracer propio (`src/observability/tracing.py`) cubre
  tool-calls y costo; para producción de verdad convendría sumar LangSmith
  (o el tracer nativo de LangGraph) para trazas distribuidas, replay de runs
  y alertas.
- **Evals**: un set de conversaciones de prueba (incluyendo intentos de
  hacer que el agente compre sin confirmar, o de saltarse compliance) que
  corra en cada cambio.
- **Perfil de riesgo real**: hoy es un campo fijo en la base; en un producto
  real condicionaría qué operaciones se pueden ni siquiera proponer.
- **Precios de LLM al día**: la tabla de `src/observability/pricing.py` es
  manual — en producción convendría una fuente centralizada (o la propia
  facturación del proveedor) en vez de mantenerla a mano.
