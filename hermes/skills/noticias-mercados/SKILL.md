---
name: noticias-mercados
description: Noticias y titulares recientes de mercados financieros (acciones, tasas, dólar, cripto, economía) vía búsqueda y extracción web — sin API de pago.
version: 1.0.0
author: demo-asesor-financiero
license: MIT

metadata:
  hermes:
    tags: [Finanzas, Noticias, Research]
    requires_tools: [web_search, web_extract]
---

# Noticias de mercados

Resumen de noticias recientes de mercados financieros usando los tools
nativos de búsqueda y extracción web de Hermes — no depende de ninguna API
de noticias de pago ni de una key propia.

## When to Use

- El cliente pide noticias, contexto o "qué está pasando" con un mercado,
  una empresa, una moneda o la economía en general.
- No la uses para pedir *el precio actual* de algo puntual — para eso están
  `lectura-mercados` (acciones/índices), `cotizacion-dolar` y
  `cotizacion-bitcoin`. Esta skill es para contexto y noticias, no cifras
  en tiempo real.

## Quick Reference

Fuentes de referencia para priorizar en los resultados de búsqueda:

| Región | Fuentes |
|---|---|
| Internacional | Reuters, Bloomberg, Financial Times |
| Argentina | Ámbito Financiero, El Cronista, Infobae Economía, La Nación Economía |
| Genérico / mercados | Investing.com, MarketWatch |

## Procedure

1. Armá una búsqueda específica con `web_search`, incluyendo el tema y,
   si el cliente no pidió un país en particular, dejando la búsqueda
   abierta (no asumas Argentina por defecto salvo que el contexto de la
   conversación ya sea sobre pesos/PPI/dólar local).
   Ejemplos de query: `"mercados hoy Wall Street"`, `"dólar blue noticias
   hoy"`, `"Apple earnings news"`.
2. De los resultados, elegí 2-3 que sean de fuentes reconocidas (ver Quick
   Reference) y recientes (preferí resultados con fecha explícita de los
   últimos 1-3 días, salvo que el cliente pida contexto histórico).
3. Usá `web_extract` sobre esos resultados para traer el cuerpo completo
   de la nota en vez de quedarte solo con el título/snippet del buscador.
4. Redactá un resumen en español, 3-5 puntos como máximo, cada uno con su
   fuente y fecha entre paréntesis. No mezcles datos de notas distintas en
   una sola afirmación sin aclarar de cuál viene cada una.

**Regla obligatoria: cada punto del resumen, sin excepción, tiene que
indicar el medio/fuente concreta de donde salió** (ej. "Ámbito Financiero,
12/09") — nunca presentes una cifra o titular sin decir de dónde salió.

## Pitfalls

- No inventes cifras ni titulares que no aparezcan en el contenido
  extraído — si una nota es ambigua o el dato no está claro, decilo en vez
  de completar el hueco vos mismo.
- No cites un solo resultado como si fuera consenso del mercado — si las
  fuentes discrepan, mencionalo.
- Evitá notas de opinión/blogs sin firma editorial cuando haya una fuente
  de las listadas arriba disponible para el mismo tema.
- Esto es contexto informativo, no asesoramiento financiero: no cierres el
  resumen con una recomendación de comprar/vender.

## Verification

Cada punto del resumen final tiene que poder rastrearse a una fuente y
fecha concretas que hayas visto en el contenido extraído — si no podés
señalar de dónde salió un dato, no lo incluyas.
