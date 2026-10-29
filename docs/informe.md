# Informe · ¿Inventa cifras Claude? Memoria contra el MCP del BCRP

Evaluación con `uv run evaluar.py` (Claude Haiku, 10 preguntas, modos `memoria` y `mcp`), el 28 de octubre de 2026.
Las 8 primeras preguntas vienen con el proyecto; `wti_set26` e `ipc_ae_set26` son nuestras (verdades en
[verdades.md](verdades.md)).

## Resultados

| Modo | Acierta | Se equivoca | No sabe | Segundos promedio |
|---|---:|---:|---:|---:|
| memoria | 0 | 0 | 10 | 7.0 |
| mcp | 10 | 0 | 0 | 14.7 |

![Aciertos, errores y «no sé» por modo](grafico.png)

## Qué falló cada modo y por qué

- **memoria · falló las 10 (todas «no sé»).** La columna `fuente` explica el motivo en todos los casos: no tiene
  internet ni herramientas («la única herramienta disponible es la de salida estructurada»), y las cifras son
  posteriores a lo que el modelo conoce («mi conocimiento llega hasta junio de 2026»). Como la instrucción le permite
  responder `null`, prefiere no estimar. Esto pasa incluso con cifras antiguas como `ipc_mar25` o `pbi_2025`: no las
  recuerda con la precisión que pide la tolerancia.
- **mcp · no falló ninguna.** En cada `fuente` cita el código de serie, el periodo y la URL de la API del BCRP, por
  ejemplo «BCRP, serie PN01660XM (…Petróleo - WTI…), periodo 2026-09 (valor 97,0982…)». Hizo de 4 a 6 turnos por
  pregunta (`buscar_series` y luego `serie` o `resumen`). En `rin_ago26` además contrastó la serie con otra
  (PN06481IM) antes de responder. El costo es el tiempo: el doble que memoria (14.7 s contra 7.0 s).

## Experimento extra · sin salida fácil

Quitamos de `INSTRUCCION` la frase «Si no puedes saberlo con certeza, pon valor null: no estimes.» y volvimos a correr
([experimento/resultados_sin_null.csv](experimento/resultados_sin_null.csv); la corrida base quedó en [experimento/resultados_base.csv](experimento/resultados_base.csv) y en [resultados.csv](../resultados.csv)).

| Modo | Acierta | Se equivoca | No sabe | Segundos promedio |
|---|---:|---:|---:|---:|
| memoria | 0 | **1** | 9 | 7.5 |
| mcp | 10 | 0 | 0 | 14.4 |

Sin el permiso explícito para decir «no sé», memoria **inventó una cifra**: para `ipc_mar25` respondió 0.21 % cuando el
dato oficial es 0.81 %. En `fuente` lo admitió («Estimación de memoria, no verificada: INEI, Nota de prensa…»), pero el
número en `valor` es un error que un usuario podría copiar. Las otras 9 siguieron en `null`. Con el MCP la frase no
cambia nada, porque el modelo no necesita estimar.

## Dos cifras del MCP comprobadas en la web del BCRP

| Cifra del MCP | Herramienta | Valor en la web | Link de la tabla |
|---|---|---|---|
| TC interbancario venta, 15 oct 2026 (PD04638PD): 3.42821 | `serie` | 3.428 (15Oct26) | <https://estadisticas.bcrp.gob.pe/estadisticas/series/diarias/resultados/PD04638PD/html/2026-10-14/2026-10-16/> |
| TC interbancario venta promedio, ago 2026 (PN01206PM): 3.3685 | `comparar_series` | 3.368 (Ago26) | <https://estadisticas.bcrp.gob.pe/estadisticas/series/mensuales/resultados/PN01206PM/html/2026-7/2026-9/> |

Ambas coinciden hasta el redondeo de la web (3 decimales).

## Conclusión

Para cifras oficiales recientes, el modelo solo no sirve: en el mejor caso dice «no sé», y si se le quita esa salida
puede inventar un número. Un MCP vale la pena cuando la misma fuente se consulta muchas veces, la precisión importa y
hay cálculos de por medio (variaciones, promedios, correlaciones). Ahí da 10 de 10, con código, periodo y URL que se
pueden auditar, y las cuentas las hace Python. La búsqueda web basta para preguntas aisladas o fuentes que no tienen
API, pero es más lenta y depende de encontrar la página correcta y leerla bien. El costo del MCP es construirlo y
mantenerlo, y el doble de tiempo que responder de memoria.
