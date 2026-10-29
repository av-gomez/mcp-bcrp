# De dónde salen las verdades de las 2 preguntas nuevas

Las dos cifras se leyeron en la tabla HTML de estadisticas.bcrp.gob.pe (no con el MCP `bcrp`), el 28 de octubre de 2026.

| id | Serie | Periodo | Valor en la web | Tolerancia | Link exacto |
|---|---|---|---|---|---|
| `wti_set26` | PN01660XM · Cotizaciones de productos (promedio del periodo) - Petróleo - WTI (US$ por barriles) | Sep26 | 97 | 1 | <https://estadisticas.bcrp.gob.pe/estadisticas/series/mensuales/resultados/PN01660XM/html/2026-1/2026-9/> |
| `ipc_ae_set26` | PN09819PM · Índice de precios Lima Metropolitana (var% 12 meses) - IPC Alimentos y Energía | Sep26 | 4.59 | 0.05 | <https://estadisticas.bcrp.gob.pe/estadisticas/series/mensuales/resultados/PN09819PM/html/2026-1/2026-9/> |

Por qué esas tolerancias:

- **WTI:** la web muestra el precio redondeado a entero (97), así que el valor real está entre 96.5 y 97.5. Una
  tolerancia de 1 US$ cubre ese redondeo.
- **IPC Alimentos y Energía:** es un porcentaje con dos decimales en la web. Uso 0.05, como pide la guía.
