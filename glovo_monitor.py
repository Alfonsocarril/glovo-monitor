"""
Glovo Menu Monitor - Street Smash Burgers
Usa URLs con coordenadas GPS para acceder directamente a cada tienda.
"""

import asyncio
import json
import os
import re
from datetime import datetime
from playwright.async_api import async_playwright
import requests

SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "TU_WEBHOOK_AQUI")

CARTA_MAESTRA = [
    "Street Burger", "Bacon Burger", "Classic Burger", "Truffle Burger",
    "Street Combo", "Bacon Combo", "Classic Combo", "Truffle Combo",
    "Veggie Combo", "Veggie Burger",
    "Fries", "Sweet Fries", "Truffle Fries",
    "Street", "Secret", "Mayo Sriracha", "Mayo Garlic",
    "Pastrami Burger", "Chimichurri",
]

# Coordenadas GPS de cada tienda
TIENDAS = [
    ("Campo de Ourique",   38.7133, -9.1589, "pt", "pt", "lisboa"),
    ("Saldanha",           38.7369, -9.1439, "pt", "pt", "lisboa"),
    ("Cais do Sodre",      38.7063, -9.1456, "pt", "pt", "lisboa"),
    ("Anjos",              38.7236, -9.1358, "pt", "pt", "lisboa"),
    ("Alvalade",           38.7517, -9.1478, "pt", "pt", "lisboa"),
    ("Cascais",            38.6979, -9.4215, "pt", "pt", "cascais"),
    ("Odivelas",           38.7952, -9.1860, "pt", "pt", "odivelas"),
    ("Vasco da Gama",      38.7633, -9.0988, "pt", "pt", "lisboa"),
    ("UBBO",               38.7340, -9.2298, "pt", "pt", "amadora"),
    ("Almada",             38.6766, -9.1594, "pt", "pt", "almada"),
    ("Arrabida",           41.1621, -8.6521, "pt", "pt", "porto"),
    ("Junqueiro",          38.7369, -9.1323, "pt", "pt", "lisboa"),
    ("Porto Baixa",        41.1496, -8.6109, "pt", "pt", "porto"),
    ("Porto Matosinhos",   41.1837, -8.6916, "pt", "pt", "matosinhos"),
    ("Porto Bessa",        41.1579, -8.6395, "pt", "pt", "porto"),
    ("Porto MarShopping",  41.1876, -8.6987, "pt", "pt", "matosinhos"),
    ("Porto Via Catarina",  41.1496, -8.6109, "pt", "pt", "porto"),
]

STORE_SLUG = "street-smash-burgers-lis"


async def cerrar_popups(page):
    for texto in ["Rejeitar", "Reject", "Aceitar tudo", "Accept all"]:
        try:
            btn = page.locator(f"button:has-text('{texto}')").first
            if await btn.is_visible(timeout=2000):
                await btn.click()
                await page.wait_for_timeout(500)
                return
        except Exception:
            pass


async def obtener_menu(page):
    await page.wait_for_timeout(3000)
    for _ in range(10):
        await page.evaluate("window.scrollBy(0, 500)")
        await page.wait_for_timeout(300)
    await page.evaluate("window.scrollTo(0, 0)")
    await page.wait_for_timeout(500)

    texto = await page.inner_text("body")

    promos = []
    patrones = re.findall(
        r'\d+%[^\n]{0,40}|GRATIS[^\n]{0,30}|Gratis[^\n]{0,30}|'
        r'2 por 1[^\n]{0,30}|World Cup[^\n]{0,30}|WORLD CUP[^\n]{0,30}|'
        r'Edicao Limitada[^\n]{0,30}|EDICAO LIMITADA[^\n]{0,30}|'
        r'Gratis no primeiro[^\n]{0,30}',
        texto
    )
    seen = set()
    for p in patrones:
        p = p.strip()
        if p and len(p) > 3 and p not in seen:
            promos.append(p)
            seen.add(p)

    return texto, promos[:5]


def formatear_slack(resultados, fecha):
    total = len(resultados)
    con_incidencias = sum(1 for r in resultados if r["productos_ausentes"] and not r["error"])
    sin_incidencias = sum(1 for r in resultados if not r["productos_ausentes"] and not r["error"])
    con_error = sum(1 for r in resultados if r["error"])

    bloques = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "Informe Glovo - Street Smash Burgers", "emoji": True}
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"Fecha: {fecha} | {total} tiendas revisadas"}]
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Sin incidencias:* {sin_incidencias}"},
                {"type": "mrkdwn", "text": f"*Con incidencias:* {con_incidencias}"},
                {"type": "mrkdwn", "text": f"*Errores:* {con_error}"},
                {"type": "mrkdwn", "text": f"*Total tiendas:* {total}"},
            ]
        },
        {"type": "divider"}
    ]

    incidencias = [r for r in resultados if r["productos_ausentes"] and not r["error"]]
    ok = [r for r in resultados if not r["productos_ausentes"] and not r["error"]]
    errores = [r for r in resultados if r["error"]]

    if incidencias:
        bloques.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*TIENDAS CON PRODUCTOS AUSENTES*"}
        })
        for r in incidencias:
            ausentes_str = "\n".join([f"- {p}" for p in r["productos_ausentes"]])
            promos_str = " | ".join(r["promociones"][:3]) if r["promociones"] else "Sin promociones"
            bloques.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*{r['nombre']}*\n"
                        f"{ausentes_str}\n"
                        f"Promos: {promos_str}"
                    )
                }
            })
        bloques.append({"type": "divider"})

    if ok:
        ok_lista = "\n".join([
            f"OK *{r['nombre']}* | {' | '.join(r['promociones'][:2]) if r['promociones'] else 'Sin promos'}"
            for r in ok
        ])
        bloques.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*TIENDAS OK*\n{ok_lista}"}
        })

    if errores:
        bloques.append({"type": "divider"})
        err_lista = "\n".join([f"ERROR *{r['nombre']}*: {r['error'][:80]}" for r in errores])
        bloques.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*ERRORES*\n{err_lista}"}
        })

    bloques.append({
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": "Generado automaticamente por Glovo Monitor"}]
    })

    return {"blocks": bloques}


def enviar_slack(mensaje):
    if SLACK_WEBHOOK_URL == "TU_WEBHOOK_AQUI":
        print(json.dumps(mensaje, indent=2, ensure_ascii=False))
        return
    r = requests.post(
        SLACK_WEBHOOK_URL,
        json=mensaje,
        headers={"Content-Type": "application/json"}
    )
    if r.status_code == 200:
        print("Informe enviado a Slack")
    else:
        print(f"Error Slack: {r.status_code} - {r.text}")


async def main():
    resultados = []
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )

        print(f"Iniciando revision - {fecha}")

        for nombre, lat, lon, lang, country, ciudad in TIENDAS:
            print(f"Revisando: {nombre}")
            resultado = {
                "nombre": nombre,
                "productos_ausentes": [],
                "productos_presentes": [],
                "promociones": [],
                "error": None
            }

            try:
                context = await browser.new_context(
                    viewport={"width": 1366, "height": 768},
                    locale="pt-PT",
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    geolocation={"latitude": lat, "longitude": lon},
                    permissions=["geolocation"],
                )
                page = await context.new_page()
                await page.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )

                # URL directa con ciudad
                url = f"https://glovoapp.com/{lang}/{country}/{ciudad}/stores/{STORE_SLUG}"
                await page.goto(url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(2000)
                await cerrar_popups(page)

                texto, promos = await obtener_menu(page)
                resultado["promociones"] = promos

                for producto in CARTA_MAESTRA:
                    if producto.lower() in texto.lower():
                        resultado["productos_presentes"].append(producto)
                    else:
                        resultado["productos_ausentes"].append(producto)

                print(f"  Ausentes: {resultado['productos_ausentes']}")
                print(f"  Promos: {promos}")

                await context.close()

            except Exception as e:
                resultado["error"] = str(e)[:150]
                print(f"  Error: {e}")
                try:
                    await context.close()
                except Exception:
                    pass

            resultados.append(resultado)
            await asyncio.sleep(2)

        await browser.close()

    mensaje = formatear_slack(resultados, fecha)
    enviar_slack(mensaje)

    with open("ultimo_informe.json", "w", encoding="utf-8") as f:
        json.dump({"fecha": fecha, "resultados": resultados}, f, ensure_ascii=False, indent=2)
    print("Guardado en ultimo_informe.json")


if __name__ == "__main__":
    asyncio.run(main())
