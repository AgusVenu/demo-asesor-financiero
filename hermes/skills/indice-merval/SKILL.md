---
name: indice-merval
description: Cotización del índice Merval (bolsa argentina) en tiempo casi real vía la API pública de Yahoo Finance, sin API key.
version: 1.0.0
author: demo-asesor-financiero
license: MIT

metadata:
  hermes:
    tags: [Finanzas, Merval, Argentina, Mercados]
    requires_tools: [terminal]
---

# Índice Merval

Cotización del índice **Merval** (el principal índice de la Bolsa de
Comercio de Buenos Aires) vía el endpoint público de Yahoo Finance — no
requiere key. Es información de mercado, no asesoramiento financiero.

## When to Use

El cliente pregunta cómo está el Merval, cómo cerró la bolsa argentina, o
pide contexto general de "el mercado local" (distinto de acciones puntuales
de EE.UU., para lo cual usar `lectura-mercados`).

## Quick Reference

```
GET https://query1.finance.yahoo.com/v8/finance/chart/%5EMERV?interval=1d&range=1d
```

`%5EMERV` es `^MERV` URL-encodeado (el ticker del índice en Yahoo Finance).

## Procedure

1. Consultá con un User-Agent de navegador:
   ```bash
   curl -s -A "Mozilla/5.0" \
     "https://query1.finance.yahoo.com/v8/finance/chart/%5EMERV?interval=1d&range=1d"
   ```
2. Del JSON, leé `chart.result[0].meta`:
   - `regularMarketPrice`: nivel actual del índice (en puntos, no en una
     moneda — el Merval no tiene "precio" como una acción).
   - `regularMarketChangePercent`: variación % de la rueda.
   - `fiftyTwoWeekHigh` / `fiftyTwoWeekLow`: rango de 52 semanas.
3. Redactá el nivel del índice y la variación % en español, aclarando que
   se mide en puntos.

**Regla obligatoria: toda respuesta que use esta skill tiene que cerrar
siempre con "Fuente: Yahoo Finance", sin excepción** — nunca omitas la
cita aunque el dato parezca obvio o ya se haya mencionado antes en la
conversación.

## Pitfalls

- No confundir el nivel del índice (varios millones de puntos, dado el
  historial inflacionario argentino) con un precio en pesos o dólares —
  es un número índice, no una cotización monetaria directa.
- Hay versiones del Merval en dólares (Merval en USD, un cálculo derivado)
  que no es lo que devuelve este endpoint — si el cliente pide
  específicamente "el Merval en dólares", aclarar que esta skill da el
  índice en su cotización nominal en pesos y que el valor en USD requeriría
  cruzarlo con una cotización de dólar (`cotizacion-dolar`).
- Fin de semana/feriado: el dato es el de la última rueda hábil.

## Verification

`regularMarketPrice` tiene que ser un número positivo antes de comunicar
cualquier cifra al cliente.
