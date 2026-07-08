"""
Glovo Menu Monitor - Street Smash Burgers
Usa las direcciones exactas del directorio para buscar cada tienda en Glovo.
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

# (nombre, direccion_exacta_del_directorio)
TIENDAS = [
    ("Almada",        "Praça São João Baptista 5, Almada"),
    ("Junqueiro",     "Praça do Junqueiro 13B, Lisboa"),
    ("Cascais",       "Rua Afonso Sanches 71D, Cascais"),
    ("Arrábida",      "Praceta Henrique Moreira 244, Vila Nova de Gaia"),
    ("Anjos",         "Rua Maria 44, Lisboa"),
    ("Campo",         "Rua Almeida e Sousa 36B, Lisboa"),
    ("Cais",          "Rua da Boavista 34, Lisboa"),
    ("Saldanha",      "Av. Defensores de Chaves 77, Lisboa"),
    ("Alvalade",      "Rua Marquesa de Alorna 19C, Lisboa"),
    ("Vasco da Gama", "CC Vasco da Gama, Lisboa"),
    ("UBBO",          "Av. Cruzeiro Seixas 5, Amadora"),
    ("Odivelas",      "Rua Pulido Valente 8, Odivelas"),
    ("Porto Baixa",   "Rua da Conceição 35, Porto"),
    ("Porto Matosinhos", "Rua Sousa Aroso 201, Matosinhos"),
    ("Porto Bessa",   "Av. do Bessa 300, Porto"),
    ("Porto MarShopping", "Avenida Doutor Óscar Lopes, Leça da Palmeira"),
    ("Porto Via Catarina", "Rua de Santa Catarina 312, Porto"),
]

GLOVO_URL_PT = "https://glovoapp.com/pt/pt/lisboa/stores/street-smash-burgers-lis"
GLOVO_URL_PORTO = "https://glovoapp.com/pt/pt/porto/stores/street-smash-burgers-opo"
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


async def seleccionar_direccion(page, direccion):
    """Busca la dirección en el buscador de Glovo igual que haría un usuario."""
    try:
        # Clic en el selector de ubicación
        for selector in [
            "button[data-testid='address-button']",
            "header button",
            "[class*='AddressButton']",
            "nav button",
        ]:
            try:
                el = page.locator(selector).first
                if await el.is_visible(timeout=3000):
                    await el.click()
                    await page.wait_for_timeout(1500)
                    break
            except Exception:
                continue

        # Escribir la dirección
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
        await campo.type(direccion, delay=80)
        await page.wait_for_timeout(2500)

        # Seleccionar primera sugerencia
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

        # Manejar pasos adicionales
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
                    "text": f"*{r['nombre']}*\n{ausentes_str}\n🏷️ {promos_str}"
                }
            })
        bloques.append({"type": "divider"})

    if ok_list:
        ok_texto = "\n".join([
            f"✅ *{r['nombre']}* | 🏷️ {' | '.join(r['promociones'][:2]) if r['promociones'] else 'Sin promos'}"
            for r in ok_list
        ])
        bloques.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*✅ TIENDAS OK*\n{ok_texto}"}
        })

    if no_encontradas:
        bloques.append({"type": "divider"})
        nd_texto = "\n".join([f"🔍 *{r['nombre']}* — No encontrada, revisar manualmente" for r in no_encontradas])
        bloques.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*🔍 NO ENCONTRADAS*\n{nd_texto}"}
        })

    if errores:
        bloques.append({"type": "divider"})
        err_texto = "\n".join([f"⚠️ *{r['nombre']}*: {r.get('error', '')[:80]}" for r in errores])
        bloques.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*⚠️ ERRORES*\n{err_texto}"}
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
            headless=False,  # Visible para que Glovo no lo bloquee
            args=["--start-maximized"]
        )
        context = await browser.new_context(
            viewport={"width": 1366, "height": 768},
            locale="pt-PT",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        print(f"Iniciando revision - {fecha}")

        # Cargar Glovo una vez y aceptar cookies
        es_porto = False
        await page.goto(GLOVO_URL_PT, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)
        await cerrar_popups(page)

        for nombre, direccion in TIENDAS:
            print(f"\nRevisando: {nombre} — {direccion}")
            resultado = {
                "nombre": nombre,
                "estado": "ok",
                "productos_ausentes": [],
                "productos_presentes": [],
                "promociones": [],
                "error": None
            }

            try:
                # Usar URL de Porto para tiendas de Porto
                if "Porto" in nombre or "Matosinhos" in nombre:
                    if not es_porto:
                        await page.goto(GLOVO_URL_PORTO, wait_until="networkidle", timeout=30000)
                        await page.wait_for_timeout(2000)
                        await cerrar_popups(page)
                        es_porto = True
                else:
                    if es_porto:
                        await page.goto(GLOVO_URL_PT, wait_until="networkidle", timeout=30000)
                        await page.wait_for_timeout(2000)
                        await cerrar_popups(page)
                        es_porto = False

                # Seleccionar dirección
                ok = await seleccionar_direccion(page, direccion)
                if not ok:
                    resultado["estado"] = "no_encontrada"
                    resultados.append(resultado)
                    continue

                await page.wait_for_timeout(2000)

                # Leer menú
                texto, promos = await obtener_menu(page)
                resultado["promociones"] = promos

                for producto in CARTA_MAESTRA:
                    if producto.lower() in texto.lower():
                        resultado["productos_presentes"].append(producto)
                    else:
                        resultado["productos_ausentes"].append(producto)

                # Validar que la tienda cargó bien
                if len(resultado["productos_presentes"]) < MIN_PRODUCTOS_VALIDOS:
                    print(f"  ⚠️ No encontrada ({len(resultado['productos_presentes'])} productos)")
                    resultado["estado"] = "no_encontrada"
                    resultado["productos_ausentes"] = []
                    resultado["productos_presentes"] = []
                    resultado["promociones"] = []
                else:
                    print(f"  ✅ OK — Ausentes: {resultado['productos_ausentes']}")
                    print(f"  🏷️ Promos: {promos}")

            except Exception as e:
                resultado["estado"] = "error"
                resultado["error"] = str(e)[:150]
                print(f"  Error: {e}")

            resultados.append(resultado)
            await asyncio.sleep(1)

        await browser.close()

    mensaje = formatear_slack(resultados, fecha)
    enviar_slack(mensaje)

    with open("ultimo_informe.json", "w", encoding="utf-8") as f:
        json.dump({"fecha": fecha, "resultados": resultados}, f, ensure_ascii=False, indent=2)
    print("\nGuardado en ultimo_informe.json")


if __name__ == "__main__":
    asyncio.run(main())
