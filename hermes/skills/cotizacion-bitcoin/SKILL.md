---
name: cotizacion-bitcoin
description: Precio de Bitcoin (y otras criptomonedas) en USD/ARS/EUR y variación 24hs, vía la API pública de CoinGecko, sin API key.
version: 1.0.0
author: demo-asesor-financiero
license: MIT

metadata:
  hermes:
    tags: [Finanzas, Cripto, Bitcoin]
    requires_tools: [terminal]
---

# Cotización de Bitcoin (y cripto en general)

Precio de Bitcoin y otras criptomonedas vía la API pública y gratuita de
**CoinGecko** — no requiere key para este uso básico. Es información de
mercado, no asesoramiento — y no ejecuta ninguna operación.

## When to Use

El cliente pregunta el precio de Bitcoin u otra criptomoneda ("¿cómo está
el bitcoin?", "¿a cuánto está ethereum en pesos?").

## Quick Reference

```
GET https://api.coingecko.com/api/v3/simple/price
    ?ids={id1},{id2}&vs_currencies={moneda1},{moneda2}&include_24hr_change=true
```

- `ids`: identificador de CoinGecko, no el ticker — `bitcoin` (no `BTC`),
  `ethereum` (no `ETH`). Si no sabés el id de una moneda, buscalo con
  `GET https://api.coingecko.com/api/v3/coins/list` (devuelve
  `id`/`symbol`/`name` de todas).
- `vs_currencies`: `usd`, `ars`, `eur`, etc. — se pueden pedir varias
  separadas por coma en el mismo pedido.

## Procedure

1. Identificá el `id` de CoinGecko de la moneda pedida (`bitcoin` para
   Bitcoin es el caso más común — no hace falta buscarlo).
2. Consultá:
   ```bash
   curl -s "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd,ars&include_24hr_change=true"
   ```
3. Redactá el precio en las monedas pedidas (default: USD si el cliente no
   aclaró) y la variación de las últimas 24hs (`{moneda}_24h_change`).

**Regla obligatoria: toda respuesta tiene que cerrar siempre con "Fuente:
CoinGecko", sin excepción** — nunca la omitas aunque ya se haya mencionado
antes en la conversación.

## Pitfalls

- No confundas el `id` de CoinGecko con el símbolo/ticker — `ids=BTC` no
  funciona, tiene que ser `ids=bitcoin`.
- CoinGecko tiene rate limit en su plan gratuito (~10-30 pedidos/minuto) —
  no repitas la misma consulta varias veces seguidas para "confirmar".
- El precio en ARS es un cruce implícito (USD de CoinGecko × su propio tipo
  de cambio interno) — no es necesariamente el mismo "dólar cripto" que
  devuelve `cotizacion-dolar`; si el cliente pregunta específicamente por
  el dólar cripto, usar esa skill en cambio.
- `simple/price` no devuelve una marca de tiempo — aclará que el valor es
  "al momento de la consulta", no de una hora de cierre específica.

## Verification

El valor devuelto para cada moneda pedida tiene que ser un número positivo
(no `null` ni ausente) antes de comunicárselo al cliente.
