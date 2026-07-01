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
    ("Campo de Ourique",   "Rua Almeida e Sousa 36B Lisboa"),
    ("Saldanha",           "Avenida Defensores de Chaves 77 Lisboa"),
    ("Cais do Sodre",      "Rua da Boavista 34 Lisboa"),
    ("Anjos",              "Rua de Anjos 78 Lisboa"),
    ("Alvalade",           "Avenida da Igreja 8 Lisboa"),
    ("Cascais",            "Rua Frederico Arouca 50 Cascais"),
    ("Odivelas",           "Rua Egas Moniz 10 Odivelas"),
    ("Vasco da Gama",      "Avenida Dom Joao II Lisboa"),
    ("UBBO",               "Estrada de Alfragide Amadora"),
    ("Almada",             "Praca do Chile 1 Almada"),
    ("Arrabida",           "Rua Particular da Arrabida Vila Nova de Gaia"),
    ("Junqueiro",          "Avenida Guerra Junqueiro 30 Lisboa"),
    ("Porto Baixa",        "Rua de Santa Catarina 10 Porto"),
    ("Porto Matosinhos",   "Rua Roberto Ivens 10 Matosinhos"),
    ("Porto Bessa",        "Avenida da Boavista 700 Porto"),
    ("Porto MarShopping",  "Avenida Meneres Matosinhos"),
    ("Porto Via Catarina", "Rua de Santa Catarina 312 Porto"),
]

GLOVO_URL = "https://glovoapp.com/pt/pt/lisboa/stores/street-smash-burgers-lis"


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


async def seleccionar_direccion(page, direccion):
    try:
        for selector in [
            "header button",
            "[data-testid='address-button']",
            "button[class*='address']",
            "nav button:first-child",
        ]:
            try:
                el = page.locator(selector).first
                if await el.is_visible(timeout=3000):
                    await el.click()
                    await page.wait_for_timeout(1500)
                    break
            except Exception:
                continue

        campo = None
        for selector in [
            "input[placeholder*='morada']",
            "input[placeholder*='Procurar']",
            "input[placeholder*='address']",
            "input[type='text']",
            "input[type='search']",
        ]:
            try:
                el = page.locator(selector).first
                if await el.is_visible(timeout=3000):
                    campo = el
                    break
            except Exception:
                continue

        if not campo:
            return False

        await campo.click()
        await campo.fill("")
        await campo.type(direccion, delay=60)
        await page.wait_for_timeout(2000)

        for selector in [
            "ul li:first-child",
            "[role='option']:first-child",
            "[data-testid='address-suggestion']",
            ".pac-item:first-child",
        ]:
            try:
                sug = page.locator(selector).first
                if await sug.is_visible(timeout=3000):
                    await sug.click()
                    await page.wait_for_timeout(1500)
                    break
            except Exception:
                continue

        for _ in range(3):
            for texto in ["Outro", "Other"]:
                try:
                    btn = page.locator(f"text={texto}").first
                    if await btn.is_visible(timeout=1000):
                        await btn.click()
                        await page.wait_for_timeout(500)
                except Exception:
                    pass

            for placeholder in ["Piso", "Floor", "Porta", "Door"]:
                try:
                    inp = page.locator(f"input[placeholder*='{placeholder}']").first
                    if await inp.is_visible(timeout=1000):
                        await inp.fill("1")
                except Exception:
                    pass

            for texto in ["Confirmar morada", "Confirmar", "Confirm"]:
                try:
                    btn = page.locator(f"text={texto}").first
                    if await btn.is_visible(timeout=1000):
                        await btn.click()
                        await page.wait_for_timeout(1500)
                except Exception:
                    pass

        return True

    except Exception as e:
        print(f"   Error direccion: {e}")
        return False


async def obtener_direccion_real(page):
    try:
        for selector in [
            "button[aria-label*='info']",
            "button[aria-label*='Info']",
            "[data-testid='store-info']",
        ]:
            try:
                btn = page.locator(selector).first
                if await btn.is_visible(timeout=2000):
                    await btn.click()
                    await page.wait_for_timeout(1000)
                    break
            except Exception:
                continue

        contenido = await page.inner_text("body")
        direccion = ""
        lineas = contenido.split("\n")
        for i, linea in enumerate(lineas):
            if "Morada" in linea and i + 1 < len(lineas):
                direccion = lineas[i + 1].strip()
                break

        for texto in ["Entendido", "Got it", "OK", "Fechar"]:
            try:
                btn = page.locator(f"text={texto}").first
                if await btn.is_visible(timeout=1000):
                    await btn.click()
                    await page.wait_for_timeout(500)
                    break
            except Exception:
                pass

        return direccion

    except Exception:
        return ""


async def obtener_menu(page):
    await page.wait_for_timeout(2000)
    for _ in range(8):
        await page.evaluate("window.scrollBy(0, 500)")
        await page.wait_for_timeout(300)
    await page.evaluate("window.scrollTo(0, 0)")
    await page.wait_for_timeout(500)

    texto = await page.inner_text("body")

    promos = []
    patrones = re.findall(
        r'\d+%[^\n]{0,40}|GRATIS[^\n]{0,30}|Gratis[^\n]{0,30}|'
        r'2 por 1[^\n]{0,30}|World Cup[^\n]{0,30}|WORLD CUP[^\n]{0,30}|'
        r'Edicao Limitada[^\n]{0,30}|EDICAO LIMITADA[^\n]{0,30}',
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
                        f"_{r['direccion_real'] or r['direccion_entrega']}_\n"
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
        context = await browser.new_context(
            viewport={"width": 1366, "height": 768},
            locale="pt-PT",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        await page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        print(f"Iniciando revision - {fecha}")

        for nombre, direccion in TIENDAS:
            print(f"Revisando: {nombre}")
            resultado = {
                "nombre": nombre,
                "direccion_entrega": direccion,
                "direccion_real": "",
                "productos_ausentes": [],
                "productos_presentes": [],
                "promociones": [],
                "error": None
            }

            try:
                await page.goto(GLOVO_URL, wait_until="networkidle", timeout=25000)
                await page.wait_for_timeout(2000)
                await cerrar_popups(page)

                ok = await seleccionar_direccion(page, direccion)
                if not ok:
                    resultado["error"] = "No se pudo seleccionar la direccion"
                    resultados.append(resultado)
                    continue

                dir_real = await obtener_direccion_real(page)
                resultado["direccion_real"] = dir_real

                texto, promos = await obtener_menu(page)
                resultado["promociones"] = promos

                for producto in CARTA_MAESTRA:
                    if producto.lower() in texto.lower():
                        resultado["productos_presentes"].append(producto)
                    else:
                        resultado["productos_ausentes"].append(producto)

                print(f"  Ausentes: {resultado['productos_ausentes']}")
                print(f"  Promos: {promos}")

            except Exception as e:
                resultado["error"] = str(e)[:150]
                print(f"  Error: {e}")

            resultados.append(resultado)
            await page.wait_for_timeout(1500)

        await browser.close()

    mensaje = formatear_slack(resultados, fecha)
    enviar_slack(mensaje)

    with open("ultimo_informe.json", "w", encoding="utf-8") as f:
        json.dump({"fecha": fecha, "resultados": resultados}, f, ensure_ascii=False, indent=2)
    print("Guardado en ultimo_informe.json")


if __name__ == "__main__":
    asyncio.run(main())
