---
name: cotizacion-dolar
description: Cotización del dólar en Argentina (oficial, blue, MEP, CCL, cripto, mayorista, tarjeta) en tiempo real vía la API pública dolarapi.com, sin API key.
version: 1.0.0
author: demo-asesor-financiero
license: MIT

metadata:
  hermes:
    tags: [Finanzas, Dólar, Argentina]
    requires_tools: [terminal]
---

# Cotización del dólar (Argentina)

Cotizaciones del dólar en Argentina vía **dolarapi.com**, una API pública y
gratuita que no requiere key ni autenticación. Es información de mercado,
no asesoramiento — y no ejecuta ninguna operación.

## When to Use

El cliente pregunta "a cuánto está el dólar", "dólar blue hoy", "dólar
oficial", "cuánto está el MEP/CCL", etc.

## Quick Reference

| Endpoint | Devuelve |
|---|---|
| `GET https://dolarapi.com/v1/dolares` | Todas las cotizaciones (array) |
| `GET https://dolarapi.com/v1/dolares/oficial` | Solo oficial |
| `GET https://dolarapi.com/v1/dolares/blue` | Solo blue |
| `GET https://dolarapi.com/v1/dolares/bolsa` | MEP |
| `GET https://dolarapi.com/v1/dolares/contadoconliqui` | CCL |
| `GET https://dolarapi.com/v1/dolares/cripto` | Dólar cripto |
| `GET https://dolarapi.com/v1/dolares/mayorista` | Mayorista |
| `GET https://dolarapi.com/v1/dolares/tarjeta` | Tarjeta/turista |

Cada respuesta trae `compra`, `venta` y `fechaActualizacion` (ISO 8601,
UTC).

## Procedure

1. Si el cliente no especifica el tipo de dólar, consultá **oficial y
   blue** (los dos más pedidos) con:
   ```bash
   curl -s https://dolarapi.com/v1/dolares/oficial
   curl -s https://dolarapi.com/v1/dolares/blue
   ```
   Si menciona un tipo puntual (MEP, CCL, cripto, mayorista, tarjeta),
   consultá directamente ese endpoint. Para un panorama completo, usá
   `https://dolarapi.com/v1/dolares` (trae todos en un solo pedido).
2. Redactá la respuesta con compra y venta de cada tipo consultado, y la
   hora de `fechaActualizacion` convertida a un formato legible (aclarando
   que es hora UTC si no la convertís).
3. Cerrá citando la fuente: "Fuente: dolarapi.com." (o "Fuente:
   bluelytics.com.ar" si se usó el fallback).

**Regla obligatoria: siempre citar la fuente/API exacta usada al final de
la respuesta, sin excepción** — nunca la omitas aunque ya se haya
mencionado antes en la conversación.

## Pitfalls

- No confundas `compra` (lo que te pagan si vendés dólares) con `venta`
  (lo que pagás si comprás) — aclarar ambos valores evita el error.
- Si `fechaActualizacion` tiene más de un día de antigüedad, aclarale al
  cliente que el dato puede estar desactualizado en vez de presentarlo
  como si fuera de la rueda actual.
- Si `dolarapi.com` no responde (timeout o error de red), usar como
  fallback `https://api.bluelytics.com.ar/v2/latest` (misma idea, formato
  de campos distinto: `oficial.value_buy/value_sell`,
  `blue.value_buy/value_sell`) y aclarar en la respuesta que se usó una
  fuente alternativa.
- No es la cotización a usar para operar GGAL/YPF en PPI — esa la resuelve
  `buy_stock` re-cotizando directo contra el bróker, no esta skill.

## Verification

`compra` y `venta` tienen que ser números positivos y `venta >= compra`;
si no, tratá la respuesta como inválida y probá el fallback.
