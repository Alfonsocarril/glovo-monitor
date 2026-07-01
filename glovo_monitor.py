"""
Glovo Menu Monitor — Street Smash Burgers
Revisa el menu y promociones de cada tienda en Glovo y envia informe a Slack.
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
    ("Campo de Ourique",  "Rua Almeida e Sousa 36B Lisboa"),
    ("Saldanha",          "Avenida Defensores de Chaves 77 Lisboa"),
    ("Cais do Sodre",     "Rua da Boavista 34 Lisboa"),
    ("Anjos",             "Rua de Anjos 78 Lisboa"),
    ("Alvalade",          "Avenida da Igreja 8 Lisboa"),
    ("Cascais",           "Rua Frederico Arouca 50 Cascais"),
    ("Odivelas",          "Rua Egas Moniz 10 Odivelas"),
    ("Vasco da Gama",     "Avenida Dom Joao II Lisboa"),
    ("UBBO",              "Estrada de Alfragide Amadora"),
    ("Almada",            "Praca do Chile 1 Almada"),
    ("Arrabida",          "Rua Particular da Arrabida Vila Nova de Gaia"),
    ("Junqueiro",         "Avenida Guerra Junqueiro 30 Lisboa"),
    ("Porto Baixa",       "Rua de Santa Catarina 10 Porto"),
    ("Porto Matosinhos",  "Rua Roberto Ivens 10 Matosinhos"),
    ("Porto Bessa",       "Avenida da Boavista 700 Porto"),
    ("Porto MarShopping", "Avenida Meneres Matosinhos"),
    ("Porto Via Catarina","Rua de Santa Catarina 312 Porto"),
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
        # Clic en el header para abrir el selector de direccion
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

        # Encontrar campo de busqueda
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
                direccion
