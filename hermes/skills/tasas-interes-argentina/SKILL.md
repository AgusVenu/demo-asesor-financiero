---
name: tasas-interes-argentina
description: Tasas de interés de plazo fijo por banco en Argentina (TNA), vía la API pública ArgentinaDatos (datos BCRA), sin API key.
version: 1.0.0
author: demo-asesor-financiero
license: MIT

metadata:
  hermes:
    tags: [Finanzas, Tasas, Argentina]
    requires_tools: [terminal]
---

# Tasas de interés (plazo fijo) en Argentina

Tasas de interés (TNA) de plazo fijo por entidad bancaria en Argentina, vía
la API pública y gratuita **ArgentinaDatos** (que a su vez toma datos del
BCRA) — no requiere key. Es información de mercado, no asesoramiento sobre
dónde invertir.

## When to Use

El cliente pregunta qué tasa paga un plazo fijo, qué banco paga más, o
compara tasas entre entidades ("¿qué tasa de plazo fijo me conviene?",
"¿cuánto paga el Nación a 30 días?").

## Quick Reference

```
GET https://api.argentinadatos.com/v1/finanzas/tasas/plazoFijo
```

Devuelve un array con un objeto por entidad bancaria:
- `entidad`: nombre del banco.
- `tnaClientes` / `tnaNoClientes`: tasa nominal anual general.
- `tasas[]`: desglose por plazo (`plazoMinDias`, `plazoMaxDias`, `tna`,
  y opcionalmente `montoMinimo`/`montoMaximo` si la tasa depende del
  monto).

## Procedure

1. Traé el listado completo:
   ```bash
   curl -s https://api.argentinadatos.com/v1/finanzas/tasas/plazoFijo
   ```
2. Si el cliente pregunta por un banco puntual, filtrá por `entidad`
   (nombres en mayúsculas, ej. `"BANCO DE LA NACION ARGENTINA"`,
   `"BANCO DE GALICIA Y BUENOS AIRES S.A."`).
3. Si pregunta "qué banco paga más" para un plazo dado (ej. 30 días),
   recorré todas las entidades, mirá el `tna` del rango de `tasas[]` que
   incluya ese plazo, y ordená de mayor a menor antes de responder.
4. Redactá la TNA en % (el campo viene como fracción — `0.1975` es 19,75%
   anual, no 0,1975%).

**Regla obligatoria: toda respuesta tiene que cerrar siempre con "Fuente:
ArgentinaDatos (BCRA)", sin excepción** — nunca la omitas aunque ya se
haya mencionado antes en la conversación.

## Pitfalls

- El campo `tna` viene como fracción decimal (`0.23` = 23% anual) — hay
  que multiplicar por 100 antes de mostrarlo, si no la cifra queda mal por
  dos órdenes de magnitud.
- `tnaClientes` (tasa para clientes de esa entidad) puede diferir bastante
  de `tnaNoClientes` — aclarar cuál corresponde si el cliente no dice si
  ya es cliente del banco.
- No es la tasa de política monetaria del BCRA ni un rendimiento de bonos —
  es específicamente plazo fijo bancario tradicional.
- No recomiendes un banco en particular como "el mejor" en términos
  generales — limitate a reportar las tasas, la decisión es del cliente.

## Verification

Cada `tna` reportado tiene que salir de un objeto `tasas[]` cuyo rango
(`plazoMinDias`-`plazoMaxDias`) efectivamente incluya el plazo que pidió el
cliente — no uses la `tnaClientes` general si el cliente pidió un plazo
específico y hay una tasa más precisa para ese rango.
