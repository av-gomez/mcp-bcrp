"""Servidor MCP del BCRP. Empiecen aquí: buscar_series ya funciona; completen los TODO hasta que pasen las pruebas.

    uv run pytest                                           # el contrato: las 8 pruebas deben pasar
    uv run server.py                                        # el servidor, por stdio
    claude mcp add --scope project bcrp -- uv run server.py # conectarlo a Claude Code

Las cuentas las hace Python, no el modelo: así cada cifra sale de una llamada que se puede repetir.
"""
import itertools
import json
import re
import time
import unicodedata
from functools import cache
from pathlib import Path

import httpx
import pandas as pd
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

AQUI = Path(__file__).parent
CATALOGO = AQUI / "datos" / "catalogo_bcrp.csv"
URL_CATALOGO = "https://estadisticas.bcrp.gob.pe/estadisticas/series/metadata"
API = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api"
WEB = "https://estadisticas.bcrp.gob.pe/estadisticas/series"
CACHE_API = AQUI / "datos" / "api"
SOLO_LECTURA = {"readOnlyHint": True, "openWorldHint": True}

mcp = FastMCP("bcrp", instructions=(
    "Series oficiales del Banco Central de Reserva del Perú (BCRP). Primero busca el código con buscar_series; "
    "luego usa resumen para variaciones, promedios y extremos, y serie para los datos. No calcules a mano: "
    "cita siempre el código de la serie y el periodo."))


def _sin_tildes(s):
    return unicodedata.normalize("NFD", str(s).lower()).encode("ascii", "ignore").decode()


@cache
def catalogo():
    """El catálogo oficial: 17 mil series en unos 7 MB. Se baja una vez y queda en datos/."""
    if not CATALOGO.exists():
        CATALOGO.parent.mkdir(exist_ok=True)
        r = httpx.get(URL_CATALOGO, timeout=120)
        r.raise_for_status()
        CATALOGO.write_text(r.content.decode("latin-1"), encoding="utf-8")
    df = pd.read_csv(CATALOGO, sep=";", dtype=str).fillna("")
    df = df.rename(columns={"Código de serie": "codigo", "Categoría de serie": "categoria", "Grupo de serie": "grupo",
                            "Nombre de serie": "nombre", "Frecuencia": "frecuencia",
                            "Fecha de actualización": "actualizada", "Fecha de inicio": "inicio"})
    df["texto"] = (df.categoria + " " + df.grupo + " " + df.nombre).map(_sin_tildes)
    return df


def _ficha(codigo):
    fila = catalogo().query("codigo == @codigo")
    if fila.empty:
        raise ToolError(f"No existe el código de serie {codigo!r}. Búsquenlo con buscar_series.")
    f = fila.iloc[0]
    return {"codigo": f.codigo, "nombre": f"{f.grupo} - {f.nombre}", "categoria": f.categoria,
            "frecuencia": f.frecuencia, "inicio": f.inicio, "actualizada": f.actualizada}


@mcp.tool(annotations=SOLO_LECTURA)
def buscar_series(texto: str, frecuencia: str | None = None, limite: int = 10) -> list[dict]:
    """Busca series del BCRP por palabras: todas deben aparecer en la categoría, el grupo o el nombre.

    Ejemplos: "ipc 12 meses", "tipo de cambio interbancario venta", "reservas internacionales netas",
    "tasa de referencia", "cobre precio". frecuencia: "Diaria", "Mensual", "Trimestral" o "Anual".
    Devuelve el código, el nombre completo, la frecuencia y desde cuándo hay datos. Si no hay resultados,
    prueben con menos palabras.
    """
    df = catalogo()
    m = pd.Series(True, index=df.index)
    for palabra in _sin_tildes(texto).split():
        m &= df.texto.str.contains(re.escape(palabra))
    if frecuencia:
        m &= df.frecuencia.str.lower() == frecuencia.lower()
    # primero las series vigentes y, entre ellas, las de nombre más corto (las más generales)
    sel = df[m]
    orden = sel.assign(vieja=sel.actualizada < "2025", largo=(sel.grupo + sel.nombre).str.len())
    return [_ficha(c) for c in orden.sort_values(["vieja", "largo"]).head(limite).codigo]


# --- TODO 1 · serie --------------------------------------------------------------------------------------------------

# Meses tal como los escribe la API: el mensual usa "Sep" y el diario "Set" para setiembre
MESES = {"Ene": "01", "Feb": "02", "Mar": "03", "Abr": "04", "May": "05", "Jun": "06", "Jul": "07", "Ago": "08",
         "Sep": "09", "Set": "09", "Oct": "10", "Nov": "11", "Dic": "12"}
# Carpeta de la página web de cada frecuencia, para dar un link que una persona pueda abrir
CARPETA_WEB = {"Diaria": "diarias", "Mensual": "mensuales", "Trimestral": "trimestrales", "Anual": "anuales"}


def _anio(aa):
    """Los periodos diarios y trimestrales traen el año con dos cifras: 97 es 1997 y 26 es 2026."""
    n = int(aa)
    if n > 50:
        return str(1900 + n)
    return str(2000 + n)


def _periodo(nombre):
    """Pasa el nombre de la API a un periodo ISO: Ene.2025 -> 2025-01, 01.Oct.26 -> 2026-10-01, T1.25 -> 2025-T1."""
    if m := re.fullmatch(r"(\d{2})\.(\w{3})\.(\d{2})", nombre):
        return f"{_anio(m[3])}-{MESES[m[2]]}-{m[1]}"
    if m := re.fullmatch(r"(\w{3})\.(\d{4})", nombre):
        return f"{m[2]}-{MESES[m[1]]}"
    if m := re.fullmatch(r"T(\d)\.(\d{2})", nombre):
        return f"{_anio(m[2])}-T{m[1]}"
    return nombre


def _fecha_api(fecha, frecuencia):
    """Pasa una fecha del usuario al formato que pide la API: 2025-1 (mensual y trimestral), 2025-01-15 o 2025."""
    anio, _, resto = str(fecha).partition("-")
    if frecuencia == "Diaria":
        return fecha
    if frecuencia == "Anual" or not resto:
        return anio
    # "2025-01" -> "2025-1" y "2025-T1" -> "2025-1"
    numero = int(resto.split("-")[0].lstrip("T"))
    return f"{anio}-{numero}"


def _descargar(url):
    """Baja el JSON de la API con caché en disco (un día) y reintenta con espera si la API responde HTML."""
    CACHE_API.mkdir(parents=True, exist_ok=True)
    archivo = CACHE_API / (re.sub(r"[^\w.-]", "_", url.removeprefix(API + "/")) + ".json")
    # 1. Si ya lo bajamos hace menos de un día, lo leemos del disco
    if archivo.exists() and time.time() - archivo.stat().st_mtime < 86400:
        return json.loads(archivo.read_text(encoding="utf-8"))
    # 2. Si no, lo pedimos; cuando la API limita pedidos devuelve HTML, así que esperamos y reintentamos
    for intento in range(5):
        try:
            r = httpx.get(url, timeout=60)
            datos = r.json()
        except (httpx.HTTPError, ValueError):
            time.sleep(2 * (intento + 1))
            continue
        archivo.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
        return datos
    raise ToolError(f"El BCRP no respondió con datos para {url}. Esperen unos segundos y reintenten.")


def _serie(codigo, desde, hasta):
    """Lógica de la herramienta serie, separada para que resumen y comparar_series la reutilicen."""
    # La ficha valida el código (ToolError con el código si no existe) y da la frecuencia
    ficha = _ficha(codigo)
    frecuencia = ficha["frecuencia"]
    url = f"{API}/{codigo}/json/{_fecha_api(desde, frecuencia)}/{_fecha_api(hasta, frecuencia)}"
    respuesta = _descargar(url)
    # Cada periodo trae una lista de valores (uno por serie pedida); saltamos los "n.d."
    datos = []
    for p in respuesta.get("periods", []):
        valor = p["values"][0]
        if valor == "n.d.":
            continue
        datos.append({"periodo": _periodo(p["name"]), "valor": float(valor)})
    return {"codigo": codigo, "nombre": ficha["nombre"], "frecuencia": frecuencia, "datos": datos, "fuente": url}


@mcp.tool(annotations=SOLO_LECTURA)
def serie(codigo: str, desde: str, hasta: str) -> dict:
    """Descarga los datos de una serie del BCRP entre dos fechas, con la URL de la fuente.

    Fechas: "2025-01" (mensual), "2025-01-15" (diaria), "2025-T1" (trimestral) o "2025" (anual).
    Ejemplo: codigo="PN01273PM", desde="2026-01", hasta="2026-09". Los periodos salen como "2025-01",
    "2026-10-01", "2025-T1" o "2025". Para variaciones, promedios o extremos usen resumen.
    """
    return _serie(codigo, desde, hasta)


# --- TODO 2 · resumen ------------------------------------------------------------------------------------------------

@mcp.tool(annotations=SOLO_LECTURA)
def resumen(codigo: str, desde: str, hasta: str) -> dict:
    """Resume una serie del BCRP: primero, último, cambio, variación %, promedio, máximo y mínimo (con su periodo).

    Úsenla en vez de hacer cuentas a mano. Ejemplo: codigo="PN01273PM", desde="2025-12", hasta="2026-09".
    """
    s = _serie(codigo, desde, hasta)
    datos = s["datos"]
    if not datos:
        raise ToolError(f"La serie {codigo} no tiene datos entre {desde} y {hasta}.")
    # Extremos del periodo y sus estadísticas
    primero = datos[0]
    ultimo = datos[-1]
    cambio = ultimo["valor"] - primero["valor"]
    variacion = None
    if primero["valor"] != 0:
        variacion = round(cambio / abs(primero["valor"]) * 100, 4)
    return {"codigo": codigo, "nombre": s["nombre"], "frecuencia": s["frecuencia"], "n": len(datos),
            "primero": primero, "ultimo": ultimo, "cambio": round(cambio, 4), "variacion_pct": variacion,
            "promedio": round(sum(d["valor"] for d in datos) / len(datos), 4),
            "maximo": max(datos, key=lambda d: d["valor"]), "minimo": min(datos, key=lambda d: d["valor"]),
            "fuente": s["fuente"]}


# --- TODO 3 · comparar_series ----------------------------------------------------------------------------------------

def _redondear(x, cifras):
    """Redondea y cambia NaN o infinito (una serie constante o que parte de cero) por None, que sí es JSON."""
    if pd.isna(x) or abs(x) == float("inf"):
        return None
    return round(float(x), cifras)


@mcp.tool(annotations=SOLO_LECTURA)
def comparar_series(codigos: list[str], desde: str, hasta: str) -> dict:
    """Compara dos o más series del BCRP de la misma frecuencia: datos alineados, variación % y correlación.

    Úsenla para ver si dos indicadores se mueven juntos, por ejemplo si el precio del petróleo (PN01660XM)
    acompaña al tipo de cambio interbancario (PN01206PM) o a la inflación (PN01273PM). Devuelve los datos
    alineados por periodo (solo los periodos que tienen todas), la variación % de cada serie entre el primer y
    el último periodo común, la correlación de Pearson entre cada par (en niveles y en cambios de un periodo
    a otro) y la URL de fuente de cada serie. Todas deben tener la misma frecuencia.
    Ejemplo: codigos=["PN01660XM", "PN01206PM", "PN01273PM"], desde="2025-01", hasta="2026-09".
    """
    codigos = list(dict.fromkeys(codigos))
    if len(codigos) < 2:
        raise ToolError("Pasen al menos dos códigos distintos.")
    # 1. Validar códigos (ToolError si alguno no existe) y frecuencias antes de bajar nada
    fichas = [_ficha(c) for c in codigos]
    frecuencias = {f["codigo"]: f["frecuencia"] for f in fichas}
    if len(set(frecuencias.values())) > 1:
        raise ToolError(f"Las frecuencias no coinciden: {frecuencias}. Elijan series de la misma frecuencia.")
    # 2. Bajar cada serie con serie y alinearlas por periodo (solo los periodos comunes)
    series = [_serie(c, desde, hasta) for c in codigos]
    tabla = pd.DataFrame({s["codigo"]: {d["periodo"]: d["valor"] for d in s["datos"]} for s in series})
    tabla = tabla.dropna().sort_index()
    if len(tabla) < 3:
        raise ToolError(f"Solo hay {len(tabla)} periodos con datos en todas las series; amplíen el rango.")
    # 3. Variación % entre el primer y el último periodo común
    variacion = (tabla.iloc[-1] - tabla.iloc[0]) / tabla.iloc[0].abs() * 100
    # 4. Correlación de cada par, en niveles y en cambios de un periodo al siguiente
    en_niveles = tabla.corr()
    en_cambios = tabla.diff().corr()
    pares = []
    for a, b in itertools.combinations(codigos, 2):
        pares.append({"a": a, "b": b, "r_niveles": _redondear(en_niveles.loc[a, b], 3),
                      "r_cambios": _redondear(en_cambios.loc[a, b], 3)})
    return {"frecuencia": fichas[0]["frecuencia"], "desde": tabla.index[0], "hasta": tabla.index[-1],
            "series": {s["codigo"]: s["nombre"] for s in series},
            "datos": [{"periodo": p, **fila.round(4).to_dict()} for p, fila in tabla.iterrows()],
            "variacion_pct": {c: _redondear(v, 2) for c, v in variacion.items()},
            "correlacion": pares,
            "fuentes": {s["codigo"]: s["fuente"] for s in series}}


# --- TODO 4 · recursos -----------------------------------------------------------------------------------------------

# Series de energía con códigos reales encontrados con buscar_series
ENERGIA = {"petroleo": ["PN01660XM", "PD04705XD"],
           "tipo_de_cambio_interbancario": ["PN01206PM", "PD04638PD"],
           "precios": ["PN01273PM", "PN09819PM", "PN01443PM"]}


@mcp.resource("bcrp://serie/{codigo}", mime_type="application/json")
def ficha_serie(codigo: str) -> str:
    """Ficha de una serie del BCRP: nombre, categoría, frecuencia, desde cuándo hay datos y su página web."""
    ficha = _ficha(codigo)
    ficha["pagina"] = f"{WEB}/{CARPETA_WEB.get(ficha['frecuencia'], 'mensuales')}/resultados/{codigo}/html"
    return json.dumps(ficha, ensure_ascii=False)


@mcp.resource("bcrp://energia", mime_type="application/json")
def energia() -> str:
    """Series del BCRP para analizar choques de energía: petróleo WTI, tipo de cambio interbancario e IPC."""
    grupos = {grupo: [_ficha(c) for c in codigos] for grupo, codigos in ENERGIA.items()}
    grupos["sugerencia"] = ("Para comparar_series usen series de la misma frecuencia: mensuales PN01660XM, "
                            "PN01206PM y PN01273PM; diarias PD04705XD y PD04638PD.")
    return json.dumps(grupos, ensure_ascii=False)


# --- TODO 5 · prompts ------------------------------------------------------------------------------------------------

@mcp.prompt
def informe(tema: str) -> str:
    """Pide un informe breve sobre un tema económico del Perú con cifras oficiales del BCRP."""
    return (f"Escribe un informe breve sobre «{tema}» en el Perú con datos oficiales del BCRP.\n"
            "1. Busca las series con buscar_series.\n"
            "2. Usa resumen o serie para cada cifra; no hagas cuentas a mano.\n"
            "3. Cita junto a cada cifra el código de la serie y el periodo, por ejemplo: 4.55 % (PN01273PM, 2026-09).\n"
            "4. Termina con la lista de URLs de fuente.")


@mcp.prompt
def choque_petroleo(desde: str, hasta: str) -> str:
    """Analiza si el precio del petróleo se movió junto con el tipo de cambio y la inflación en un periodo."""
    return (f"Analiza el choque del precio del petróleo entre {desde} y {hasta}.\n"
            "1. Lee el recurso bcrp://energia para conocer los códigos de petróleo, tipo de cambio e IPC.\n"
            "2. Llama a comparar_series con las series mensuales (PN01660XM, PN01206PM y PN01273PM) "
            f"desde {desde} hasta {hasta}.\n"
            "3. Explica la variación % de cada serie y la correlación entre ellas; recuerda que correlación no es "
            "causalidad.\n"
            "4. Cita el código y el periodo de cada cifra, y las URLs de fuente.")


if __name__ == "__main__":
    mcp.run()
