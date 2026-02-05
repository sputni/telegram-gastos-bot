from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
from openai import OpenAI
import sqlite3
import json
from datetime import datetime, timedelta
import os

# === Variables de entorno ===
TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

if not TOKEN or not OPENAI_KEY:
    print("ERROR: Faltan variables de entorno. Revisa Railway.")
    exit(1)

# Cliente OpenAI
client = OpenAI(api_key=OPENAI_KEY)

# Base de datos
conn = sqlite3.connect("gastos.db")
c = conn.cursor()
c.execute("""
CREATE TABLE IF NOT EXISTS gastos(
    fecha TEXT,
    concepto TEXT,
    monto REAL,
    categoria TEXT
)
""")
c.execute("""
CREATE TABLE IF NOT EXISTS ingresos(
    fecha TEXT,
    monto REAL,
    descripcion TEXT
)
""")
conn.commit()

# === Función para registrar gastos e ingresos ===
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()

    if "sueldo" in text or "ingreso" in text:
        # Registrar ingreso
        try:
            prompt = f"""
Devuelve estrictamente este JSON, sin texto adicional:

{{
  "monto": numero,
  "descripcion": "..."
}}

Texto: {text}
"""
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}]
            )
            data = json.loads(resp.choices[0].message.content)
            monto = data["monto"]
            descripcion = data["descripcion"]
            fecha = datetime.today().strftime("%Y-%m-%d")

            c.execute("INSERT INTO ingresos VALUES (?,?,?)", (fecha, monto, descripcion))
            conn.commit()
            await update.message.reply_text(f"💰 Ingreso registrado: {descripcion} - ${monto}")
        except Exception as e:
            await update.message.reply_text(f"❌ Error al registrar ingreso:\n{e}")
        return

    # Registrar gasto
    try:
        prompt = f"""
Devuelve estrictamente este JSON, sin texto adicional:

{{
  "concepto": "...",
  "monto": numero,
  "fecha": "YYYY-MM-DD",
  "categoria": "..."
}}

Texto: {text}
"""
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        data = json.loads(resp.choices[0].message.content)
        fecha = data.get("fecha", datetime.today().strftime("%Y-%m-%d"))
        c.execute("INSERT INTO gastos VALUES (?,?,?,?)",
                  (fecha, data["concepto"], data["monto"], data["categoria"]))
        conn.commit()
        await update.message.reply_text(f"💸 Gasto registrado: {data['concepto']} - ${data['monto']} ({data['categoria']})")
    except Exception as e:
        await update.message.reply_text(f"❌ Error al registrar gasto:\n{e}")

# === Función para generar reportes ===
async def reporte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    hoy = datetime.today()
    fecha_inicio = None

    if not args or args[0].lower() == "mes":
        fecha_inicio = hoy.replace(day=1)
    elif args[0].lower() == "semana":
        fecha_inicio = hoy - timedelta(days=7)
    elif args[0].lower() == "15dias":
        fecha_inicio = hoy - timedelta(days=15)
    elif args[0].lower() == "dia":
        fecha_inicio = hoy
    else:
        await update.message.reply_text("Parámetro inválido. Usa: dia, semana, 15dias o mes")
        return

    # Gastos
    c.execute("SELECT concepto, monto, fecha, categoria FROM gastos WHERE fecha >= ?", (fecha_inicio.strftime("%Y-%m-%d"),))
    gastos = c.fetchall()
    total_gastos = sum(row[1] for row in gastos)

    # Ingresos
    c.execute("SELECT monto FROM ingresos WHERE fecha >= ?", (fecha_inicio.strftime("%Y-%m-%d"),))
    ingresos = c.fetchall()
    total_ingresos = sum(row[0] for row in ingresos)

    disponible = total_ingresos - total_gastos

    # Preparar texto
    texto = f"📊 Resumen de {args[0] if args else 'mes'}:\n\n"
    if gastos:
        texto += "Gastos:\n"
        categorias = {}
        for concepto, monto, fecha, categoria in gastos:
            texto += f"{fecha} - {concepto} (${monto}) [{categoria}]\n"
            categorias[categoria] = categorias.get(categoria, 0) + monto
        texto += "\nPor categoría:\n"
        for cat, monto in categorias.items():
            texto += f"{cat}: ${monto}\n"
    else:
        texto += "No hay gastos registrados.\n"

    texto += f"\n💰 Total gastos: ${total_gastos}\n"
    texto += f"💵 Total ingresos: ${total_ingresos}\n"
    texto += f"💸 Dinero disponible: ${disponible}"

    await update.message.reply_text(texto)

# === Crear el bot y agregar handlers ===
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT, handle))
app.add_handler(CommandHandler("reporte", reporte))

print("Bot de gastos completo iniciado correctamente")
app.run_polling()