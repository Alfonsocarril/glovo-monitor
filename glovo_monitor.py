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
    ("Almada",             "Praça São João Baptista 5 Almada Portugal"),
    ("Junqueiro",          "Praça do Junqueiro 13B Lisboa Portugal"),
    ("Cascais",            "Rua Afonso Sanches 71D Cascais Portugal"),
    ("Arrábida",           "Praceta Henrique Moreira 244 Vila Nova de Gaia Portugal"),
    ("Anjos",              "Rua Maria 44 Lisboa Portugal"),
    ("Campo",              "Rua Almeida e Sousa 36B Lisboa Portugal"),
    ("Cais",               "Rua da Boavista 34 Lisboa Portugal"),
    ("Saldanha",           "Av. Defensores de Chaves 77 Lisboa Portugal"),
    ("Alvalade",           "Rua Marquesa de Alorna 19C Lisboa Portugal"),
    ("Vasco da Gama",      "CC Vasco da Gama Lisboa Portugal"),
    ("UBBO",               "Av. Cruzeiro Seixas 5 Amadora Portugal"),
    ("Odivelas",           "Rua Pulido Valente 8 Odivelas Portugal"),
    ("Porto Baixa",        "Rua da Conceição 35 Porto Portugal"),
    ("Porto Matosinhos",   "Rua Sousa Aroso 201 Matosinhos Portugal"),
    ("Porto Bessa",        "Av. do Bessa 300 Porto Portugal"),
    ("Porto MarShopping",  "Avenida Doutor Óscar Lopes Leça da Palmeira Portugal"),
    ("Porto Via Catarina", "Rua de Santa Catarina 312 Porto Portugal"),
]

GLOVO_URL = "https://glovoapp.com/pt/pt/lisboa"
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
    try:
        # Clic en el botón de dirección del header
        clicked = False
        for selector in [
            "[class*='AddressButton']",
            "[class*='addressButton']",
            "button[class*='Address']",
            "header button:first-child",
            "nav button:first-child",
        ]:
            try:
                el = page.locator(selector).first
                if await el.is_visible(timeout=2000):
                    await el.click()
                    await page.wait_for_timeout(1500)
                    clicked = True
                    break
            except Exception:
                continue

        if not clicked:
            try:
                await page.locator("header").locator("button").first.click(timeout=3000)
                await page.wait_for_timeout(1500)
                clicked = True
            except Exception:
                pass

        # Buscar el campo con data-testid exacto
        campo = None
        for selector in [
            "input[data-testid='address-book-search-input']",
            "input[placeholder='Procurar morada']",
            "input[type='search']",
            "input[placeholder*='morada']",
            "input[placeholder*='Procurar']",
        ]:
            try:
                el = page.locator(selector).first
                if await el.is_visible(timeout=3000):
                    campo = el
                    break
            except Exception:
                continue

        if not campo:
            print(f"   Campo de busqueda no encontrado")
            return False

        await campo.click()
        await campo.fill("")
        await asyncio.sleep(0.3)
        await campo.type(direccion, delay=80)
        await page.wait_for_timeout(2500)

        # Seleccionar primera sugerencia
        for selector in [
            "[class*='FindAddressByText_resultsList'] div:first-child",
            "[class*='resultsList'] div:first-child",
            "[class*='results'] li:first-child",
            "ul li:first-child",
            "[role='option']:first-child",
        ]:
            try:
                sug = page.locator(selector).first
                if await sug.is_visible(timeout=3000):
                    await sug.click()
                    await page.wait_for_timeout(2000)
                    break
            except Exception:
                continue

        # Manejar pasos adicionales
        for _ in range(4):
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
                    if await inp.is_visible(timeout=800):
                        await inp.fill("1")
                except Exception:
                    pass

            for texto in ["Confirmar morada", "Confirmar", "Confirm"]:
                try:
                    btn = page.locator(f"text={texto}").first
                    if await btn.is_visible(timeout=800):
                        await btn.click()
                        await page.wait_for_timeout(1500)
                except Exception:
                    pass

        return True

    except Exception as e:
        print(f"   Error direccion: {e}")
        return False


async def ir_a_tienda(page):
    try:
        for selector in [
            "text=Street Smash",
            "a[href*='street-smash']",
        ]:
            try:
                el = page.locator(selector).first
                if await el.is_visible(timeout=3000):
                    await el.click()
                    await page.wait_for_timeout(3000)
                    return True
            except Exception:
                continue

        # Buscar en comida
        try:
            await page.locator("text=Comida").first.click(timeout=3000)
            await page.wait_for_timeout(2000)
            campo = page.locator("input[placeholder*='precisa'], input[placeholder*='need'], input[placeholder*='Procurar']").first
            if await campo.is_visible(timeout=2000):
                await campo.type("Street Smash", delay=80)
                await page.wait_for_timeout(2000)
            resultado = page.locator("text=Street Smash").first
            if await resultado.is_visible(timeout=3000):
                await resultado.click()
                await page.wait_for_timeout(3000)
                return True
        except Exception:
            pass

        return False
    except Exception:
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
            "text": {"type": "plain_text", "text": "Informe Glovo - Street Smash Burgers", "emoji": True}
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"Fecha: {fecha} | {total} tiendas revisadas"}]
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Sin incidencias:* {len(ok_list)}"},
                {"type": "mrkdwn",
