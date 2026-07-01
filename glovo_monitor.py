"""
Glovo Menu Monitor — Street Smash Burgers
Revisa el menú y promociones de cada tienda en Glovo y envía informe a Slack.
"""

import asyncio
import json
import os
import re
from datetime import datetime
from playwright.async_api import async_playwright
import requests

# ============================================================
# CONFIGURACIÓN
# ============================================================

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
    ("Campo de Ourique",  "Rua Almeida e Sousa 36B Lisboa"),
    ("Saldanha",          "Avenida Defensores de Chaves 77 Lisboa"),
    ("Cais do Sodré",     "Rua da Boavista 34 Lisboa"),
    ("Anjos",             "Rua de Anjos 78 Lisboa"),
    ("Alvalade",          "Avenida da Igreja 8 Lisboa"),
    ("Cascais",           "Rua Frederico Arouca 50 Cascais"),
    ("Odivelas",          "Rua Egas Moniz 10 Odivelas"),
    ("Vasco da Gama",     "Avenida Dom João II Lisboa"),
    ("UBBO",              "Estrada de Alfragide Amadora"),
    ("Almada",            "Praça do Chile 1 Almada"),
    ("Arrábida",          "Rua Particular da Arrábida Vila Nova de Gaia"),
    ("Junqueiro",         "Avenida Guerra Junqueiro 30 Lisboa"),
    ("Porto Baixa",       "Rua de Santa Catarina 10 Porto"),
    ("Porto Matosinhos",  "Rua Roberto Ivens 10 Matosinhos"),
    ("Porto Bessa",       "Avenida da Boavista 700 Porto"),
    ("Porto MarShopping", "Avenida Menéres Matosinhos"),
    ("Porto Via Catarina","Rua de Santa Catarina 312 Porto"),
]

GLOVO_URL = "https://glovoapp.com/pt/pt/lisboa/stores/street-smash-burgers-lis"

# ============================================================
# FUNCIONES
# ============================================================

def normalizar(texto):
    return texto.lower().strip()

def producto_presente(nombre, texto):
    return normalizar(nombre) in normalizar(texto)

async def cerrar_popups(page):
    """Cierra cookies y otros popups."""
    for selector in [
        "button:has-text('Rejeitar')",
        "button:has-text('Reject')",
        "button:has-text('Aceitar tudo')",
        "button:has-text('Accept')",
        "[data-testid='cookie-reject']",
    ]:
        try:
            btn = page.locator(selector).first
            if await btn.is_visible(timeout=2000):
                await btn.click()
                await page.wait_for_timeout(800)
                break
        except Exception:
            pass

async def cambiar_direccion_via_url(page, direccion, context):
    """Usa la API de geocoding de Google para obtener coordenadas y las pasa via URL a Glovo."""
    # Usar Nominatim (OpenStreetMap) para geocodificar la dirección
    import urllib.parse
    query = urllib.parse.quote(direccion)
    
    geo_page = await context.new_page()
    try:
        await geo_page.goto(
            f"https://nominatim.openstreetmap.org/search?q={query}&format=json&limit=1",
            wait_until="domcontentloaded",
            timeout=10000
        )
        contenido = await geo_page.inner_text("body")
        datos = json.loads(contenido)
        if datos:
            lat = datos[0]["lat"]
            lon = datos[0]["lon"]
            await geo_page.close()
            return float(lat), float(lon)
    except Exception:
        pass
    await geo_page.close()
    return None, None

async def seleccionar_direccion(page, direccion):
    """Introduce dirección usando el campo de búsqueda de Glovo."""
    try:
        # Intentar clic en el selector de ubicación del header
        for selector in [
            "[data-testid='address-button']",
            "button[class*='address']",
            "header button",
            "nav button",
            "text=Procurar morada",
            "text=Lisboa",
            "text=Porto",
        ]:
            try:
                el = page.locator(selector).first
                if await el.is_visible(timeout=2000):
                    await el.click()
                    await page.wait_for_timeout(1000)
                    break
            except Exception:
                continue

        # Buscar campo de input de dirección
        campo = None
        for selector in [
            "input[placeholder*='morada']",
            "input[placeholder*='address']",
            "input[placeholder*='Procurar']",
            "input[type='text']",
            "input[type='search']",
        ]:
            try:
                el = page.locator(selector).first
                if await el.is_visible(timeout=2000):
                    campo = el
                    break
            except Exception:
                continue

        if not campo:
            return False

        await campo.click()
        await campo.fill("")
        await asyncio.sleep(0.5)
        await campo.type(direccion, delay=80)
        await page.wait_for_timeout(2500)

        # Seleccionar primera sugerencia
        for selector in [
            "ul[role='listbox'] li:first-child",
            "[data-testid='address-suggestion']",
            ".pac-item:first-child",
            "li[role='option']:first-child",
            "ul li:first-child",
        ]:
            try:
                sugerencia = page.locator(selector).first
                if await sugerencia.is_visible(timeout=3000):
                    await sugerencia.click()
                    await page.wait_for_timeout(1500)
                    break
            except Exception:
                continue

        # Manejar pasos adicionales (tipo de local, piso, confirmar)
        for _ in range(3):
            for texto in ["Outro", "Other", "Otro"]:
                try:
                    btn = page.locator(f"text={texto}").first
                    if await btn.is_visible(timeout=1500):
                        await btn.click()
                        await page.wait_for_timeout(800)
                except Exception:
                    pass

            for campo_adicional in ["Piso", "Floor", "Porta", "Door"]:
                try:
                    inp = page.locator(f"input[placeholder*='{campo_adicional}']").first
                    if await inp.is_visible(timeout=1000):
                        await inp.fill("1")
                except Exception:
                    pass

            for texto in ["Confirmar morada", "Confirmar", "Confirm", "Entendido"]:
                try:
                    btn = page.locator(f"text={texto}").first
                    if await btn.is_visible(timeout=1500):
                        await btn.click()
                        await page.wait_for_timeout(1500)
                except Exception:
                    pass

        return True

    except Exception as e:
        print(f"   ⚠️ Error cambiando dirección: {e}")
        return False

async def obtener_info_tienda(page):
    """Obtiene la dirección real de la tienda desde el popup ⓘ."""
    try:
        for selector in [
            "button[aria-label*='info']",
            "button[aria-label*='Info']", 
            "[data-testid='store-info']",
            "svg[data-testid='InfoIcon']",
        ]:
            try:
                btn = page.locator(selector).first
                if await btn.is_visible(timeout=2000):
                    await btn.click()
                    await page.wait_for_timeout(1000)
                    break
            except Exception:
                continue

        # Leer contenido del modal
        contenido = ""
        for selector in ["[role='dialog']", ".modal", "[class*='modal']", "[class*='dialog']"]:
            try:
                modal = page.locator(selector).first
                if await modal.is_visible(timeout=2000):
                    contenido = await modal.inner_text()
                    break
            except Exception:
                continue

        if not contenido:
            contenido = await page.inner_text("body")

        # Extraer dirección
        direccion_real = ""
        lineas = contenido.split("\n")
        for i, linea in enumerate(lineas):
            if "Morada" in linea and i + 1 < len(lineas):
                direccion_real = lineas[i + 1].strip()
                break

        # Cerrar modal
        for texto in ["Entendido", "Got it", "OK", "Fechar", "Close"]:
            try:
                btn = page.locator(f"text={texto}").first
                if await btn.is_visible(timeout=1500):
                    await btn.click()
                    await page.wait_for_timeout(500)
                    break
            except Exception:
                pass

        return direccion_real

    except Exception:
        return ""

async def obtener_menu_y_promos(page):
    """Extrae el menú completo y las promociones."""
    # Scroll completo para cargar todo
    await page.wait_for_timeout(2000)
    for _ in range(10):
        await page.evaluate("window.scrollBy(0, 400)")
        await page.wait_for_timeout(400)
    await page.evaluate("window.scrollTo(0, 0)")
    await page.wait_for_timeout(500)

    texto = await page.inner_text("body")

    # Extraer promociones
    promos = []
    patrones = re.findall(
        r'[-−]?\d+%[^\n€]{0,50}|GRÁTIS[^\n]{0,40}|2 por 1[^\n]{0,30}|'
        r'World Cup[^\n]{0,30}|WORLD CUP[^\n]{0,30}|'
        r'Edição Limitada[^\n]{0,30}|EDIÇÃO LIMITADA[^\n]{0,30}|'
        r'Grátis no primeiro pedido[^\n]{0,30}',
        texto
    )
    seen = set()
    for p in patrones:
        p = p.strip()
        if p and len(p) > 2 and p not in seen:
            promos.append(p)
            seen.add(p)

    return texto, promos[:6]

# ============================================================
# PRINCIPAL
# ============================================================

async def revisar_tiendas():
    resultados = []
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ]
        )
        context = await browser.new_context(
            viewport={"width": 1366, "height": 768},
            locale="pt-PT",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            geolocation={"latitude": 38.7169, "longitude": -9.1399},
            permissions=["geolocation"],
        )

        page = await context.new_page()
        # Evitar detección de bot
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)

        print(f"\n🚀 Iniciando revisión — {fecha}")

        # Cargar la página una vez y aceptar cookies
        await page.goto(GLOVO_URL, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)
        await cerrar_popups(page)
        await page.wait_for_timeout(1000)

        for nombre, direccion in TIENDAS:
            print(f"\n🔍 {nombre} — {direccion}")
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
                # Recargar para cada tienda
                await page.goto(GLOVO_URL, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(2000)
                await cerrar_popups(page)

                # Cambiar dirección
                ok = await seleccionar_direccion(page, direccion)
                if not ok:
                    resultado["error"] = "No se pudo seleccionar la dirección"
                    resultados.append(resultado)
                    continue

                await page.wait_for_timeout(2000)

                # Obtener dirección real via ⓘ
                dir_real = await obtener_info_tienda(page)
                resultado["direccion_real"] = dir_real
                if dir_real:
                    print(f"   📍 Tienda: {dir_real}")

                # Leer menú y promos
                texto, promos = await obtener_menu_y_promos(page)
                resultado["promociones"] = promos

                # Comparar con carta
                for producto in CARTA_MAESTRA:
                    if producto_presente(producto, texto):
                        resultado["productos_presentes"].append(producto)
                    else:
                        resultado["productos_ausentes"].append(producto)

                ausentes = resultado["productos_ausentes"]
                if ausentes:
                    print(f"   ❌ Ausentes: {', '.join(ausentes)}")
                else:
                    print(f"   ✅ Menú completo")
                if promos:
                    print(f"   🏷️ Promos: {', '.join(promos[:2])}")

            except Exception as e:
                resultado["error"] = str(e)[:150]
                print(f"   ⚠️ Error: {e}")

            resultados.append(resultado)
            await page.wait_for_timeout(2000)

        await browser.close()

    return resultados, fecha

# ============================================================
# SLACK
# ============================================================

def formatear_slack(resultados, fecha):
    total = len(resultados)
    con_incidencias = sum(1 for r in resultados if r["productos_ausentes"] and not r["error"])
    sin_incidencias = sum(1 for r in resultados if not r["productos_ausentes"] and not r["error"])
    con_error = sum(1 for r in resultados if r["error"])

    bloques = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🍔 Informe Glovo — Street Smash Burgers", "emoji": True}
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"📅 {fecha} | {total} tiendas revisadas"}]
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"✅ *Sin incidencias:* {sin_incidencias}"},
                {"type": "mrkdwn", "text": f"❌ *Con incidencias:* {con_incidencias}"},
                {"type": "mrkdwn", "text": f"⚠️ *Errores:* {con_error}"},
                {"type": "mrkdwn", "text": f"📍 *Total tiendas:* {total}"},
            ]
        },
        {"type": "divider"}
    ]

    incidencias = [r for r in resultados if r["productos_ausentes"] and not r["error"]]
    ok = [r for r in resultados if not r["productos_ausentes"] and not r["error"]]
    errores = [r for r in resultados if r["error"]]

    if incidencias:
        bloques.append({"type": "section", "text": {"type": "mrkdwn", "text": "*❌ TIENDAS CON PRODUCTOS AUSENTES*"}})
        for r in incidencias:
            ausentes_str = "\n".join([f"• ~{p}~" for p in r["productos_ausentes"]])
            promos_str = " | ".join(r["promociones"][:3]) if r["promociones"] else "Sin promociones"
            bloques.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*{r['nombre']}*\n"
                        f"📍 _{r['direccion_real'] or r['direccion_entrega']}_\n"
                        f"{ausentes_str}\n"
                        f"🏷️ {promos_str}"
                    )
                }
            })
        bloques.append({"type": "divider"})

    if ok:
        ok_lista = "\n".join([
            f"✅ *{r['nombre']}* — {' | '.join(r['promociones'][:2]) if r['promociones'] else 'Sin promos'}"
            for r in ok
        ])
        bloques.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*✅ TIENDAS OK*\n{ok_lista}"}})

    if errores:
        bloques.append({"type": "divider"})
        err_lista = "\n".join([f"⚠️ *{r['nombre']}*: {r['error'][:100]}" for r in errores])
        bloques.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*⚠️ ERRORES*\n{err_lista}"}})

    bloques.append({
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": "🤖 Generado automáticamente por Glovo Monitor"}]
    })

    return {"blocks": bloques}

def enviar_slack(mensaje):
    if SLACK_WEBHOOK_URL == "TU_WEBHOOK_AQUI":
        print("\n⚠️ Webhook no configurado")
        print(json.dumps(mensaje, indent=2, ensure_ascii=False))
        return

    r = requests.post(SLACK_WEBHOOK_URL, json=mensaje, headers={"Content-Type": "application/json"})
    if r.status_code == 200:
        print("\n✅ Informe enviado a Slack")
    else:
        print(f"\n❌ Error Slack: {r.status_code} — {r.text}")

async def main():
    resultados, fecha = await revisar_tiendas()
    mensaje = formatear_slack(resultados, fecha)
    enviar_slack(mensaje)
    with open("ultimo_informe.json", "w", encoding="utf-8") as f:
        json.dump({"fecha": fecha, "resultados": resultados}, f, ensure_ascii=False, indent=2)
    print("\n💾 Guardado en ultimo_informe.json")

if __name__ == "__main__":
    asyncio.run(main())
