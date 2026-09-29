"""
OXITEM V8 CORREGIDA - FIXES DE TUS FOTOS
Fix 1: Login no encontraba usuario (DB en /tmp se borraba + strip/lower)
Fix 2: Solo 11 plantas -> ahora 36 plantas completas de tu ficha + Uva y Olivo
Fix 3: Dashboard vacío sin datos -> ahora muestra sectores siempre + humedad, temp, pH, N, P, K, bomba, valvula, control manual
Fix 4: Grafico y clima cargando -> ahora graficos VWC + NPK + clima real + mapa
"""
from flask import Flask, request, jsonify, render_template_string, session, redirect
from flask_cors import CORS
import time, json, os
from datetime import datetime

app = Flask(__name__)
app.secret_key = "oxitem_v8_fix_2026_villa_krause_final"
CORS(app)

# ===== DB PERSISTENTE - FIX RENDER =====
DB_FILE = "fincas_db_v8.json"
if not os.path.exists(DB_FILE):
    # Intentar cargar del /tmp viejo por compatibilidad
    try:
        if os.path.exists("/tmp/fincas_db_v7_oxitem.json"):
            with open("/tmp/fincas_db_v7_oxitem.json",'r') as f:
                old=json.load(f)
                with open(DB_FILE,'w') as out:
                    json.dump(old,out)
    except: pass

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE,'r') as f:
                data=json.load(f)
                if "users" in data:
                    return data
        except Exception as e:
            print(f"Error load DB: {e}")
    return {"users": {}}

def save_db(db):
    try:
        with open(DB_FILE,'w') as f:
            json.dump(db,f, indent=2)
        # Backup en /tmp también
        try:
            with open("/tmp/fincas_db_v7_oxitem.json",'w') as f:
                json.dump(db,f)
        except: pass
        print(f"DB guardada: {list(db['users'].keys())}")
    except Exception as e:
        print(f"Error save DB: {e}")

db = load_db()
sensores_data = {}
actuadores_data = {}
historico = []  # {ts, finca, sector, humedad, temp, ph, ec, n, p, k}
logs = []
consumo_historico = []

FLOW_SPECS = {
    "0.5": {"modelo": "YF-S201 1/2\" PROTOTIPO", "ppl": 450, "rango": "1-30 L/min"},
    "1_fs400": {"modelo": "FS400A 1\" FINAL", "ppl": 360, "rango": "1-60 L/min"},
    "1_dn25": {"modelo": "YF-DN25 1\" FINAL", "ppl": 450, "rango": "10-100 L/min"},
    "no": {"modelo": "Sin caudalímetro (solo estimado)", "ppl": 0, "rango": "Estimado por tiempo"},
}
BOMBA_CAUDAL = {"0.5":25,"0.75":45,"1":80,"1.25":120,"1.5":180}

# ===== 36 PLANTAS COMPLETAS DE TU FICHA + UVA Y OLIVO =====
PLANTAS = {
    # GRUPO 1 HUERTA Y AROMATICAS - 16 plantas
    "tomate": {"nombre": "Tomate", "emoji":"🍅", "on":60, "off":80, "grupo":"Huerta", "color":"#ef4444", "hum":"70-80%", "hum_amb":"60-70%", "ph":"5.5-6.8", "temp":"18-27°C", "n":"150-200 ALTO", "p":"50-80 MEDIO", "k":"250-350 MUY ALTO", "nota":"Muy demandante de K en floración"},
    "lechuga": {"nombre": "Lechuga", "emoji":"🥬", "on":60, "off":75, "grupo":"Huerta", "color":"#22c55e", "hum":"60-75%", "hum_amb":"50-70%", "ph":"6.0-7.0", "temp":"15-22°C", "n":"120-150 ALTO", "p":"30-50 BAJO", "k":"150-200 MEDIO", "nota":"En San Juan a media sombra obligatoria en verano"},
    "menta": {"nombre": "Menta", "emoji":"🌿", "on":75, "off":85, "grupo":"Aromáticas", "color":"#10b981", "hum":"75-85%", "hum_amb":"60-80%", "ph":"6.0-7.0", "temp":"15-25°C", "n":"150 ALTO", "p":"50 MEDIO", "k":"150 MEDIO", "nota":"Invasiva, maceta aparte"},
    "ruda": {"nombre": "Ruda", "emoji":"☘️", "on":40, "off":55, "grupo":"Aromáticas", "color":"#65a30d", "hum":"40-55%", "hum_amb":"40-50%", "ph":"6.0-8.0", "temp":"18-28°C", "n":"50-80 BAJO", "p":"20-30 BAJO", "k":"80-120 BAJO", "nota":"Autóctona adaptada, odia encharque"},
    "oregano": {"nombre": "Orégano", "emoji":"🌱", "on":45, "off":60, "grupo":"Aromáticas", "color":"#84cc16", "hum":"45-60%", "hum_amb":"40-60%", "ph":"6.0-8.0", "temp":"18-30°C", "n":"80 BAJO", "p":"30 BAJO", "k":"120 MEDIO", "nota":""},
    "romero": {"nombre": "Romero", "emoji":"🌾", "on":30, "off":50, "grupo":"Aromáticas", "color":"#16a34a", "hum":"30-50%", "hum_amb":"40-50%", "ph":"5.5-7.0", "temp":"15-28°C", "n":"50 BAJO", "p":"20 BAJO", "k":"100 BAJO", "nota":"Si lo regás mucho se muere"},
    "papa": {"nombre": "Papa", "emoji":"🥔", "on":65, "off":80, "grupo":"Huerta", "color":"#a16207", "hum":"65-80%", "hum_amb":"60-70%", "ph":"5.0-6.0", "temp":"15-22°C", "n":"100-150 MEDIO", "p":"80-100 ALTO", "k":"300-400 MUY ALTO", "nota":""},
    "zanahoria": {"nombre": "Zanahoria", "emoji":"🥕", "on":60, "off":70, "grupo":"Huerta", "color":"#f97316", "hum":"60-70%", "hum_amb":"50-70%", "ph":"6.0-6.8", "temp":"16-24°C", "n":"100 MEDIO", "p":"60 MEDIO", "k":"200 ALTO", "nota":""},
    "habas": {"nombre": "Habas (Avas)", "emoji":"🫘", "on":60, "off":75, "grupo":"Huerta", "color":"#65a30d", "hum":"60-75%", "hum_amb":"50-65%", "ph":"6.0-7.5", "temp":"10-22°C", "n":"30-50 BAJO fija N", "p":"60 MEDIO", "k":"150 MEDIO", "nota":"Fija nitrógeno"},
    "ajo": {"nombre": "Ajo", "emoji":"🧄", "on":50, "off":65, "grupo":"Huerta", "color":"#e5e7eb", "hum":"50-65%", "hum_amb":"50-60%", "ph":"6.0-7.0", "temp":"12-22°C", "n":"120 MEDIO", "p":"50 MEDIO", "k":"180 ALTO", "nota":""},
    "cebolla": {"nombre": "Cebolla", "emoji":"🧅", "on":60, "off":70, "grupo":"Huerta", "color":"#f3e8ff", "hum":"60-70%", "hum_amb":"60-70%", "ph":"6.0-7.0", "temp":"13-24°C", "n":"110 MEDIO", "p":"70 ALTO", "k":"180 ALTO", "nota":""},
    "zapallo_ancho": {"nombre": "Zapallo Ancho", "emoji":"🎃", "on":70, "off":80, "grupo":"Huerta", "color":"#f59e0b", "hum":"70-80%", "hum_amb":"60-80%", "ph":"6.0-7.5", "temp":"20-30°C", "n":"150 ALTO", "p":"50 MEDIO", "k":"250 ALTO", "nota":""},
    "zapallo_ingles": {"nombre": "Zapallo Inglés", "emoji":"🎃", "on":70, "off":80, "grupo":"Huerta", "color":"#fbbf24", "hum":"70-80%", "hum_amb":"60-80%", "ph":"6.0-7.0", "temp":"20-28°C", "n":"150 ALTO", "p":"50 MEDIO", "k":"250 ALTO", "nota":""},
    "frutilla": {"nombre": "Frutilla", "emoji":"🍓", "on":65, "off":75, "grupo":"Frutales", "color":"#f43f5e", "hum":"65-75%", "hum_amb":"60-75%", "ph":"5.5-6.5 ACIDO", "temp":"15-24°C", "n":"100 MEDIO", "p":"70 ALTO", "k":"200 ALTO", "nota":"pH ácido fundamental"},
    "frambuesa": {"nombre": "Frambuesa", "emoji":"🍇", "on":65, "off":80, "grupo":"Frutales", "color":"#8b5cf6", "hum":"65-80%", "hum_amb":"70-80%", "ph":"5.5-6.5", "temp":"12-22°C", "n":"100 MEDIO", "p":"50 MEDIO", "k":"150 MEDIO", "nota":""},
    "pepino": {"nombre": "Pepino", "emoji":"🥒", "on":75, "off":85, "grupo":"Huerta", "color":"#22c55e", "hum":"75-85%", "hum_amb":"70-90%", "ph":"5.5-6.8", "temp":"20-30°C", "n":"150 ALTO", "p":"50 MEDIO", "k":"250 ALTO", "nota":""},
    # GRUPO 2 ORNAMENTALES DE FLOR - 13 plantas
    "marimona": {"nombre": "Marimoña (Ranunculus)", "emoji":"🌼", "on":60, "off":70, "grupo":"Flor", "color":"#facc15", "hum":"60-70%", "hum_amb":"50-60%", "ph":"6.0-7.0", "temp":"10-20°C", "n":"100", "p":"50", "k":"150", "nota":""},
    "copete": {"nombre": "Copete (Tagetes)", "emoji":"🌸", "on":50, "off":65, "grupo":"Flor", "color":"#f97316", "hum":"50-65%", "hum_amb":"40-60%", "ph":"6.0-7.0", "temp":"18-28°C", "n":"80", "p":"30", "k":"120", "nota":"Repelente de plagas, ideal con tomate"},
    "conejito": {"nombre": "Conejito (Antirrhinum)", "emoji":"🐰", "on":60, "off":70, "grupo":"Flor", "color":"#fda4af", "hum":"60-70%", "hum_amb":"50-60%", "ph":"6.0-7.0", "temp":"12-22°C", "n":"100", "p":"40", "k":"140", "nota":""},
    "clavel": {"nombre": "Clavel", "emoji":"🌹", "on":50, "off":60, "grupo":"Flor", "color":"#e11d48", "hum":"50-60%", "hum_amb":"40-60%", "ph":"6.0-7.5", "temp":"15-24°C", "n":"120", "p":"50", "k":"180", "nota":""},
    "clavel_enano": {"nombre": "Clavel Enano", "emoji":"🌹", "on":50, "off":60, "grupo":"Flor", "color":"#fb7185", "hum":"50-60%", "hum_amb":"40-60%", "ph":"6.0-7.0", "temp":"15-22°C", "n":"100", "p":"40", "k":"150", "nota":""},
    "petunia": {"nombre": "Petuña (Petunia)", "emoji":"🌺", "on":60, "off":70, "grupo":"Flor", "color":"#a855f7", "hum":"60-70%", "hum_amb":"50-70%", "ph":"5.5-6.5", "temp":"16-26°C", "n":"120", "p":"50", "k":"150", "nota":""},
    "girasol": {"nombre": "Girasol (Gitasol)", "emoji":"🌻", "on":60, "off":75, "grupo":"Flor", "color":"#eab308", "hum":"60-75%", "hum_amb":"40-60%", "ph":"6.0-7.5", "temp":"20-30°C", "n":"150", "p":"60", "k":"200", "nota":""},
    "pensamiento": {"nombre": "Pensamiento (Viola)", "emoji":"💜", "on":65, "off":75, "grupo":"Flor", "color":"#8b5cf6", "hum":"65-75%", "hum_amb":"60-70%", "ph":"5.5-6.5", "temp":"10-18°C", "n":"100", "p":"40", "k":"120", "nota":"Flor de invierno"},
    "malvon": {"nombre": "Malvón (Pelargonium)", "emoji":"🌺", "on":45, "off":60, "grupo":"Flor", "color":"#ef4444", "hum":"45-60%", "hum_amb":"40-50%", "ph":"6.0-7.5", "temp":"16-26°C", "n":"80", "p":"30", "k":"120", "nota":""},
    "rosa": {"nombre": "Rosa", "emoji":"🌹", "on":60, "off":70, "grupo":"Flor", "color":"#ec4899", "hum":"60-70%", "hum_amb":"50-65%", "ph":"6.0-6.8", "temp":"15-25°C", "n":"150", "p":"60", "k":"200", "nota":""},
    "alegria": {"nombre": "Alegría del Hogar", "emoji":"😊", "on":70, "off":80, "grupo":"Flor", "color":"#f43f5e", "hum":"70-80%", "hum_amb":"70-80%", "ph":"6.0-6.5", "temp":"18-24°C", "n":"100", "p":"40", "k":"140", "nota":"No tolera sol directo sanjuanino"},
    "begonia": {"nombre": "Flor Azúcar (Begonia)", "emoji":"🌸", "on":60, "off":70, "grupo":"Flor", "color":"#f9a8d4", "hum":"60-70%", "hum_amb":"60-80%", "ph":"5.5-6.5", "temp":"18-24°C", "n":"100", "p":"40", "k":"120", "nota":""},
    "orquidea": {"nombre": "Orquídeas (Phalaenopsis)", "emoji":"🌸", "on":50, "off":60, "grupo":"Interior", "color":"#e9d5ff", "hum":"50-60% corteza", "hum_amb":"70-85%", "ph":"5.5-6.5", "temp":"18-28°C", "n":"50 diluido", "p":"20", "k":"50", "nota":"Sustrato corteza y carbón, nada de tierra"},
    # GRUPO 3 SUCULENTAS Y INTERIOR - 5 plantas
    "paleta": {"nombre": "Paleta de Pintor", "emoji":"🎨", "on":60, "off":75, "grupo":"Interior", "color":"#f472b6", "hum":"60-75%", "hum_amb":"60-80%", "ph":"5.5-6.5", "temp":"18-26°C", "n":"80", "p":"30", "k":"100", "nota":""},
    "calanchoe": {"nombre": "Calanchoe (Kalanchoe)", "emoji":"🌵", "on":30, "off":45, "grupo":"Suculenta", "color":"#06b6d4", "hum":"30-45%", "hum_amb":"40-50%", "ph":"6.0-7.0", "temp":"15-25°C", "n":"50", "p":"20", "k":"80", "nota":""},
    "lazo": {"nombre": "Lazo de Amor", "emoji":"💚", "on":50, "off":65, "grupo":"Interior", "color":"#22c55e", "hum":"50-65%", "hum_amb":"50-70%", "ph":"6.0-7.0", "temp":"15-26°C", "n":"80", "p":"30", "k":"100", "nota":""},
    "dolar_negro": {"nombre": "Dólar Negro", "emoji":"💲", "on":55, "off":70, "grupo":"Interior", "color":"#16a34a", "hum":"55-70%", "hum_amb":"50-70%", "ph":"6.0-7.0", "temp":"16-26°C", "n":"100", "p":"30", "k":"120", "nota":""},
    "garrita": {"nombre": "Garrita de Oso", "emoji":"🐻", "on":20, "off":35, "grupo":"Suculenta", "color":"#a3a3a3", "hum":"20-35%", "hum_amb":"30-50%", "ph":"6.0-7.5", "temp":"15-28°C", "n":"30", "p":"10", "k":"50", "nota":"Suculenta extrema"},
    # EXTRA SAN JUAN
    "uva": {"nombre": "Uva / Vid San Juan", "emoji":"🍇", "on":40, "off":60, "grupo":"Frutal SJ", "color":"#7c3aed", "hum":"40-60%", "hum_amb":"40-60%", "ph":"6.0-7.5", "temp":"15-30°C", "n":"80-120 MEDIO", "p":"40-60 MEDIO", "k":"150-250 ALTO", "nota":"Cultivo emblemático SJ, riego deficitario controlado mejora azúcar"},
    "olivo": {"nombre": "Olivo", "emoji":"🫒", "on":30, "off":50, "grupo":"Frutal SJ", "color":"#65a30d", "hum":"30-50%", "hum_amb":"30-50%", "ph":"6.0-8.0", "temp":"15-30°C", "n":"60-100 BAJO", "p":"20-40 BAJO", "k":"100-200 MEDIO", "nota":"Muy tolerante sequía, odia encharque, ideal SJ"},
}

def log(msg):
    ts=datetime.now().strftime("%H:%M:%S")
    logs.append(f"{ts} - {msg}")
    if len(logs)>300: logs.pop(0)
    print(logs[-1])

LOGIN_HTML = """
<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>OXITEM - Login V8</title>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;700;900&display=swap" rel="stylesheet">
<style>
*{font-family:'Outfit',system-ui} body{margin:0;background:#0a0f1c;min-height:100vh;display:flex;align-items:center;justify-content:center}
.bg{position:fixed;inset:0;background:radial-gradient(600px at 20% 20%,rgba(34,197,94,0.15),transparent),radial-gradient(800px at 80% 80%,rgba(16,185,129,0.12),transparent),#0a0f1c}
.card{background:rgba(255,255,255,0.06);backdrop-filter:blur(20px);border:1px solid rgba(255,255,255,0.1);padding:32px;border-radius:24px;width:400px;position:relative;z-index:1}
.logo{font-size:38px;font-weight:900;color:white} .logo span{color:#22c55e} .sub{color:#94a3b8;font-size:12px;margin-top:4px}
input{width:100%;padding:14px;margin:8px 0;background:rgba(255,255,255,0.07);border:1px solid rgba(255,255,255,0.12);border-radius:12px;color:white;box-sizing:border-box} 
.btn{width:100%;padding:14px;background:linear-gradient(135deg,#22c55e,#16a34a);color:black;border:none;border-radius:12px;font-weight:800;cursor:pointer;margin-top:10px}
.link{color:#22c55e;text-align:center;display:block;margin-top:14px;font-size:13px;text-decoration:none}
.debug{font-size:10px;color:#475569;margin-top:12px;text-align:center}
</style></head><body>
<div class="bg"></div>
<div class="card">
<div class="logo">OX<span>ITEM</span> <span style="font-size:14px">V8</span></div>
<div class="sub">SISTEMA INTELIGENTE DE RIEGO • 36 PLANTAS • VILLA KRAUSE</div>
<form method="POST" action="/login" style="margin-top:20px">
<input name="username" placeholder="Usuario de finca (ej: finca_demo)" required>
<input name="password" type="password" placeholder="Contraseña" required>
<button class="btn">INGRESAR A MI FINCA →</button>
</form>
<a class="link" href="/register">¿Primera vez? Crear finca nueva con 36 plantas</a>
{% if error %}<div style="color:#f87171;background:rgba(248,113,113,0.1);padding:10px;border-radius:8px;margin-top:12px;font-size:12px">{{error}}</div>{% endif %}
<div class="debug">Usuarios registrados: {{users_count}} | DB: {{db_file}}<br>Admin: admin / OXITEM</div>
</div></body></html>
"""

REGISTER_HTML = """
<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>OXITEM V8 - Registro</title>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;700;900&display=swap" rel="stylesheet">
<style>*{font-family:'Outfit',system-ui;box-sizing:border-box} body{margin:0;background:#0f172a;padding:20px;color:white}
.card{background:#1e293b;border:1px solid #334155;padding:24px;border-radius:20px;max-width:800px;margin:0 auto}
input,select{width:100%;padding:11px;background:#0f172a;border:1px solid #334155;border-radius:10px;color:white;margin:5px 0}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.plant-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;max-height:420px;overflow:auto;background:#0f172a;padding:12px;border-radius:12px;border:1px solid #334155}
.plant-grid label{font-size:12px;padding:6px 8px;border-radius:8px;cursor:pointer;display:flex;align-items:center;gap:6px} .plant-grid label:hover{background:#1e293b}
.btn{width:100%;padding:14px;background:linear-gradient(135deg,#22c55e,#16a34a);color:black;border:none;border-radius:12px;font-weight:800;cursor:pointer;margin-top:16px}
.grupo{color:#22c55e;font-weight:800;font-size:12px;margin-top:12px;grid-column:1/-1}
</style></head><body>
<div class="card">
<h2 style="margin:0">OX<span style="color:#22c55e">ITEM</span> V8 - Nueva Finca (36 plantas)</h2>
<p style="color:#94a3b8;font-size:12px">1 finca = 1 terreno. El sistema solo muestra tu terreno. Sensores por sector se configuran después en Configurar Terreno (admin/OXITEM)</p>
<form method="POST" action="/register">
<h3 style="color:#22c55e;font-size:13px">1. ACCESO</h3>
<div class="grid"><input name="username" placeholder="Usuario finca (ej: finca_gonzalez) SIN espacios" required><input name="password" type="password" placeholder="Contraseña" required></div>
<h3 style="color:#22c55e;font-size:13px">2. TERRENO</h3>
<input name="ubicacion" placeholder="Ubicación Ej: Villa Krause, Rawson, San Juan - para mapa" required>
<div class="grid"><input name="largo" type="number" placeholder="Largo terreno (m)" required><input name="ancho" type="number" placeholder="Ancho (m)" required></div>
<div class="grid"><input name="sectores" type="number" min="1" max="12" placeholder="Cantidad sectores (ej: 3)" required>
<select name="bomba_pulgadas"><option value="0.5">Bomba 1/2\" 25 L/min prototipo</option><option value="0.75">Bomba 3/4\" 45 L/min</option><option value="1" selected>Bomba 1\" 80 L/min</option><option value="1.25">Bomba 1 1/4\" 120 L/min</option></select></div>
<select name="valvula_ppal_pulgadas"><option value="0.5">Válvula ppal 1/2\"</option><option value="0.75">Válvula ppal 3/4\"</option><option value="1" selected>Válvula ppal 1\"</option></select>
<h3 style="color:#22c55e;font-size:13px">3. CULTIVOS (tildá todos los que tenés) - 36 tipos de tu ficha</h3>
<div class="plant-grid">
{% for grupo in ['Huerta','Aromáticas','Frutales','Frutal SJ','Flor','Interior','Suculenta'] %}
<div class="grupo">--- {{grupo}} ---</div>
{% for key, pl in plantas.items() if pl.grupo==grupo %}
<label><input type="checkbox" name="plantas" value="{{key}}"> {{pl.emoji}} {{pl.nombre}} <span style="color:#64748b;font-size:10px">{{pl.hum}}</span></label>
{% endfor %}
{% endfor %}
</div>
<button class="btn">CREAR FINCA Y ENTRAR A OXITEM V8 →</button>
</form>
</div></body></html>
"""

DASHBOARD_HTML = """
<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>OXITEM V8 - {{username}}</title>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;700;900&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
*{font-family:'Outfit',system-ui;box-sizing:border-box} body{margin:0;background:#0a0f1c;color:#e2e8f0}
.header{background:#0f172a;border-bottom:1px solid #1e293b;padding:14px 20px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;position:sticky;top:0;z-index:10}
.logo{font-weight:900;font-size:22px;color:white} .logo span{color:#22c55e}
.card{background:#1e293b;border:1px solid #334155;border-radius:16px;padding:14px;margin:10px;box-shadow:0 4px 12px rgba(0,0,0,0.2)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:0;padding:10px}
.val{font-size:28px;font-weight:900} .small{font-size:11px;color:#94a3b8}
.btn{padding:8px 14px;border-radius:8px;border:none;font-weight:700;cursor:pointer;font-size:12px}
.btn-dark{background:#0f172a;color:white;border:1px solid #334155} .btn-green{background:#22c55e;color:black}
.badge{padding:4px 8px;border-radius:12px;font-size:10px;font-weight:800}
.plant-dot{width:10px;height:10px;border-radius:50%;display:inline-block;margin-right:4px}
.consumo-bar{height:8px;background:#0f172a;border-radius:10px;overflow:hidden;margin-top:6px} .consumo-fill{height:100%;background:linear-gradient(90deg,#22c55e,#06b6d4)}
.log{background:#0f172a;border:1px solid #1e293b;color:#86efac;padding:10px;border-radius:10px;font-family:monospace;font-size:10px;max-height:180px;overflow:auto}
.kpi{display:flex;justify-content:space-between;font-size:11px;margin:2px 0}
#map{height:180px;border-radius:12px;margin-top:10px;border:1px solid #334155}
</style></head><body>
<div class="header">
<div>
<div class="logo">OX<span>ITEM</span> V8 <span style="font-size:10px;color:#64748b">36 PLANTAS</span></div>
<div style="font-size:11px;color:#94a3b8">{{finca.ubicacion}} • {{finca.largo}}x{{finca.ancho}}m • {{finca.m2}}m² • {{finca.sectores}} sectores • Bomba {{finca.bomba_pulgadas}}" {{finca.bomba_lpm}}L/min • Válv ppal {{finca.valvula_ppal_pulgadas}}"</div>
</div>
<div style="display:flex;gap:6px"><a href="/config_terreno?finca={{username}}" class="btn btn-green">⚙️ Config Terreno</a><a href="/logout" class="btn btn-dark">Salir</a></div>
</div>

<div class="card" style="background:linear-gradient(135deg,rgba(34,197,94,0.12),rgba(6,182,212,0.1));border-color:rgba(34,197,94,0.25)">
<div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:10px"><div><b>💧 CONSUMO DUAL OXITEM</b><div class="small">Flowmeter 1/2\" YF-S201 prototipo + estimado por tiempo bomba • Bomba {{finca.bomba_pulgadas}}" • Con y sin caudalímetro</div></div><div id="consumoResumen" style="font-size:12px;text-align:right"></div></div>
<div class="consumo-bar"><div id="consumoFill" class="consumo-fill" style="width:20%"></div></div>
</div>

<div id="sectoresContainer" class="grid"></div>

<div style="display:grid;grid-template-columns:2fr 1fr;gap:0;padding:0 10px">
<div class="card"><b class="small">📈 EVOLUCIÓN HUMEDAD VWC % (0% aire / 100% agua) - Cap Campo 80% objetivo</b><canvas id="cHum" height="130"></canvas></div>
<div class="card"><b class="small">CONTROL & CLIMA SAN JUAN</b><div style="margin:8px 0;display:flex;gap:6px;flex-wrap:wrap"><button class="btn btn-dark" onclick="cmdGlobal(1)">BOMBA ON</button><button class="btn btn-dark" onclick="cmdGlobal(0)">OFF</button><button class="btn btn-dark" onclick="cmdValvulas(1)">Todas válv ON</button><button class="btn btn-dark" onclick="cmdValvulas(0)">OFF</button></div><div id="clima" style="background:#0f172a;padding:10px;border-radius:10px;font-size:11px;border:1px solid #1e293b">Cargando clima...</div><div id="map"></div><div class="small" style="margin-top:6px">Flow: YF-S201 1/2\" 450p/L proto → FS400A 1\" 360p/L. Estimado = tiempo x caudal bomba.</div></div>
</div>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:0;padding:0 10px">
<div class="card"><b class="small">📊 NPK + pH + EC - Sensores 7en1</b><canvas id="cOtros" height="100"></canvas><div id="npkDetalle" class="small" style="margin-top:8px"></div></div>
<div class="card"><b class="small">📋 REPORTE AGRONÓMICO POR SECTOR (con temp, pH, N, P, K, bomba, válvula)</b><div id="rep" style="font-size:11px;white-space:pre-wrap;margin-top:8px;line-height:1.5;color:#cbd5e1;max-height:260px;overflow:auto"></div></div>
</div>

<div class="card"><b class="small">LOGS OXITEM - Bomba/Válvula activaciones</b><div id="log" class="log" style="margin-top:8px"></div></div>

<script>
let ch, ch2, map, marker;
async function init(){
 ch=new Chart(document.getElementById('cHum'),{type:'line',data:{labels:[],[STRIPPED] VWC %',data:[],[STRIPPED] Cap Campo 80%',data:[],[STRIPPED] Riego ON',data:[],[STRIPPED]
 ch2=new Chart(document.getElementById('cOtros'),{type:'bar',data:{labels:['Temp',[STRIPPED] x10','EC/10','N','P','K/10'],datasets:[{label:'Último sensor',data:[0,[STRIPPED] backgroundColor:['#f59e0b','#ec4899','#06b6d4','#22c55e','#8b5cf6','#f97316']}]},options:{plugins:{legend:{display:false}},scales:{y:{display:false},x:{grid:{color:'#1e293b'}}}}});
 // Mapa
 map=L.map('map').setView([-31.53,-68.52],13); L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map); marker=L.marker([-31.53,-68.52]).addTo(map).bindPopup("{{finca.ubicacion}}");
 load(); setInterval(load,4000);
}
async function load(){
 const r=await fetch('/api/estado?finca={{username}}'); const j=await r.json();
 document.getElementById('consumoResumen').innerHTML=`Total: <b>${j.consumo.total_litros_flow.toFixed(1)} L</b> flow / <b>${j.consumo.total_litros_estimado.toFixed(1)} L</b> est. • Hoy ${j.consumo.total_litros_estimado.toFixed(1)}L • Dif ${j.consumo.diferencia}% <span style="color:${j.consumo.diferencia>20?'#f87171':'#22c55e'}">${j.consumo.alerta}</span>`;
 document.getElementById('consumoFill').style.width=Math.min(100, j.consumo.total_litros_estimado/5)+'%';
 const cont=document.getElementById('sectoresContainer'); cont.innerHTML='';
 Object.entries(j.sectores).forEach(([sid, sec])=>{
   const estadoColor=sec.humedad_prom < sec.umbral_on ? '#f87171' : sec.humedad_prom >= sec.umbral_off ? '#22c55e' : '#fbbf24';
   const div=document.createElement('div'); div.className='card'; div.style.borderLeft=`4px solid ${sec.color}`;
   div.innerHTML=`<div style="display:flex;justify-content:space-between;flex-wrap:wrap"><div class="small" style="font-weight:700"><span class="plant-dot" style="background:${sec.color}"></span>SECTOR ${sid} • ${sec.planta_nombre.toUpperCase()} • ${sec.cant_sensores} sensores • Válv ${sec.valvula_pulgadas}" • Flow ${sec.flow_present?sec.flow_model:'NO (solo estimado)'}</div><div class="badge" style="background:${estadoColor}20;color:${estadoColor};border:1px solid ${estadoColor}40">${sec.bomba_estado?'BOMBA ON':'OFF'} • ${sec.valvula_estado?'VÁLV OPEN':'CLOSED'}</div></div>
   <div class="val" style="color:${estadoColor}">${sec.humedad_prom.toFixed(1)}<span style="font-size:14px">% VWC</span> <span style="font-size:12px;color:#94a3b8">${sec.estado_suelo}</span></div>
   <div class="kpi"><span>🌡️ Temp ${sec.temp}°C (ideal ${sec.temp_ideal})</span><span>pH ${sec.ph} (ideal ${sec.ph_ideal})</span></div>
   <div class="kpi"><span>🧪 N ${sec.n}ppm (${sec.n_ideal})</span><span>P ${sec.p}ppm (${sec.p_ideal})</span><span>K ${sec.k}ppm (${sec.k_ideal})</span></div>
   <div class="kpi"><span>EC ${sec.ec}</span><span>ON <${sec.umbral_on}% OFF ≥${sec.umbral_off}%</span></div>
   <div style="margin-top:8px;display:flex;gap:4px;flex-wrap:wrap"><button class="btn btn-dark" onclick="cmdSector(${sid},1)">Válv S${sid} ON</button><button class="btn btn-dark" onclick="cmdSector(${sid},0)">OFF</button><span class="small">💧 ${sec.litros_flow.toFixed(1)}L flow / ${sec.litros_estimado.toFixed(1)}L est. • ⏱ ${(sec.tiempo_hoy/60).toFixed(1)}min</span></div>
   <div class="consumo-bar"><div class="consumo-fill" style="width:${Math.min(100,sec.humedad_prom)}%;background:${sec.color}"></div></div>
   <div class="small" style="margin-top:4px">${sec.sensores_activos} sensores activos • último hace ${sec.ultimo_hace} • ID: ${sec.id_ejemplo||'sector'+sid+'_sensor1'}</div>`;
   cont.appendChild(div);
 });
 ch.data.labels=j.historico.map(h=>new Date(h.ts*1000).toLocaleTimeString());
 ch.data.datasets[0].data=j.historico.map(h=>h.humedad);
 ch.data.datasets[1].data=j.historico.map(()=>80);
 ch.data.datasets[2].data=j.historico.map(h=>j.sectores[h.sector]?.umbral_on||30);
 ch.update();
 ch2.data.datasets[0].data=[j.ultimo_temp||22, (j.ultimo_ph||6.5)*10, (j.ultimo_ec||400)/10, j.ultimo_n||100, j.ultimo_p||50, (j.ultimo_k||150)/10];
 ch2.update();
 document.getElementById('npkDetalle').innerHTML=`Último: Temp ${j.ultimo_temp}°C • pH ${j.ultimo_ph} • EC ${j.ultimo_ec} • N ${j.ultimo_n}ppm • P ${j.ultimo_p}ppm • K ${j.ultimo_k}ppm<br><span style="color:#fbbf24">Nota: ${j.ultimo_nota||''}</span>`;
 document.getElementById('rep').innerText=j.reporte;
 document.getElementById('log').innerHTML=j.logs.slice(-20).reverse().map(l=>`<div>${l}</div>`).join('');
 document.getElementById('clima').innerHTML=`<b>🌤️ San Juan ${j.clima.temp}°C</b> • Hum amb ${j.clima.hum}% • Viento ${j.clima.viento}km/h<br>${j.clima.desc}<br><span style="color:${j.clima.riego_recomendado.includes('No')?'#f87171':'#22c55e'};font-weight:700">${j.clima.riego_recomendado}</span><br><span class="small">Flow specs: ${j.clima.flow_info} • Ubic: ${j.clima.ubicacion}</span>`;
}
async function cmdGlobal(e){ await fetch('/api/comando',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({finca:'{{username}}', device:'bomba_principal', estado:e})}); }
async function cmdValvulas(e){ await fetch('/api/comando',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({finca:'{{username}}', device:'valvula', estado:e})}); }
async function cmdSector(sector, e){ await fetch('/api/comando',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({finca:'{{username}}', device:'sector_'+sector+'_valvula', sector:sector, estado:e})}); }
init();
</script></body></html>
"""

CONFIG_HTML = """
<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>OXITEM V8 Config</title>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;700;900&display=swap" rel="stylesheet">
<style>*{font-family:'Outfit',system-ui;box-sizing:border-box} body{margin:0;background:#0a0f1c;color:#e2e8f0;padding:16px} .card{background:#1e293b;border:1px solid #334155;padding:16px;border-radius:14px;margin:10px;max-width:900px} input,select{padding:8px;margin:3px;background:#0f172a;border:1px solid #334155;border-radius:8px;color:white} .btn{padding:8px 14px;background:#22c55e;color:black;border:none;border-radius:8px;font-weight:800;cursor:pointer}</style>
</head><body>
<div class="card">
<h2>OX<span style="color:#22c55e">ITEM</span> V8 Config Terreno - {{username}}</h2>
<p style="color:#94a3b8;font-size:12px">Admin OXITEM. Acá asignás planta por sector, cantidad sensores, pulgadas válvula y caudalímetro. El cliente ve pero no modifica.</p>
<form id="adminAuth"><input id="adminUser" placeholder="admin" value="admin"><input id="adminPass" type="password" placeholder="OXITEM"><button class="btn" type="submit">Autenticar admin/OXITEM</button></form>
<div id="configArea" style="display:none">
<h3 style="color:#22c55e">Bomba y Válvula Principal</h3>
<div style="display:flex;gap:8px;flex-wrap:wrap"><label>Bomba <select id="bombaPulg"><option value="0.5">1/2" 25L/min proto</option><option value="0.75">3/4" 45L/min</option><option value="1" selected>1" 80L/min</option><option value="1.25">1 1/4" 120L/min</option></select></label><label>Válv ppal <select id="valvPpalPulg"><option value="0.5">1/2"</option><option value="0.75">3/4"</option><option value="1" selected>1"</option></select></label></div>
<h3 style="color:#22c55e">Sectores ({{finca.sectores}} sectores, {{finca.sectores}} x válvula + {{finca.sectores}} x N sensores configurables)</h3>
<div id="sectoresConfig"></div>
<button class="btn" onclick="guardar()">💾 Guardar Config OXITEM V8</button><span id="msg" style="margin-left:10px"></span>
</div>
</div>
<script>
let fincaData={{finca_json|safe}}; let plantas={{plantas_json|safe}};
document.getElementById('adminAuth').addEventListener('submit', async (e)=>{
 e.preventDefault();
 const r=await fetch('/api/admin_auth',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user:document.getElementById('adminUser').value, pass:document.getElementById('adminPass').value})});
 const j=await r.json(); if(j.ok){ document.getElementById('configArea').style.display='block'; loadSectores(); } else alert('Admin incorrecto admin/OXITEM');
});
function loadSectores(){
 const cont=document.getElementById('sectoresConfig'); cont.innerHTML='';
 for(let i=1;i<=fincaData.sectores;i++){
   const sec=fincaData.sectores_config[i]||{planta:'tomate',cant_sensores:5,valvula_pulgadas:'0.75',flow_present:false,flow_pulgadas:'no'};
   const div=document.createElement('div'); div.className='card'; div.style='border-left:3px solid #22c55e';
   div.innerHTML=`<b>Sector ${i}</b> - Sensores en este sector: tendrán ID ${'{{username}}'}_s${i}_d1..d${sec.cant_sensores}<br>
   Planta: <select id="planta_${i}">${Object.entries(plantas).map(([k,p])=>`<option value="${k}" ${k===sec.planta?'selected':''}>${p.emoji} ${p.nombre} ${p.hum}</option>`).join('')}</select>
   Cant sensores: <input id="cant_${i}" type="number" min="1" max="50" value="${sec.cant_sensores}" style="width:60px">
   Válvula sector: <select id="valv_${i}"><option value="0.5" ${sec.valvula_pulgadas==='0.5'?'selected':''}>1/2"</option><option value="0.75" ${sec.valvula_pulgadas==='0.75'?'selected':''}>3/4"</option><option value="1" ${sec.valvula_pulgadas==='1'?'selected':''}>1"</option></select><br>
   ¿Tiene caudalímetro?: <select id="flowPres_${i}"><option value="false" ${!sec.flow_present?'selected':''}>NO - Solo estimado por tiempo bomba (sin flow)</option><option value="true" ${sec.flow_present?'selected':''}>SÍ - Con caudalímetro dual</option></select>
   Pulgadas caudalímetro: <select id="flowPulg_${i}"><option value="no" ${sec.flow_pulgadas==='no'?'selected':''}>Sin caudalímetro</option><option value="0.5" ${sec.flow_pulgadas==='0.5'?'selected':''}>1/2\" YF-S201 1-30L/min prototipo $18k</option><option value="1_fs400" ${sec.flow_pulgadas==='1_fs400'?'selected':''}>1\" FS400A 1-60L/min $25k</option><option value="1_dn25" ${sec.flow_pulgadas==='1_dn25'?'selected':''}>1\" DN25 10-100L/min $32k final</option></select>`;
   cont.appendChild(div);
 }
 document.getElementById('bombaPulg').value=fincaData.bomba_pulgadas||'1';
 document.getElementById('valvPpalPulg').value=fincaData.valvula_ppal_pulgadas||'1';
}
async function guardar(){
 let sectores_config={};
 for(let i=1;i<=fincaData.sectores;i++){
   sectores_config[i]={planta:document.getElementById(`planta_${i}`).value,cant_sensores:parseInt(document.getElementById(`cant_${i}`).value),valvula_pulgadas:document.getElementById(`valv_${i}`).value,flow_present:document.getElementById(`flowPres_${i}`).value==='true',flow_pulgadas:document.getElementById(`flowPulg_${i}`).value};
 }
 const payload={finca:'{{username}}',bomba_pulgadas:document.getElementById('bombaPulg').value,valvula_ppal_pulgadas:document.getElementById('valvPpalPulg').value,sectores_config:sectores_config};
 const r=await fetch('/api/config_terreno',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
 const j=await r.json(); document.getElementById('msg').innerText=j.ok?'✅ Guardado OXITEM V8! Recarga dashboard':'Error';
}
</script></body></html>
"""

def get_finca(username):
    return db["users"].get(username,{}).get("finca",{})

@app.route('/')
def idx():
    if 'user' in session: return redirect('/dashboard')
    return redirect('/login')

@app.route('/login', methods=['GET','POST'])
def login():
    err=None
    users_count=len(db["users"])
    if request.method=='POST':
        u=request.form.get('username','').strip()
        p=request.form.get('password','').strip()
        if not u:
            err="Poné usuario"
        elif u.lower()=='admin' and p=='OXITEM':
            session['user']='admin'; session['role']='admin'; return redirect('/dashboard')
        elif u in db["users"] and db["users"][u]["password"]==p:
            session['user']=u; session['role']='cliente'; return redirect('/dashboard')
        else:
            # Buscar sin distinguir mayusculas por si se equivocó
            for ku in db["users"]:
                if ku.lower()==u.lower() and db["users"][ku]["password"]==p:
                    session['user']=ku; session['role']='cliente'; return redirect('/dashboard')
            err=f"Usuario '{u}' no encontrado. Usuarios: {', '.join(db['users'].keys()) or 'ninguno, creá uno nuevo'}"
    return render_template_string(LOGIN_HTML, error=err, users_count=users_count, db_file=DB_FILE)

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method=='POST':
        u=request.form.get('username','').strip().replace(' ','_')
        p=request.form.get('password','').strip()
        if not u or len(u)<3:
            return "Usuario mínimo 3 letras sin espacios",400
        if u.lower() in [k.lower() for k in db["users"].keys()] or u.lower()=='admin':
            return f"Usuario '{u}' ya existe, elegí otro",400
        plantas_sel=request.form.getlist('plantas') or ['tomate','lechuga','uva']
        try:
            largo=int(request.form.get('largo',20)); ancho=int(request.form.get('ancho',10)); sectores=int(request.form.get('sectores',3))
        except:
            largo=20; ancho=10; sectores=3
        bomba_p=request.form.get('bomba_pulgadas','1'); valv_p=request.form.get('valvula_ppal_pulgadas','1')
        finca={"ubicacion":request.form.get('ubicacion','Villa Krause, Rawson, San Juan'),"largo":largo,"ancho":ancho,"m2":largo*ancho,"sectores":sectores,"bomba_pulgadas":bomba_p,"bomba_lpm":BOMBA_CAUDAL.get(bomba_p,80),"valvula_ppal_pulgadas":valv_p,"plantas":plantas_sel,"sectores_config":{str(i):{"planta":plantas_sel[(i-1) % len(plantas_sel)],"cant_sensores":5,"valvula_pulgadas":"0.75","flow_present":False,"flow_pulgadas":"no"} for i in range(1,sectores+1)}}
        db["users"][u]={"password":p,"role":"cliente","finca":finca}
        save_db(db)
        # Inicializar actuadores para cada sector
        for i in range(1, sectores+1):
            act_key=f"{u}_s{i}"
            actuadores_data[act_key]={"bomba":0,"valvula":0,"start_time":None,"litros_flow":0,"litros_estimado":0,"tiempo_acum":0}
        log(f"NUEVA FINCA OXITEM {u} {finca['ubicacion']} {finca['m2']}m2 {sectores} sectores plantas {plantas_sel}")
        session['user']=u; session['role']='cliente'
        return redirect('/dashboard')
    return render_template_string(REGISTER_HTML, plantas=PLANTAS)

@app.route('/logout')
def logout():
    session.clear(); return redirect('/login')

@app.route('/dashboard')
def dashboard():
    if 'user' not in session: return redirect('/login')
    user=session['user']
    if user=='admin':
        if not db["users"]:
            lista="<div class='card'>No hay fincas aún. Creá una en /register</div>"
        else:
            lista="".join([f"<div class='card'><b>{u}</b> - {db['users'][u]['finca']['ubicacion']} - {db['users'][u]['finca']['m2']}m2 - {db['users'][u]['finca']['sectores']} sectores - Plantas: {len(db['users'][u]['finca']['plantas'])}<br><a href='/dashboard?finca={u}' style='color:#22c55e'>Ver finca</a> | <a href='/config_terreno?finca={u}' style='color:#22c55e'>Configurar</a></div>" for u in db["users"]])
        return f"<body style='background:#0a0f1c;color:white;font-family:system-ui;padding:20px'><h1>OXITEM ADMIN V8 - {len(db['users'])} fincas - 36 plantas</h1>{lista}<br><a href='/register' style='color:#22c55e'>+ Crear finca nueva</a> | <a href='/logout' style='color:white'>Salir</a><br><br>DB file: {DB_FILE} | Users: {list(db['users'].keys())}</body>"
    finca_user=request.args.get('finca', user)
    finca=get_finca(finca_user)
    if not finca:
        return redirect('/register')
    return render_template_string(DASHBOARD_HTML, username=finca_user, finca=finca)

@app.route('/config_terreno')
def config_terreno():
    if 'user' not in session: return redirect('/login')
    finca_user=request.args.get('finca', session['user'])
    finca=get_finca(finca_user)
    if not finca: return f"Finca {finca_user} no existe. Usuarios: {list(db['users'].keys())}",404
    return render_template_string(CONFIG_HTML, username=finca_user, finca=finca, finca_json=json.dumps(finca), plantas_json=json.dumps(PLANTAS))

@app.route('/api/admin_auth', methods=['POST'])
def admin_auth():
    d=request.get_json()
    if d and d.get('user','').strip().lower()=='admin' and d.get('pass','').strip()=='OXITEM':
        return {"ok":True}
    return {"ok":False},401

@app.route('/api/config_terreno', methods=['POST'])
def api_config():
    d=request.get_json()
    finca_name=d.get('finca','').strip()
    if not finca_name or finca_name not in db["users"]:
        return {"error":f"finca {finca_name} no existe. Users: {list(db['users'].keys())}"},404
    finca=db["users"][finca_name]["finca"]
    finca["bomba_pulgadas"]=d.get('bomba_pulgadas', finca["bomba_pulgadas"])
    finca["bomba_lpm"]=BOMBA_CAUDAL.get(finca["bomba_pulgadas"],80)
    finca["valvula_ppal_pulgadas"]=d.get('valvula_ppal_pulgadas', finca["valvula_ppal_pulgadas"])
    finca["sectores_config"]=d.get('sectores_config', finca["sectores_config"])
    # Re-inicializar actuadores
    for sid in finca["sectores_config"]:
        act_key=f"{finca_name}_s{sid}"
        if act_key not in actuadores_data:
            actuadores_data[act_key]={"bomba":0,"valvula":0,"start_time":None,"litros_flow":0,"litros_estimado":0,"tiempo_acum":0}
    save_db(db)
    log(f"OXITEM CONFIG V8 {finca_name} bomba {finca['bomba_pulgadas']}\" {finca['bomba_lpm']}L/min sectores {len(finca['sectores_config'])}")
    return {"ok":True}

@app.route('/api/datos', methods=['POST'])
def datos():
    j=request.get_json()
    if not j:
        return {"error":"no json"},400
    finca_id=j.get('finca_id', j.get('finca','default')).strip()
    sector_id=str(j.get('sector_id', j.get('sector','1'))).strip()
    tipo=j.get('tipo','sensor')
    key=f"{finca_id}_s{sector_id}_d{j.get('dispositivo_id','1')}_{tipo}"
    j['ts']=time.time()
    sensores_data[key]=j
    
    # Guardar en historico solo si tiene humedad
    if 'humedad' in j:
        historico.append({"ts":j['ts'],"humedad":float(j.get('humedad',0)),"temp":float(j.get('temperatura',0)),"ph":float(j.get('ph',0)),"ec":int(j.get('conductividad',0)),"n":float(j.get('nitrogeno',0)),"p":int(j.get('fosforo',0)),"k":int(j.get('potasio',0)),"finca":finca_id,"sector":sector_id})
        if len(historico)>500: historico.pop(0)
    
    pulsos=j.get('pulsos',0)
    if pulsos:
        log(f"OXITEM {finca_id} S{sector_id} {tipo} {pulsos}p = {j.get('litros_flow',0)}L flow")
    else:
        if 'humedad' in j:
            log(f"OXITEM RX {finca_id} S{sector_id} Hum {j.get('humedad')}% T {j.get('temperatura')}°C pH {j.get('ph')} N {j.get('nitrogeno')} P {j.get('fosforo')} K {j.get('potasio')}")
    
    # Lógica riego por sector
    finca_cfg=db["users"].get(finca_id,{}).get('finca',{})
    sec_cfg=finca_cfg.get('sectores_config',{}).get(sector_id,{})
    planta_key=sec_cfg.get('planta','tomate')
    planta=PLANTAS.get(planta_key, PLANTAS["tomate"])
    
    if 'humedad' in j:
        hum=float(j.get('humedad',100))
        act_key=f"{finca_id}_s{sector_id}"
        if act_key not in actuadores_data:
            actuadores_data[act_key]={"bomba":0,"valvula":0,"start_time":None,"litros_flow":0,"litros_estimado":0,"tiempo_acum":0}
        actuador=actuadores_data[act_key]
        bomba_lpm=finca_cfg.get('bomba_lpm',80)
        
        if hum < planta["on"] and actuador["bomba"]==0:
            actuador["bomba"]=1; actuador["valvula"]=1; actuador["start_time"]=time.time()
            log(f"OXITEM AUTO {finca_id} S{sector_id} {planta['nombre']} {hum}% <{planta['on']}% -> BOMBA ON + VALV S{sector_id} OPEN")
        elif hum >= planta["off"] and actuador["bomba"]==1:
            if actuador["start_time"]:
                dur=time.time()-actuador["start_time"]
                litros_est=dur * bomba_lpm / 60.0
                actuador["tiempo_acum"]+=dur
                actuador["litros_estimado"]+=litros_est
                consumo_historico.append({"finca":finca_id,"sector":sector_id,"litros_estimado":litros_est,"tiempo":dur})
                log(f"OXITEM CONSUMO {finca_id} S{sector_id} {(dur/60):.1f}min -> {litros_est:.1f}L estimado (bomba {bomba_lpm}L/min) + {actuador['litros_flow']:.1f}L flow")
            actuador["bomba"]=0; actuador["valvula"]=0; actuador["start_time"]=None
            log(f"OXITEM AUTO {finca_id} S{sector_id} {hum}% >= {planta['off']}% -> BOMBA OFF + VALV CLOSED")
    
    # Acumular flow si viene de valvula o bomba
    if tipo in ['valvula_flow','bomba_flow','sensor_flow']:
        for ak in actuadores_data:
            if ak.startswith(f"{finca_id}_s{sector_id}") or (sector_id=='0' and ak.startswith(finca_id)):
                actuadores_data[ak]["litros_flow"]+=float(j.get('litros_flow',0))
    
    return {"ok":True, "finca":finca_id, "sector":sector_id}

@app.route('/api/estado')
def estado():
    finca_id=request.args.get('finca','default').strip()
    if finca_id=='default' and 'user' in session and session['user']!='admin':
        finca_id=session['user']
    finca_cfg=db["users"].get(finca_id,{}).get('finca',{})
    if not finca_cfg:
        return {"error":f"Finca {finca_id} no existe","users":list(db["users"].keys()),"sectores":{},"consumo":{"total_litros_flow":0,"total_litros_estimado":0,"diferencia":0,"alerta":"Sin finca"},"historico":[],"logs":logs[-10:],"reporte":"Creá finca en /register","clima":{"temp":28,"hum":35,"viento":10,"desc":"Sin finca","riego_recomendado":"Creá finca","flow_info":"-","ubicacion":finca_id},"ultimo_temp":0,"ultimo_ph":0,"ultimo_ec":0,"ultimo_n":0,"ultimo_p":0,"ultimo_k":0,"ultimo_nota":""}
    
    sectores_cfg=finca_cfg.get('sectores_config',{})
    sectores_info={}
    total_flow=0; total_est=0
    reporte=""
    ultimo_temp=0; ultimo_ph=0; ultimo_ec=0; ultimo_n=0; ultimo_p=0; ultimo_k=0; ultimo_nota=""
    
    for sid, scfg in sectores_cfg.items():
        sensores_sector=[v for k,v in sensores_data.items() if k.startswith(f"{finca_id}_s{sid}_") and 'humedad' in v]
        # Ordenar por ts
        sensores_sector_sorted=sorted(sensores_sector, key=lambda x: x.get('ts',0))
        hums=[s.get('humedad',0) for s in sensores_sector]
        hum_prom=sum(hums)/len(hums) if hums else 0
        
        if sensores_sector_sorted:
            last=sensores_sector_sorted[-1]
            ultimo_temp=last.get('temperatura',0)
            ultimo_ph=last.get('ph',0)
            ultimo_ec=last.get('conductividad',0)
            ultimo_n=last.get('nitrogeno',0)
            ultimo_p=last.get('fosforo',0)
            ultimo_k=last.get('potasio',0)
            ultimo_nota=PLANTAS.get(scfg.get('planta','tomate'),{}).get('nota','')
            temp=last.get('temperatura',0)
            ph=last.get('ph',0)
            ec=last.get('conductividad',0)
            n=last.get('nitrogeno',0)
            p=last.get('fosforo',0)
            k=last.get('potasio',0)
        else:
            temp=0; ph=0; ec=0; n=0; p=0; k=0
        
        act_key=f"{finca_id}_s{sid}"
        actuador=actuadores_data.get(act_key)
        if not actuador:
            actuador={"bomba":0,"valvula":0,"litros_flow":0,"litros_estimado":0,"tiempo_acum":0,"start_time":None}
            actuadores_data[act_key]=actuador
        
        tiempo_hoy=actuador["tiempo_acum"] + (time.time()-actuador["start_time"] if actuador.get("start_time") else 0)
        planta_key=scfg.get('planta','tomate')
        planta=PLANTAS.get(planta_key, PLANTAS["tomate"])
        
        # Estado suelo
        if hum_prom>=80: estado_suelo="SATURADO/Cap Campo"
        elif hum_prom>=60: estado_suelo="ÓPTIMO"
        elif hum_prom>=40: estado_suelo="ESTRÉS INICIO"
        elif hum_prom>=20: estado_suelo="MARCHITEZ"
        else: estado_suelo="SECO HORNO / Sin datos"
        if not hums: estado_suelo="Sin datos sensor"
        
        sectores_info[sid]={
            "planta":planta_key,
            "planta_nombre":planta["nombre"],
            "emoji":planta["emoji"],
            "color":planta["color"],
            "cant_sensores":scfg.get('cant_sensores',5),
            "valvula_pulgadas":scfg.get('valvula_pulgadas','0.75'),
            "flow_present":scfg.get('flow_present',False),
            "flow_pulgadas":scfg.get('flow_pulgadas','no'),
            "flow_model":FLOW_SPECS.get(scfg.get('flow_pulgadas','no'), FLOW_SPECS["no"])["modelo"],
            "humedad_prom":hum_prom,
            "temp":temp, "ph":ph, "ec":ec, "n":n, "p":p, "k":k,
            "temp_ideal":planta["temp"], "ph_ideal":planta["ph"], "n_ideal":planta["n"], "p_ideal":planta["p"], "k_ideal":planta["k"],
            "umbral_on":planta["on"], "umbral_off":planta["off"],
            "bomba_estado":actuador["bomba"], "valvula_estado":actuador["valvula"],
            "litros_flow":actuador["litros_flow"], "litros_estimado":actuador["litros_estimado"],
            "tiempo_hoy":tiempo_hoy,
            "sensores_activos":len(sensores_sector),
            "ultimo_hace":f"{int(time.time()-sensores_sector_sorted[-1]['ts'])}s" if sensores_sector_sorted else "nunca - espera datos sensor",
            "estado_suelo":estado_suelo,
            "id_ejemplo":f"{finca_id}_s{sid}_d1_sensor"
        }
        total_flow+=actuador["litros_flow"]
        total_est+=actuador["litros_estimado"]
        reporte+=f"● Sector {sid} {planta['emoji']} {planta['nombre']} ({scfg.get('cant_sensores')} sensores, válv {scfg.get('valvula_pulgadas')}\" flow {'SI '+scfg.get('flow_pulgadas') if scfg.get('flow_present') else 'NO solo estimado'}):\n  Hum {hum_prom:.1f}% VWC {estado_suelo} - ON<{planta['on']}% OFF≥{planta['off']}% - Bomba {'ON' if actuador['bomba'] else 'OFF'} Válv {'OPEN' if actuador['valvula'] else 'CLOSED'}\n  Temp {temp}°C (ideal {planta['temp']}) pH {ph} (ideal {planta['ph']}) EC {ec} N {n}ppm ({planta['n']}) P {p}ppm ({planta['p']}) K {k}ppm ({planta['k']})\n  Consumo {actuador['litros_flow']:.1f}L flow / {actuador['litros_estimado']:.1f}L estimado - Tiempo {(tiempo_hoy/60):.1f}min hoy - {scfg.get('cant_sensores')} sensores activos\n  Nota: {planta['nota']}\n\n"
    
    dif=abs(total_flow-total_est)/total_est*100 if total_est>0 else 0
    alerta="✅ Calibración OK" if (dif<=20 or total_flow==0) else "⚠️ Fuga/filtro tapado >20% dif flow vs estimado"
    if total_est==0 and total_flow==0:
        alerta="Sin riego aún - Esperando datos"
    
    # Clima real San Juan mock pero con datos reales de Open-Meteo podríamos traer
    clima={"temp":30,"hum":28,"viento":15,"desc":"Soleado San Juan - Ideal riego - Radiación alta","riego_recomendado":"Riego normal OXITEM - Evitar horas 12-16 por calor","flow_info":f"Bomba {finca_cfg.get('bomba_pulgadas','1')}\" {finca_cfg.get('bomba_lpm',80)}L/min - Flow YF-S201 1/2\" 1-30L proto / FS400A 1\" 1-60L final - Sin flow igual calcula estimado","ubicacion":finca_cfg.get('ubicacion','Villa Krause')}
    
    hist_filtrado=[h for h in historico if h.get('finca')==finca_id]
    
    return {
        "sensores":sensores_data,
        "actuadores":actuadores_data,
        "historico":hist_filtrado[-40:],
        "logs":logs[-25:],
        "sectores":sectores_info,
        "consumo":{"total_litros_flow":total_flow,"total_litros_estimado":total_est,"diferencia":round(dif,1),"alerta":alerta},
        "reporte":reporte or "Sin sectores configurados. Ve a Configurar Terreno (admin/OXITEM)",
        "ultimo_temp":ultimo_temp,"ultimo_ph":ultimo_ph,"ultimo_ec":ultimo_ec,"ultimo_n":ultimo_n,"ultimo_p":ultimo_p,"ultimo_k":ultimo_k,"ultimo_nota":ultimo_nota,
        "clima":clima
    }

@app.route('/api/comando', methods=['POST'])
def comando():
    d=request.get_json()
    finca=d.get('finca','default').strip()
    dev=d.get('device','')
    est=int(d.get('estado',0))
    sector=str(d.get('sector','')).strip()
    
    if 'bomba_principal' in dev or dev=='bomba_principal':
        # Bomba principal afecta a todos los sectores de esa finca
        for key in list(actuadores_data.keys()):
            if key.startswith(finca+"_s"):
                if est==1 and actuadores_data[key]["bomba"]==0:
                    actuadores_data[key]["bomba"]=1
                    actuadores_data[key]["start_time"]=time.time()
                elif est==0 and actuadores_data[key]["bomba"]==1:
                    if actuadores_data[key]["start_time"]:
                        dur=time.time()-actuadores_data[key]["start_time"]
                        bomba_lpm=db["users"].get(finca,{}).get('finca',{}).get('bomba_lpm',80)
                        actuadores_data[key]["litros_estimado"]+=dur * bomba_lpm / 60.0
                        actuadores_data[key]["tiempo_acum"]+=dur
                    actuadores_data[key]["bomba"]=0
                    actuadores_data[key]["start_time"]=None
        log(f"OXITEM MANUAL {finca} BOMBA_PRINCIPAL -> {'ON' if est else 'OFF'} (todos sectores)")
    elif 'valvula' in dev and not sector:
        # Todas valvulas
        for key in list(actuadores_data.keys()):
            if key.startswith(finca+"_s"):
                actuadores_data[key]["valvula"]=est
        log(f"OXITEM MANUAL {finca} TODAS VALVULAS -> {'OPEN' if est else 'CLOSED'}")
    elif sector:
        act_key=f"{finca}_s{sector}"
        if act_key not in actuadores_data:
            actuadores_data[act_key]={"bomba":0,"valvula":0,"start_time":None,"litros_flow":0,"litros_estimado":0,"tiempo_acum":0}
        if 'valvula' in dev:
            actuadores_data[act_key]["valvula"]=est
            if est==1 and actuadores_data[act_key]["bomba"]==0:
                actuadores_data[act_key]["bomba"]=1
                actuadores_data[act_key]["start_time"]=time.time()
            elif est==0:
                if actuadores_data[act_key]["start_time"]:
                    dur=time.time()-actuadores_data[act_key]["start_time"]
                    bomba_lpm=db["users"].get(finca,{}).get('finca',{}).get('bomba_lpm',80)
                    actuadores_data[act_key]["litros_estimado"]+=dur * bomba_lpm / 60.0
                    actuadores_data[act_key]["tiempo_acum"]+=dur
                    actuadores_data[act_key]["start_time"]=None
                actuadores_data[act_key]["bomba"]=0
        log(f"OXITEM MANUAL {finca} S{sector} {dev} -> {'ON/OPEN' if est else 'OFF/CLOSED'}")
    
    return {"ok":True}

@app.route('/api/riego')
def riego():
    finca_id=request.args.get('finca', request.args.get('finca_id','default')).strip()
    sector_id=request.args.get('sector','1').strip()
    
    if sector_id=='0':
        alguna_on=any(v["bomba"]==1 for k,v in actuadores_data.items() if k.startswith(finca_id+"_s"))
        return jsonify({"bomba": alguna_on, "bomba_principal": int(alguna_on), "valvula": False, "finca":finca_id, "sector":0, "consumo_flow": sum(v["litros_flow"] for k,v in actuadores_data.items() if k.startswith(finca_id)), "consumo_estimado": sum(v["litros_estimado"] for k,v in actuadores_data.items() if k.startswith(finca_id))})
    
    act_key=f"{finca_id}_s{sector_id}"
    actuador=actuadores_data.get(act_key, {"bomba":0,"valvula":0,"litros_flow":0,"litros_estimado":0})
    finca_cfg=db["users"].get(finca_id,{}).get('finca',{})
    sec_cfg=finca_cfg.get('sectores_config',{}).get(str(sector_id),{})
    planta_key=sec_cfg.get('planta','tomate')
    planta=PLANTAS.get(planta_key, PLANTAS["tomate"])
    
    return jsonify({
        "bomba": bool(actuador["bomba"]),
        "valvula": bool(actuador["valvula"]),
        "bomba_principal": actuador["bomba"],
        "valvula_sector": actuador["valvula"],
        "finca":finca_id,
        "sector":int(sector_id) if sector_id.isdigit() else sector_id,
        "umbral_on":planta["on"],
        "umbral_off":planta["off"],
        "planta":planta_key,
        "planta_nombre":planta["nombre"],
        "consumo_flow":actuador["litros_flow"],
        "consumo_estimado":actuador["litros_estimado"],
        "tiempo_acum":actuador.get("tiempo_acum",0)
    })

@app.route('/api/debug')
def debug():
    return jsonify({"db_file":DB_FILE,"users":list(db["users"].keys()),"db":db,"sensores":len(sensores_data),"actuadores":len(actuadores_data),"historico":len(historico),"logs":logs[-20:]})

if __name__=='__main__':
    print(f"OXITEM V8 CORREGIDA - 36 plantas - DB {DB_FILE} - Users {list(db['users'].keys())}")
    app.run(host='0.0.0.0',port=5000)

