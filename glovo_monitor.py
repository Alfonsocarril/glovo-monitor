"""
Glovo Menu Monitor — Street Smash Burgers
Revisa el menú y promociones de cada tienda en Glovo y envía informe a Slack.
Ejecutar: python glovo_monitor.py
"""

import asyncio
import json
import os
import re
from datetime import datetime
from playwright.async_api import async_playwright
import requests

# ============================================================
# CONFIGURACIÓN — edita estos valores
# ============================================================

SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "TU_WEBHOOK_AQUI")

# Carta maestra — productos que deben estar en todas las tiendas
CARTA_MAESTRA = [
    "Street Burger",
    "Bacon Burger",
    "Classic Burger",
    "Truffle Burger",
    "Street Combo",
    "Bacon Combo",
    "Classic Combo",
    "Truffle Combo",
    "Veggie Combo",
    "Veggie Burger",
    "Fries",
    "Sweet Fries",
    "Truffle Fries",
    "Street",       # Salsa
    "Secret",       # Salsa
    "Mayo Sriracha",
    "Mayo Garlic",
    "Pastrami Burger",
    "Maionese de chimichurri",
]

# Tiendas a revisar: (nombre, dirección de entrega para Glovo)
TIENDAS = [
    # Lisboa
    ("Campo de Ourique",  "Rua Almeida e Sousa 36B Lisboa"),
    ("Saldanha",          "Avenida Defensores de Chaves 77 Lisboa"),
    ("Cais do Sodré",     "Rua da Boavista 34 Lisboa"),
    ("Anjos",             "Rua de Anjos 78 Lisboa"),
    ("Alvalade",          "Avenida da Igreja 8 Lisboa"),
    ("Cascais",           "Rua Frederico Arouca 50 Cascais"),
    ("Odivelas",          "Rua Egas Moniz 10 Odivelas"),
    ("Vasco da Gama",     "Avenida Dom João II Lisboa"),
    ("UBBO",              "Estrada de Alfragide Amadora"),
    ("Almada",            "Alameda dos Oceanos Almada"),
    ("Arrábida",          "Rua Particular da Arrábida Vila Nova de Gaia"),
    ("Junqueiro",         "Avenida Guerra Junqueiro 30 Lisboa"),
    # Porto
    ("Porto Baixa",       "Rua de Santa Catarina 10 Porto"),
    ("Porto Matosinhos",  "Rua Roberto Ivens 10 Matosinhos"),
    ("Porto Bessa",       "Avenida da Boavista 700 Porto"),
    ("Porto MarShopping", "Avenida Menéres Matosinhos"),
    ("Porto Via Catarina","Rua de Santa Catarina 312 Porto"),
]

GLOVO_URL = "https://glovoapp.com/pt/pt/lisboa/stores/street-smash-burgers-lis"

# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def normalizar(texto):
    """Normaliza texto para comparación flexible."""
    return texto.lower().strip()

def producto_presente(nombre_producto, texto_pagina):
    """Comprueba si un producto de la carta aparece en el texto de la página."""
    return normalizar(nombre_producto) in normalizar(texto_pagina)

async def seleccionar_direccion(page, direccion):
    """Introduce una dirección de entrega en Glovo y la confirma."""
    try:
        # Clic en selector de dirección
        await page.locator("text=Procurar morada").first.click(timeout=5000)
    except Exception:
        try:
            await page.locator("[data-testid='address-input']").click(timeout=3000)
        except Exception:
            # Clic en la dirección actual en el header
            await page.locator("header").locator("button").first.click(timeout=5000)
            await page.wait_for_timeout(1000)

    # Esperar campo de búsqueda y escribir
    campo = page.locator("input[placeholder*='morada'], input[placeholder*='address']").first
    await campo.wait_for(state="visible", timeout=8000)
    await campo.fill("")
    await campo.type(direccion, delay=50)
    await page.wait_for_timeout(2000)

    # Seleccionar primera sugerencia
    sugerencia = page.locator("[data-testid='address-suggestion'], .address-suggestion, ul li").first
    await sugerencia.wait_for(state="visible", timeout=5000)
    await sugerencia.click()
    await page.wait_for_timeout(1000)

    # Si pide tipo de local, seleccionar "Outro"
    try:
        outro = page.locator("text=Outro, text=Other").first
        if await outro.is_visible(timeout=2000):
            await outro.click()
            await page.wait_for_timeout(500)
    except Exception:
        pass

    # Si pide piso/puerta, rellenar y confirmar
    try:
        piso = page.locator("input[placeholder*='Piso'], input[placeholder*='Floor']").first
        if await piso.is_visible(timeout=2000):
            await piso.fill("1")
            porta = page.locator("input[placeholder*='Porta'], input[placeholder*='Door']").first
            await porta.fill("1")
    except Exception:
        pass

    # Confirmar dirección
    try:
        confirmar = page.locator("text=Confirmar morada, text=Confirmar, text=Confirm").first
        if await confirmar.is_visible(timeout=3000):
            await confirmar.click()
            await page.wait_for_timeout(2000)
    except Exception:
        pass

async def obtener_info_tienda(page):
    """Abre el popup ⓘ y extrae la dirección real de la tienda."""
    try:
        info_btn = page.locator("button[aria-label='Store info'], [data-testid='store-info-button']").first
        if not await info_btn.is_visible(timeout=2000):
            # Buscar el botón ⓘ por posición en el banner
            info_btn = page.locator("button").filter(has_text="").nth(1)
        await info_btn.click(timeout=3000)
        await page.wait_for_timeout(1000)

        contenido = await page.locator(".store-info, [data-testid='store-info-modal'], [role='dialog']").first.inner_text(timeout=5000)
        
        # Extraer dirección
        lineas = contenido.split("\n")
        direccion_real = ""
        for i, linea in enumerate(lineas):
            if "Morada" in linea and i + 1 < len(lineas):
                direccion_real = lineas[i + 1].strip()
                break

        # Extraer horarios
        horario = ""
        for linea in lineas:
            if any(dia in linea for dia in ["Segunda", "Monday", "Lunes"]):
                horario = linea.strip()
                break

        # Cerrar popup
        await page.locator("text=Entendido, text=Got it, text=OK").first.click(timeout=3000)
        await page.wait_for_timeout(500)

        return direccion_real, contenido
    except Exception as e:
        return "No disponible", ""

async def obtener_menu_y_promos(page):
    """Extrae todo el texto del menú y las promociones activas."""
    await page.wait_for_timeout(2000)
    
    # Scroll para cargar todo el contenido
    for _ in range(8):
        await page.keyboard.press("End")
        await page.wait_for_timeout(600)
    await page.keyboard.press("Home")
    await page.wait_for_timeout(500)

    texto_completo = await page.inner_text("body")
    
    # Extraer promociones (buscar patrones de descuento)
    promos = []
    patrones_promo = re.findall(r'[-−]?\d+%[^€\n]*|GRÁTIS[^\n]*|2 por 1[^\n]*|Grátis[^\n]*|World Cup[^\n]*|WORLD CUP[^\n]*|Edição Limitada[^\n]*|EDIÇÃO LIMITADA[^\n]*', texto_completo)
    for p in patrones_promo:
        p = p.strip()
        if p and len(p) > 2 and p not in promos:
            promos.append(p)

    # Categorías visibles en el menú lateral
    categorias = re.findall(r'(?:Burgers|Combos|Veggie|Fries|Sauces|Sauces|Molhos|Promoções|Mais vendidos|WORLD CUP|EDIÇÃO LIMITADA|Bebidas|Drinks)[^\n]*', texto_completo)

    return texto_completo, list(set(promos))[:8], list(set(categorias))[:10]

# ============================================================
# FUNCIÓN PRINCIPAL
# ============================================================

async def revisar_tiendas():
    resultados = []
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="pt-PT",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        print(f"\n🚀 Iniciando revisión — {fecha}")
        print(f"📋 {len(TIENDAS)} tiendas a revisar\n")

        for nombre, direccion in TIENDAS:
            print(f"🔍 Revisando: {nombre} ({direccion})")
            resultado = {
                "nombre": nombre,
                "direccion_entrega": direccion,
                "direccion_real": "",
                "productos_ausentes": [],
                "productos_presentes": [],
                "promociones": [],
                "categorias": [],
                "error": None
            }

            try:
                # Navegar a Glovo
                await page.goto(GLOVO_URL, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)

                # Cerrar cookies si aparecen
                try:
                    await page.locator("text=Rejeitar, text=Reject, text=Aceitar tudo").first.click(timeout=3000)
                    await page.wait_for_timeout(1000)
                except Exception:
                    pass

                # Seleccionar dirección de entrega
                await seleccionar_direccion(page, direccion)
                await page.wait_for_timeout(2000)

                # Verificar tienda con ⓘ
                dir_real, _ = await obtener_info_tienda(page)
                resultado["direccion_real"] = dir_real
                print(f"   ✅ Tienda confirmada: {dir_real}")

                # Leer menú completo y promociones
                texto, promos, categorias = await obtener_menu_y_promos(page)
                resultado["promociones"] = promos
                resultado["categorias"] = categorias

                # Comparar con carta maestra
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
                    print(f"   🏷️ Promos: {', '.join(promos[:3])}")

            except Exception as e:
                resultado["error"] = str(e)
                print(f"   ⚠️ Error: {e}")

            resultados.append(resultado)
            await page.wait_for_timeout(1500)  # Pausa entre tiendas

        await browser.close()

    return resultados, fecha

# ============================================================
# FORMATO DEL INFORME SLACK
# ============================================================

def formatear_informe_slack(resultados, fecha):
    """Genera el mensaje Slack con bloques formateados."""
    
    total = len(resultados)
    con_incidencias = sum(1 for r in resultados if r["productos_ausentes"] and not r["error"])
    sin_incidencias = sum(1 for r in resultados if not r["productos_ausentes"] and not r["error"])
    con_error = sum(1 for r in resultados if r["error"])

    bloques = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🍔 Informe Glovo — Street Smash Burgers",
                "emoji": True
            }
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

    # Tiendas con incidencias primero
    incidencias = [r for r in resultados if r["productos_ausentes"] and not r["error"]]
    ok = [r for r in resultados if not r["productos_ausentes"] and not r["error"]]
    errores = [r for r in resultados if r["error"]]

    if incidencias:
        bloques.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*❌ TIENDAS CON PRODUCTOS AUSENTES*"}
        })
        for r in incidencias:
            ausentes_str = "\n".join([f"• ~{p}~" for p in r["productos_ausentes"]])
            promos_str = " | ".join(r["promociones"][:3]) if r["promociones"] else "Sin promociones activas"
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
        bloques.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*✅ TIENDAS OK*\n{ok_lista}"}
        })

    if errores:
        bloques.append({"type": "divider"})
        err_lista = "\n".join([f"⚠️ *{r['nombre']}*: {r['error'][:80]}" for r in errores])
        bloques.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*⚠️ ERRORES*\n{err_lista}"}
        })

    bloques.append({
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": "🤖 Generado automáticamente por Glovo Monitor"}]
    })

    return {"blocks": bloques}

# ============================================================
# ENVÍO A SLACK
# ============================================================

def enviar_slack(mensaje):
    if SLACK_WEBHOOK_URL == "TU_WEBHOOK_AQUI":
        print("\n⚠️ Slack Webhook no configurado. Mostrando informe en consola:\n")
        print(json.dumps(mensaje, indent=2, ensure_ascii=False))
        return

    response = requests.post(
        SLACK_WEBHOOK_URL,
        json=mensaje,
        headers={"Content-Type": "application/json"}
    )
    if response.status_code == 200:
        print("\n✅ Informe enviado a Slack correctamente")
    else:
        print(f"\n❌ Error enviando a Slack: {response.status_code} — {response.text}")

# ============================================================
# MAIN
# ============================================================

async def main():
    resultados, fecha = await revisar_tiendas()
    mensaje = formatear_informe_slack(resultados, fecha)
    enviar_slack(mensaje)
    
    # Guardar también en JSON local como backup
    with open("ultimo_informe.json", "w", encoding="utf-8") as f:
        json.dump({"fecha": fecha, "resultados": resultados}, f, ensure_ascii=False, indent=2)
    print("\n💾 Informe guardado en ultimo_informe.json")

if __name__ == "__main__":
    asyncio.run(main())
