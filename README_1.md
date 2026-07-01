# 🍔 Glovo Menu Monitor — Street Smash Burgers

Revisa automáticamente el menú y promociones de cada tienda en Glovo y envía un informe diario a Slack.

## ¿Qué hace?
- ✅ Revisa todas las tiendas de Portugal (Lisboa + Porto)
- ❌ Detecta productos ausentes/bloqueados comparando con la carta maestra
- 🏷️ Detecta promociones activas en cada tienda
- 📍 Verifica qué tienda física está sirviendo cada zona
- 📤 Envía informe a Slack todos los días a las 12:30

---

## Instalación (una sola vez)

### 1. Crea el repositorio en GitHub
- Ve a github.com → "New repository"
- Nombre: `glovo-monitor`
- Privado ✅
- Sube estos archivos

### 2. Añade el Slack Webhook como secreto
- En tu repositorio GitHub → **Settings** → **Secrets and variables** → **Actions**
- Clic en **"New repository secret"**
- Nombre: `SLACK_WEBHOOK_URL`
- Valor: tu URL de Slack (https://hooks.slack.com/services/...)

### 3. Activa GitHub Actions
- Ve a la pestaña **Actions** en tu repositorio
- Acepta activar los workflows

### 4. ¡Listo!
El script se ejecutará automáticamente cada día a las 12:30 hora de Madrid.

---

## Ejecución manual
Desde la pestaña **Actions** → **Glovo Menu Monitor** → **Run workflow**

## Ejecución local (para probar)
```bash
pip install -r requirements.txt
playwright install chromium
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/TU_URL"
python glovo_monitor.py
```

---

## Añadir nuevas tiendas
Edita la lista `TIENDAS` en `glovo_monitor.py`:
```python
TIENDAS = [
    ("Nombre tienda", "Dirección completa Ciudad"),
    ...
]
```

## Actualizar la carta maestra
Edita la lista `CARTA_MAESTRA` en `glovo_monitor.py`.

---

## Ejemplo de informe Slack

```
🍔 Informe Glovo — Street Smash Burgers
📅 01/07/2026 12:30 | 17 tiendas revisadas

✅ Sin incidencias: 14   ❌ Con incidencias: 3

❌ TIENDAS CON PRODUCTOS AUSENTES
Campo de Ourique — R. Almeida e Sousa 36b
• ~Truffle Burger~
• ~Truffle Combo~
🏷️ -10% em alguns artigos | -20% com o Prime

✅ TIENDAS OK
✅ Saldanha — -10% em alguns artigos
✅ Cais do Sodré — Sin promos
...
```
