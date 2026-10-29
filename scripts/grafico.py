"""Dibuja grafico.png: aciertos, errores y «no sé» por modo, a partir de resultados.csv.

    uv run scripts/grafico.py
"""
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

AQUI = Path(__file__).parent.parent  # la raíz del proyecto
ORDEN = ["acierta", "se equivoca", "no sabe"]
COLORES = {"acierta": "#2a9d8f", "se equivoca": "#e76f51", "no sabe": "#9aa5b1"}

# Conteo de cada resultado por modo, con las tres columnas aunque alguna tenga cero
res = pd.read_csv(AQUI / "resultados.csv")
tabla = res.groupby("modo").resultado.value_counts().unstack(fill_value=0).reindex(columns=ORDEN, fill_value=0)

# Barras apiladas horizontales: una barra por modo
fig, ax = plt.subplots(figsize=(7, 2.8))
izquierda = pd.Series(0, index=tabla.index)
for resultado in ORDEN:
    ax.barh(tabla.index, tabla[resultado], left=izquierda, color=COLORES[resultado], label=resultado)
    for modo, n in tabla[resultado].items():
        if n > 0:
            ax.text(izquierda[modo] + n / 2, modo, str(n), ha="center", va="center", color="white", fontweight="bold")
    izquierda = izquierda + tabla[resultado]

# Títulos y leyenda
ax.set_xlabel(f"preguntas (de {len(res.id.unique())})")
ax.set_title("Claude (Haiku) sin herramientas vs. con el MCP del BCRP", loc="left")
ax.legend(ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.35), frameon=False)
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig(AQUI / "grafico.png", dpi=150, bbox_inches="tight")
print(tabla)
