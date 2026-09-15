---
name: lectura-mercados
description: Cotización de acciones, índices y otros instrumentos vía la API pública de Yahoo Finance (sin API key) — cualquier ticker, no solo GGAL/YPF/PPI.
version: 1.0.0
author: demo-asesor-financiero
license: MIT

metadata:
  hermes:
    tags: [Finanzas, Mercados, Research]
    requires_tools: [terminal]
---

# Lectura de mercados

Cotización casi en tiempo real de acciones, ETFs e índices vía el endpoint
público de Yahoo Finance — no requiere API key ni cuenta. Es información
general de mercado, **no asesoramiento financiero**, y no ejecuta ninguna
operación (para eso, y solo para GGAL/YPF contra una cuenta real de PPI,
usar la skill `asesor-financiero`, que es un sistema separado).

## When to Use

- El cliente pregunta el precio o la variación del día de una acción,
  ETF o índice puntual (ej. "¿cómo está Apple?", "¿cómo cerró el S&P 500?").
- No uses esta skill para dólar (usar `cotizacion-dolar`) ni para
  criptomonedas (usar `cotizacion-bitcoin`) — esas tienen fuentes más
  específicas y confiables para ese dato.

## Quick Reference

| Instrumento | Ticker de ejemplo |
|---|---|
| Acción (NASDAQ/NYSE) | `AAPL`, `MSFT`, `TSLA` |
| Acción argentina (BYMA, en USD vía ADR/CEDEAR de referencia) | `GGAL`, `YPF` |
| Índice S&P 500 | `%5EGSPC` (`^GSPC` URL-encodeado) |
| Índice Merval | `%5EMERV` |
| ETF | `SPY`, `QQQ` |

Endpoint:
```
GET https://query1.finance.yahoo.com/v8/finance/chart/{TICKER}?interval=1d&range=1d
```

## Procedure

1. Armá la URL con el ticker (URL-encodeando `^` como `%5E` si es un índice).
2. Hacé la consulta con un User-Agent de navegador — el endpoint a veces
   rechaza pedidos sin uno:
   ```bash
   curl -s -A "Mozilla/5.0" \
     "https://query1.finance.yahoo.com/v8/finance/chart/AAPL?interval=1d&range=1d"
   ```
3. Del JSON de respuesta, leé `chart.result[0].meta`:
   - `regularMarketPrice`: precio actual.
   - `regularMarketChangePercent`: variación % del día.
   - `fiftyTwoWeekHigh` / `fiftyTwoWeekLow`: rango de 52 semanas.
   - `currency`, `fullExchangeName`: para aclarar en qué moneda y mercado.
4. Redactá la respuesta en español citando esos datos. No dediques ninguna
   frase a recomendar comprar o vender — es información, no asesoramiento.

**Regla obligatoria: toda respuesta tiene que cerrar siempre con "Fuente:
Yahoo Finance", sin excepción** — nunca la omitas aunque ya se haya
mencionado antes en la conversación.

## Pitfalls

- Si `chart.result` viene vacío o `chart.error` no es `null`, el ticker no
  existe o está mal escrito — decíselo al cliente en vez de inventar datos.
- Los índices necesitan el prefijo `^` (URL-encodeado como `%5E`).
- Fines de semana o feriados: `regularMarketTime` va a ser de la última
  rueda hábil — aclarálo si la fecha implícita no es "hoy".
- No hay endpoint de "panorama general" acá — para varios tickers a la vez,
  repetí la consulta una vez por ticker.

## Verification

La respuesta debe incluir un `regularMarketPrice` numérico y no nulo antes
de redactar cualquier cifra para el cliente.
