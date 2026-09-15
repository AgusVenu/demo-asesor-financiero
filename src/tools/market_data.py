"""Tool de research de mercado: cotizaciones reales vía Yahoo Finance (yfinance)."""
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import yfinance as yf
from langchain_core.tools import tool

# Tickers usados para armar un panorama general cuando el cliente pregunta por
# "las principales acciones" en vez de un ticker puntual.
MAIN_TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META", "MELI"]


def _fetch_snapshot(ticker: str) -> dict:
    ticker = ticker.upper().strip()
    info = dict(yf.Ticker(ticker).fast_info)
    last = info.get("lastPrice")
    if last is None:
        raise ValueError(f"No se pudo obtener una cotización para {ticker}")
    prev = info.get("previousClose") or info.get("regularMarketPreviousClose")
    fifty = info.get("fiftyDayAverage")
    two_hundred = info.get("twoHundredDayAverage")
    year_low = info.get("yearLow")
    year_high = info.get("yearHigh")
    change_pct = ((last - prev) / prev * 100) if prev else None

    return {
        "ticker": ticker,
        "last_price": round(last, 2),
        "change_pct": round(change_pct, 2) if change_pct is not None else None,
        "fifty_day_avg": round(fifty, 2) if fifty else None,
        "two_hundred_day_avg": round(two_hundred, 2) if two_hundred else None,
        "year_low": round(year_low, 2) if year_low else None,
        "year_high": round(year_high, 2) if year_high else None,
        "source": "Yahoo Finance",
    }


@tool
def get_market_snapshot(ticker: str) -> dict:
    """Devuelve una foto del mercado para un ticker: precio actual, variación del
    día, promedios móviles de 50 y 200 días, y el rango de las últimas 52 semanas.
    Usar siempre que el cliente pregunte por una acción puntual."""
    return _fetch_snapshot(ticker)


@tool
def get_market_overview() -> list:
    """Devuelve un panorama (precio y variación % del día) de un puñado de las
    principales acciones del mercado (AAPL, MSFT, GOOGL, AMZN, TSLA, NVDA, META,
    MELI). Usar cuando el cliente pregunte en general por "el mercado" o "las
    principales acciones", sin mencionar un ticker puntual — para un ticker
    específico usar `get_market_snapshot` en su lugar."""
    results = []
    with ThreadPoolExecutor(max_workers=len(MAIN_TICKERS)) as pool:
        futures = {pool.submit(_fetch_snapshot, ticker): ticker for ticker in MAIN_TICKERS}
        for future, ticker in futures.items():
            try:
                results.append(future.result())
            except Exception as exc:
                results.append({"ticker": ticker, "error": str(exc)})
    order = {ticker: i for i, ticker in enumerate(MAIN_TICKERS)}
    results.sort(key=lambda item: order[item["ticker"]])
    return results


def detect_opportunity(snapshot: dict) -> Optional[str]:
    """Heurística simple e ilustrativa para el demo — NO es asesoramiento financiero real."""
    last = snapshot.get("last_price")
    fifty = snapshot.get("fifty_day_avg")
    two_hundred = snapshot.get("two_hundred_day_avg")
    year_low = snapshot.get("year_low")

    if last and fifty and two_hundred and fifty > two_hundred and last < fifty * 0.95:
        return "la tendencia de mediano plazo es alcista, pero el precio retrocedió más de un 5% respecto de su promedio de 50 días"
    if last and year_low and last <= year_low * 1.05:
        return "el precio está a menos de un 5% de su mínimo de las últimas 52 semanas"
    return None
