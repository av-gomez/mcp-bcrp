"""Prueba el servidor tal como lo lanza Claude Code: por stdio, con la entrada bcrp de .mcp.json.

    uv run scripts/verificar.py
"""
import asyncio
import json
from pathlib import Path

from fastmcp import Client

AQUI = Path(__file__).parent.parent  # la raíz del proyecto


async def main():
    # Solo el servidor bcrp de .mcp.json, lanzado como subproceso (uv run server.py) desde la raíz del proyecto
    config = json.loads((AQUI / ".mcp.json").read_text())
    servidor = config["mcpServers"]["bcrp"] | {"cwd": str(AQUI)}
    bcrp = {"mcpServers": {"bcrp": servidor}}
    async with Client(bcrp) as c:
        # 1. Recurso: la ficha de la serie del IPC a 12 meses
        ficha = await c.read_resource("bcrp://serie/PN01273PM")
        print("RECURSO bcrp://serie/PN01273PM\n", ficha[0].text, "\n")
        # 2. Prompt: informe sobre inflación
        prompt = await c.get_prompt("informe", {"tema": "inflación"})
        print("PROMPT informe\n", prompt.messages[0].content.text, "\n")
        # 3. Herramienta propia con datos reales: petróleo, tipo de cambio e inflación
        r = await c.call_tool("comparar_series", {"codigos": ["PN01660XM", "PN01206PM", "PN01273PM"],
                                                  "desde": "2025-01", "hasta": "2026-09"})
        d = r.data
        print("COMPARAR_SERIES", d["desde"], "->", d["hasta"], f"({len(d['datos'])} periodos)")
        print(" variación %:", d["variacion_pct"])
        print(" correlación:", d["correlacion"])
        print(" fuentes:", d["fuentes"])
        assert len(d["datos"]) >= 12


asyncio.run(main())
