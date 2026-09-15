"""Wrapper del bróker real (PPI — Portfolio Personal Inversiones).

A diferencia del LLM (que cae a un modo por reglas si no hay API key), el
bróker es obligatorio: sin `PPI_PUBLIC_KEY`/`PPI_PRIVATE_KEY`/
`PPI_ACCOUNT_NUMBER` válidos en el entorno, el portafolio y la compra reales
no funcionan — no hay modo mockeado alternativo.

Alcance v1: solo se puede *comprar* de verdad `GGAL` y `YPF` — acciones
argentinas que PPI opera 1 a 1 en ARS (`ACCIONES`/`BYMA`), sin ratio de
CEDEAR ni conversión de moneda de por medio (a diferencia de tickers como
AAPL o MELI, que en PPI cotizan como CEDEARs en ARS con un ratio propio
frente a la acción real — fuera de alcance de esta primera versión). Ver
`src/tools/trading.py` para el rechazo explícito de tickers no soportados.

`YPF` es un caso especial confirmado contra la cuenta real: el ticker de
BYMA en PPI es `YPFD`, no `YPF` (que es el ADR de NYSE) — pedirle a PPI la
cotización de `YPF` da "Instrument not found". Este módulo traduce
`YPF ↔ YPFD` en el borde (`_to_ppi_ticker`/`_to_display_ticker`) para que el
resto de la app siga usando siempre `YPF`, el mismo ticker con el que
research (Yahoo Finance) y el cliente ya trabajan.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, List, Optional

from dotenv import load_dotenv

load_dotenv()

REAL_TRADING_TICKERS = {"GGAL", "YPF"}
_INSTRUMENT_TYPE = "ACCIONES"
_MERCADO = "BYMA"
_SETTLEMENT = os.environ.get("PPI_PLAZO", "A-24HS")
_MARKET_ORDER = "PRECIO-DE-MERCADO"
_QUANTITY_TYPE = "TITULOS"
_OPERATION_TERM = "POR-EL-DIA"

# El ticker "de chat" (el que usa el cliente y también el research de Yahoo
# Finance) no siempre coincide con el ticker real que espera PPI/BYMA. YPF es
# el caso confirmado: "YPF" es el ticker del ADR en NYSE, pero la acción
# argentina en BYMA es "YPFD" — pedirle a PPI la cotización de "YPF" da
# "Instrument not found". Este mapeo traduce en el borde (get_quote /
# place_market_buy) para no filtrar ese detalle al resto de la app.
_DISPLAY_TO_PPI_TICKER = {"YPF": "YPFD"}
_PPI_TO_DISPLAY_TICKER = {v: k for k, v in _DISPLAY_TO_PPI_TICKER.items()}


def _to_ppi_ticker(display_ticker: str) -> str:
    return _DISPLAY_TO_PPI_TICKER.get(display_ticker, display_ticker)


def _to_display_ticker(ppi_ticker: str) -> str:
    return _PPI_TO_DISPLAY_TICKER.get(ppi_ticker, ppi_ticker)


class BrokerConfigError(RuntimeError):
    """Faltan credenciales de PPI o son inválidas."""


class BrokerError(RuntimeError):
    """Error al operar contra la API de PPI."""


@dataclass
class Quote:
    ticker: str
    price: float


@dataclass
class Position:
    ticker: str
    quantity: float
    avg_price: float


class PPIBroker:
    """Cuenta real de PPI. Requiere credenciales válidas — no tiene modo mock."""

    def __init__(self, public_key: str, private_key: str, account_number: str, sandbox: bool = False) -> None:
        if not public_key or not private_key or not account_number:
            raise BrokerConfigError(
                "Faltan PPI_PUBLIC_KEY / PPI_PRIVATE_KEY / PPI_ACCOUNT_NUMBER en .env. "
                "Generá un par de API keys reales desde la web de PPI "
                "(Configuración → API) — el usuario/contraseña con el que entrás "
                "a la web NO sirve como public_key/private_key."
            )
        self._account_number = account_number
        self._sandbox = sandbox
        self._ppi = None
        self._public_key = public_key
        self._private_key = private_key

    def _client(self):
        if self._ppi is None:
            from ppi_client.ppi import PPI

            ppi = PPI(sandbox=self._sandbox)
            try:
                ppi.account.login_api(self._public_key, self._private_key)
            except Exception as exc:
                raise BrokerConfigError(f"Fallo de autenticación con PPI: {exc}") from exc
            self._ppi = ppi
        return self._ppi

    def get_available_cash(self) -> float:
        try:
            balances = self._client().account.get_available_balance(self._account_number)
        except Exception as exc:
            raise BrokerError(f"No se pudo obtener el saldo disponible: {exc}") from exc

        for item in _as_list(balances):
            symbol = str(_attr(item, "symbol", _attr(item, "name", "")) or "").upper()
            settlement = str(_attr(item, "settlement", "") or "").upper()
            amount = _attr(item, "amount", 0)
            is_ars = "ARS" in symbol or "PESO" in symbol or symbol in ("$", "")
            if is_ars and settlement == "INMEDIATA" and amount:
                try:
                    return float(amount)
                except (TypeError, ValueError):
                    continue
        return 0.0

    def get_portfolio(self) -> List[Position]:
        try:
            data = self._client().account.get_balance_and_positions(self._account_number)
        except Exception as exc:
            raise BrokerError(f"No se pudo obtener el portafolio: {exc}") from exc

        positions: List[Position] = []
        for group in _safe_list(data, "groupedInstruments"):
            for instrument in _safe_list(group, "instruments"):
                try:
                    positions.append(
                        Position(
                            ticker=_to_display_ticker(_attr(instrument, "ticker", "")),
                            quantity=float(_attr(instrument, "quantity", 0) or 0),
                            avg_price=float(
                                _attr(instrument, "purchasePrice", _attr(instrument, "averagePrice", 0)) or 0
                            ),
                        )
                    )
                except (TypeError, ValueError):
                    continue
        return positions

    def get_quote(self, ticker: str) -> Quote:
        ppi_ticker = _to_ppi_ticker(ticker)
        try:
            data = self._client().marketdata.current(ppi_ticker, _INSTRUMENT_TYPE, _SETTLEMENT)
        except Exception as exc:
            raise BrokerError(f"No se pudo obtener la cotización de {ticker}: {exc}") from exc

        if isinstance(data, list) and data:
            data = data[-1]
        price = _attr(data, "price", None)
        if price is None:
            raise BrokerError(f"Cotización de {ticker} sin precio disponible.")
        return Quote(ticker=ticker, price=float(price))

    def place_market_buy(self, ticker: str, quantity: int) -> tuple[str, Any]:
        """Envía una orden de COMPRA real a mercado. quantity en títulos (no en ARS)."""
        from ppi_client.models.order_budget import OrderBudget
        from ppi_client.models.order_confirm import OrderConfirm
        from ppi_client.models.disclaimer import Disclaimer

        client = self._client()
        ppi_ticker = _to_ppi_ticker(ticker)

        budget_req = OrderBudget(
            self._account_number,
            quantity,
            0,  # a mercado: PPI define el precio
            ppi_ticker,
            _INSTRUMENT_TYPE,
            _QUANTITY_TYPE,
            _MARKET_ORDER,
            _OPERATION_TERM,
            None,
            "COMPRA",
            _SETTLEMENT,
        )
        try:
            budget_resp = client.orders.budget(budget_req)
        except Exception as exc:
            raise BrokerError(f"Fallo el budget de la orden de {ticker}: {exc}") from exc

        disclaimers = []
        if budget_resp and _attr(budget_resp, "disclaimers", None):
            disclaimers = [Disclaimer(d.code, True) for d in _attr(budget_resp, "disclaimers")]

        confirm_req = OrderConfirm(
            self._account_number,
            quantity,
            0,
            ppi_ticker,
            _INSTRUMENT_TYPE,
            _QUANTITY_TYPE,
            _MARKET_ORDER,
            _OPERATION_TERM,
            None,
            "COMPRA",
            _SETTLEMENT,
            disclaimers,
            None,
        )
        try:
            response = client.orders.confirm(confirm_req)
        except Exception as exc:
            raise BrokerError(f"Fallo la confirmación de la orden de {ticker}: {exc}") from exc

        order_id = str(
            _attr(response, "orderId", _attr(response, "id", _attr(response, "orderNumber", "UNKNOWN")))
        )
        return order_id, response


_broker: Optional[PPIBroker] = None


def get_broker() -> PPIBroker:
    """Instancia memoizada del bróker real. Requiere credenciales válidas en .env."""
    global _broker
    if _broker is None:
        _broker = PPIBroker(
            public_key=os.environ.get("PPI_PUBLIC_KEY", ""),
            private_key=os.environ.get("PPI_PRIVATE_KEY", ""),
            account_number=os.environ.get("PPI_ACCOUNT_NUMBER", ""),
            sandbox=os.environ.get("PPI_SANDBOX", "false").strip().lower() == "true",
        )
    return _broker


def _attr(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _as_list(data: Any) -> list:
    return data if isinstance(data, list) else ([data] if data else [])


def _safe_list(data: Any, key: str) -> list:
    val = _attr(data, key, [])
    return val if isinstance(val, list) else []
