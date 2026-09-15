---
name: inflacion-argentina
description: Inflación mensual (IPC) e interanual de Argentina, histórica y últimos datos, vía la API pública ArgentinaDatos, sin API key.
version: 1.0.0
author: demo-asesor-financiero
license: MIT

metadata:
  hermes:
    tags: [Finanzas, Inflación, Argentina]
    requires_tools: [terminal]
---

# Inflación en Argentina (IPC)

Serie histórica y último dato de inflación (IPC) de Argentina vía la API
pública y gratuita **ArgentinaDatos** — no requiere key. Es información
estadística, no asesoramiento financiero.

## When to Use

El cliente pregunta por la inflación de un mes puntual, la inflación
interanual, o pide un panorama ("¿cómo viene la inflación?", "¿cuánto dio
el IPC del mes pasado?").

## Quick Reference

| Endpoint | Devuelve |
|---|---|
| `GET https://api.argentinadatos.com/v1/finanzas/indices/inflacion` | Serie mensual completa (`fecha`, `valor` = % mensual) |
| `GET https://api.argentinadatos.com/v1/finanzas/indices/inflacionInteranual` | Serie interanual completa (`fecha`, `valor` = % i.a.) |

Ambos devuelven un array ordenado por fecha ascendente — el último
elemento es el dato más reciente disponible.

## Procedure

1. Pedí ambas series si el cliente no fue específico:
   ```bash
   curl -s https://api.argentinadatos.com/v1/finanzas/indices/inflacion
   curl -s https://api.argentinadatos.com/v1/finanzas/indices/inflacionInteranual
   ```
2. Tomá el último elemento de cada array para el dato más reciente. Si el
   cliente pide un mes puntual o una serie ("los últimos 6 meses"), filtrá
   por `fecha` en vez de traer todo el historial a la respuesta.
3. Redactá el mes/valor (mensual) y el acumulado interanual, aclarando que
   `fecha` es el último día del mes que mide el dato.

**Regla obligatoria: toda respuesta tiene que cerrar siempre con "Fuente:
ArgentinaDatos (en base a datos de INDEC)", sin excepción** — nunca la
omitas aunque ya se haya mencionado antes en la conversación.

## Pitfalls

- El dato del mes más reciente puede no estar publicado todavía (INDEC
  publica con unas semanas de rezago) — si el último elemento del array es
  de hace más de ~45 días respecto a hoy, aclarale al cliente que ese es
  el último dato disponible, no necesariamente el del mes en curso.
- No confundas la serie mensual (variación % respecto al mes anterior) con
  la interanual (variación % respecto al mismo mes del año anterior) — son
  dos endpoints distintos, no lo mismo con otro formato.
- No es una fuente de tipo de cambio ni de tasas — para eso usar
  `cotizacion-dolar` y `tasas-interes-argentina` respectivamente.

## Verification

El `valor` del último elemento de cada serie tiene que ser un número (puede
ser negativo en un mes de deflación, pero no `null` ni ausente).
