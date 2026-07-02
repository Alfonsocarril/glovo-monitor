"""
Glovo Menu Monitor - Street Smash Burgers
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

TIENDAS = [
    ("Campo de Ourique",   38.7133, -9.1589, "lisboa",     "street-smash-burgers-lis"),
    ("Saldanha",           38.7369, -9.1439, "lisboa",     "street-smash-burgers-lis"),
    ("Cais do Sodre",      38.7063, -9.1456, "lisboa",     "street-smash-burgers-lis"),
    ("Anjos",              38.7236, -9.1358, "lisboa",     "street-smash-burgers-lis"),
    ("Alvalade",           38.7517, -9.1478, "lisboa",     "street-smash-burgers-lis"),
    ("Cascais",            38.6979, -9.4215, "cascais",    "street-smash-burgers-csc"),
    ("Odivelas",           38.7952, -9.1860, "odivelas",   "street-smash-burgers-odi"),
    ("Vasco da Gama",      38.7633, -9.0988, "lisboa",     "street-smash-burgers-lis"),
    ("UBBO",               38.7340, -9.2298, "amadora",    "street-smash-burgers-lis"),
    ("Almada",             38.6766, -9.1594, "almada",     "street-smash-burgers-lis"),
    ("Arrabida",           41.1621, -8.6521, "porto",      "street-smash-burgers-opo"),
    ("Junqueiro",          38.7369, -9.1323, "lisboa",     "street-smash-burgers-lis"),
    ("Porto Baixa",        41.1496, -8.6109, "porto",      "street-smash-burgers-opo"),
    ("Porto Matosinhos",   41.1837, -8.6916, "matosinhos", "street-smash-burgers-opo"),
    ("Porto Bessa",        41.1579, -8.6395, "porto",      "street-smash-burgers-opo"),
    ("Porto MarShopping",  41.1876, -8.6987, "matosinhos", "street-smash-burgers-opo"),
    ("Porto Via Catarina", 41.1496, -8.6109, "porto",      "street-smash-burgers-opo"),
]

# Si la tienda cargó bien, debe tener al menos estos productos visibles
MIN_PRODUCTOS_VALIDOS = 5


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
        r'-?\d+%[^\n]{0,40}|'
        r'Free delivery[^\n]{0,30}|'
        r'Gratis[^\n]{0,30}|'
        r'GRATIS[^\n]{0,30}|'
        r'2 por 1[^\n]{0,30}|'
        r'2 for 1[^\n]{0,30}|'
        r'World Cup[^\n]{0,30}|'
        r'WORLD CUP[^\n]{0,30}|'
        r'Pastrami[^\n]{0,40}|'
        r'Edição Limitada[^\n]{0,30}|'
        r'Limited Edition[^\n]{0,30}',
        texto
    )
    seen = set()
    for p in patrones:
        p = p.strip()
        if p and len(p) > 3 and p not in seen:
            promos.append(p)
            seen.add(p)

    return texto, promos[:6]


def tienda_cargo_bien(productos_presentes):
    """Comprueba que la tienda cargó correctamente."""
    return len(productos_presentes) >= MIN_PRODUCTOS_VALIDOS


def formatear_slack(resultados, fecha):
    total = len(resultados)
    ok_list = [r for r in resultados if r["estado"] == "ok" and len(r["productos_ausentes"]) == 0]
    incidencias = [r for r in resultados if r["estado"] == "ok" and len(r["productos_ausentes"]) > 0]
    no_encontradas = [r for r in resultados if r["estado"] == "no_encontrada"]
    errores = [r for r in resultados if r["estado"] == "error"]

    bloques = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🍔 Informe Glovo - Street Smash Burgers", "emoji": True}
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"📅 {fecha} | {total} tiendas revisadas"}]
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"✅ *Sin incidencias:* {len(ok_list)}"},
                {"type": "mrkdwn", "text": f"❌ *Con incidencias:* {len(incidencias)}"},
                {"type": "mrkdwn", "text": f"🔍 *No encontradas:* {len(no_encontradas)}"},
                {"type": "mrkdwn", "text": f"⚠️ *Errores:* {len(errores)}"},
            ]
        },
        {"type": "divider"}
    ]

    # Tiendas con productos ausentes
    if incidencias:
        bloques.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*❌ TIENDAS CON PRODUCTOS AUSENTES*"}
        })
        for r in incidencias:
            ausentes_str = "\n".join([f"  • {p}" for p in r["productos_ausentes"]])
            promos_str = " | ".join(r["promociones"][:3]) if r["promociones"] else "Sin promociones"
            bloques.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*{r['nombre']}*\n"
                        f"{ausentes_str}\n"
                        f"🏷️ {promos_str}"
                    )
                }
            })
        bloques.append({"type": "divider"})

    # Tiendas OK
    if ok_list:
        ok_texto = "\n".join([
            f"✅ *{r['nombre']}* | 🏷️ {' | '.join(r['promociones'][:2]) if r['promociones'] else 'Sin promos'}"
            for r in ok_list
        ])
        bloques.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*✅ TIENDAS OK*\n{ok_texto}"}
        })

    # Tiendas no encontradas
    if no_encontradas:
        bloques.append({"type": "divider"})
        nd_texto = "\n".join([f"🔍 *{r['nombre']}* — No encontrada en Glovo, revisar manualmente" for r in no_encontradas])
        bloques.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*🔍 TIENDAS NO ENCONTRADAS*\n{nd_texto}"}
        })

    # Errores técnicos
    if errores:
        bloques.append({"type": "divider"})
        err_texto = "\n".join([f"⚠️ *{r['nombre']}*: {r.get('error', '')[:80]}" for r in errores])
        bloques.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*⚠️ ERRORES TÉCNICOS*\n{err_texto}"}
        })

    bloques.append({
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": "🤖 Generado automaticamente por Glovo Monitor"}]
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

        for nombre, lat, lon, ciudad, slug in TIENDAS:
            print(f"Revisando: {nombre}")
            resultado = {
                "nombre": nombre,
                "estado": "ok",
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

                url = f"https://glovoapp.com/pt/pt/{ciudad}/stores/{slug}"
                print(f"  URL: {url}")
                await page.goto(url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(2000)
                await cerrar_popups(page)

                texto, promos = await obtener_menu(page)
                resultado["promociones"] = promos

                # Comprobar qué productos están presentes
                for producto in CARTA_MAESTRA:
                    if producto.lower() in texto.lower():
                        resultado["productos_presentes"].append(producto)
                    else:
                        resultado["productos_ausentes"].append(producto)

                # Si hay menos de 5 productos encontrados, la tienda no cargó bien
                if not tienda_cargo_bien(resultado["productos_presentes"]):
                    print(f"  ⚠️ Tienda no encontrada (solo {len(resultado['productos_presentes'])} productos detectados)")
                    resultado["estado"] = "no_encontrada"
                    resultado["productos_ausentes"] = []
                    resultado["productos_presentes"] = []
                    resultado["promociones"] = []
                else:
                    print(f"  ✅ Cargada correctamente ({len(resultado['productos_presentes'])} productos encontrados)")
                    print(f"  ❌ Ausentes: {resultado['productos_ausentes']}")
                    print(f"  🏷️ Promos: {promos}")

                await context.close()

            except Exception as e:
                resultado["estado"] = "error"
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
