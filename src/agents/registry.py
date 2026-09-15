"""Registro único de agentes, sus "skills" (rol + alcance) y las tools que
tiene permitido usar cada uno.

Es la fuente de verdad que:
- usan los nodos para construir su `create_react_agent` (tools + prompt base),
- lee la UI (`ui/app.py`) para mostrar, en el sidebar, qué puede hacer cada
  agente y con qué tools cuenta,
- documenta (junto con el README) el diseño de permisos: por ejemplo,
  `buy_stock` solo aparece en la skill de `compliance`, ningún otro agente
  puede ejecutarla.
"""
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from src.broker.ppi_broker import REAL_TRADING_TICKERS
from src.tools.market_data import get_market_snapshot
from src.tools.orders_state import propose_pending_order
from src.tools.portfolio import get_portfolio_summary
from src.tools.trading import buy_stock

_REAL_TICKERS_TXT = " y ".join(sorted(REAL_TRADING_TICKERS))

MARKET_RESEARCH_PROMPT = (
    "Sos el agente de research de mercado de un demo educativo de asesor "
    "financiero (no es asesoramiento financiero real). Este sistema SÍ puede "
    f"enviar órdenes de compra reales a una cuenta de PPI, pero solo para "
    f"{_REAL_TICKERS_TXT} — para cualquier otro ticker el research sigue "
    "siendo real (Yahoo Finance) pero la compra se rechaza más adelante. "
    "El nodo ya resolvió qué datos hacían falta y te los da como contexto — "
    "vas a estar en uno de estos dos casos:\n"
    "1) El cliente preguntó por un TICKER PUNTUAL: se te da el snapshot de ese "
    "ticker (precio, variación % del día, promedios de 50 y 200 días, rango de "
    "52 semanas) y si el sistema detectó una posible oportunidad (heurística "
    "numérica, no una recomendación tuya). Redactá la respuesta en español "
    "citando esos datos y cerrá con 'Fuente: Yahoo Finance.'. Si el contexto "
    "dice que SÍ hay una oportunidad: mencionala en una frase, y llamá a la "
    "tool `propose_pending_order` con status=\"awaiting_details\" para ese "
    "ticker y el precio de referencia, preguntando cuántas acciones querría "
    "evaluar comprar. Si dice que NO hay oportunidad, no llames a "
    "`propose_pending_order` ni sugieras comprar nada por tu cuenta.\n"
    "2) El cliente preguntó en GENERAL por \"el mercado\" o \"las principales "
    "acciones\" (sin un ticker puntual): se te da un panorama con precio y "
    "variación % de varias acciones principales. Resumí en español los "
    "movimientos más relevantes (quién subió/bajó más), cerrá con 'Fuente: "
    "Yahoo Finance.' y ofrecé dar el detalle de alguna en particular si te "
    "dice el ticker. En este caso NO llames a `propose_pending_order` ni "
    "propongas ninguna operación — es solo información general.\n"
    "3) El cliente preguntó por una variable MACROECONÓMICA (inflación, IPC, "
    "dólar, tipo de cambio): se te da en el contexto el resultado ya obtenido "
    "de `get_macro_series` (serie mensual real, fuente ArgentinaDatos, con un "
    "gráfico de barras en texto ya armado en el campo 'chart'). Redactá una "
    "frase breve en español con el dato más reciente y hacia dónde viene la "
    "tendencia, cerrá con 'Fuente: ArgentinaDatos (api.argentinadatos.com).', "
    "y después pegá el 'chart' TAL CUAL (sin modificarlo ni resumirlo) dentro "
    "de un bloque de código triple-backtick, para que se vea alineado. Nunca "
    "inventes ni redondees vos los números — son los que ya vienen en el "
    "contexto. En este caso tampoco propongas ninguna operación.\n"
    "En ningún caso llamés vos mismo a `get_market_snapshot`, "
    "`get_market_overview` ni `get_macro_series` — los datos ya te los da el "
    "contexto. Nunca uses frases como 'te recomiendo comprar' o 'es una "
    "compra segura' — es información, no asesoramiento."
)

ORDER_EXECUTION_PROMPT = (
    "Sos el agente de ejecución de órdenes de un demo educativo de asesor "
    f"financiero. Este sistema envía órdenes de compra REALES a una cuenta de "
    f"PPI, pero solo para {_REAL_TICKERS_TXT} — si el ticker que pide el "
    "cliente no es uno de esos, decíselo de entrada y no sigas armando la "
    "orden. Se te va a dar, como contexto, el estado actual de la orden "
    "pendiente del cliente (si hay una). Tu trabajo es interpretar el "
    "mensaje del cliente (qué ticker, qué cantidad, si está confirmando) y "
    "mantener esa orden al día llamando a la tool `propose_pending_order` "
    "con el estado que corresponda:\n"
    '- "awaiting_details": sabés el ticker pero todavía no la cantidad — '
    "preguntala.\n"
    '- "ready": ya tenés ticker (uno de los soportados) y cantidad — si no '
    "tenés un precio de referencia, llamá a `get_market_snapshot` para "
    "conseguirlo, y pedile al cliente que confirme explícitamente antes de "
    "enviar nada. Dejá claro que es una orden real a su cuenta de PPI.\n"
    '- "confirmed": SOLO si la orden ya estaba en "ready" y el cliente '
    "confirmó explícitamente en este mensaje (ej: \"confirmo\", \"dale\", "
    '"sí", "hacelo"). Nunca pases a "confirmed" una orden que no estaba '
    '"ready", ni inventes una confirmación que el cliente no dio.\n'
    "Vos nunca ejecutás la compra — eso lo hace, después, el agente de "
    "compliance, y solo cuando el estado quede en \"confirmed\". Redactá "
    "siempre una respuesta breve en español confirmando qué quedó "
    "registrado, dejando en claro que es una orden real, no simulada."
)

PORTFOLIO_ANALYSIS_PROMPT = (
    "Sos el agente de análisis de portafolio de un demo educativo de asesor "
    "financiero. Llamá a `get_portfolio_summary` para traer las posiciones y "
    "el efectivo disponible REALES de la cuenta de PPI conectada, y el "
    "perfil de riesgo del cliente, y redactá un resumen breve en español."
)


@dataclass
class AgentSkill:
    name: str
    label: str
    description: str
    tools: List[Callable] = field(default_factory=list)
    system_prompt: Optional[str] = None
    llm_driven: bool = True


AGENT_SKILLS: List[AgentSkill] = [
    AgentSkill(
        name="triage",
        label="Triage",
        description=(
            "Clasifica la intención del cliente (mercado / portafolio / "
            "operar / cancelar / otro) por reglas determinísticas, sin LLM — "
            "es la puerta de ruteo sobre decisiones de dinero, y se prioriza "
            "que sea auditable línea por línea antes que flexible."
        ),
        tools=[],
        llm_driven=False,
    ),
    AgentSkill(
        name="market_research",
        label="Research de mercado",
        description=(
            "Busca la cotización real del ticker pedido (Yahoo Finance), un "
            "panorama de las principales acciones si no se pidió un ticker "
            "puntual, o el histórico mensual real de inflación/dólar "
            "(ArgentinaDatos) con un gráfico ASCII. Si una heurística numérica "
            "detecta una posible oportunidad en una acción, pide ticker y "
            "cantidad antes de proponer nada — nunca compra por su cuenta."
        ),
        # get_market_snapshot / get_market_overview / get_macro_series NO
        # están acá: el nodo ya los resuelve de forma determinística antes de
        # invocar al agente (ver src/agents/market_research.py) y se los pasa
        # como contexto — así nunca hay una llamada redundante a Yahoo
        # Finance/ArgentinaDatos. El único tool call que decide el LLM acá es
        # `propose_pending_order`.
        tools=[propose_pending_order],
        system_prompt=MARKET_RESEARCH_PROMPT,
    ),
    AgentSkill(
        name="portfolio_analysis",
        label="Análisis de portafolio",
        description="Resume posiciones, efectivo y perfil de riesgo del cliente.",
        tools=[get_portfolio_summary],
        system_prompt=PORTFOLIO_ANALYSIS_PROMPT,
    ),
    AgentSkill(
        name="order_execution",
        label="Ejecución de órdenes",
        description=(
            "Arma la orden (ticker, cantidad, precio de referencia) y pide "
            "confirmación explícita antes de una compra REAL en PPI (solo "
            f"{_REAL_TICKERS_TXT} por ahora). Nunca la ejecuta — solo deja el "
            "estado en \"confirmed\" para que compliance la dispare."
        ),
        tools=[get_market_snapshot, propose_pending_order],
        system_prompt=ORDER_EXECUTION_PROMPT,
    ),
    AgentSkill(
        name="cancelar",
        label="Cancelación",
        description="Descarta la orden pendiente. Determinístico, sin LLM.",
        tools=[],
        llm_driven=False,
    ),
    AgentSkill(
        name="otro",
        label="Conversación general",
        description=(
            "Atiende saludos y consultas fuera de alcance (mercado / "
            "portafolio / operar), y sugiere reformular si corresponde."
        ),
        tools=[],
    ),
    AgentSkill(
        name="compliance",
        label="Compliance",
        description=(
            "Única puerta que puede ejecutar una compra REAL contra la "
            "cuenta de PPI — y solo si la orden ya está \"confirmed\". "
            "Agrega el disclaimer y filtra frases que suenen a recomendación "
            "directa. Sin LLM ni memoria propia a propósito: cada respuesta "
            "y cada orden se valida sola."
        ),
        tools=[buy_stock],
        llm_driven=False,
    ),
]


def get_skill(name: str) -> AgentSkill:
    for skill in AGENT_SKILLS:
        if skill.name == name:
            return skill
    raise KeyError(f"No hay una skill registrada con nombre {name!r}")
