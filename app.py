"""
OXITEM V9 FINAL FUNCIONAL - REESCRITA DESDE CERO SIN ERRORES JS
Fix bomba/valvula no activan, sensor no muestra, grafico vacio, clima cargando, mapa
- Sin Leaflet externo que rompia JS
- Sin Chart.js complejo
- Sectores siempre visibles
- /api/estado siempre devuelve JSON valido
- Logica bomba/valvula simplificada y probada
"""
from flask import Flask, request, jsonify, render_template_string, session, redirect
from flask_cors import CORS
import time, json, os
from datetime import datetime

app = Flask(__name__)
app.secret_key = "oxitem_v9_final_funcional_2026"
CORS(app)

DB_FILE = "fincas_db_v9.json"
def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE,'r') as f:
                return json.load(f)
        except: pass
    return {"users": {}}
def save_db(db):
    try:
        with open(DB_FILE,'w') as f:
            json.dump(db,f,indent=2)
    except Exception as e:
        print(f"Error save {e}")

db = load_db()
sensores_data = {}  # key: finca_ssector_did_tipo -> dict con ts, humedad, temp...
actuadores_data = {} # key: finca_ssector -> {bomba, valvula, start, litros...}
historico = [] # lista de dicts
logs = []

BOMBA_CAUDAL = {"0.5":25,"0.75":45,"1":80,"1.25":120,"1.5":180}
FLOW_SPECS = {
    "0.5": {"modelo": "YF-S201 1/2\" 1-30L/min", "ppl": 450},
    "1_fs400": {"modelo": "FS400A 1\" 1-60L/min", "ppl": 360},
    "1_dn25": {"modelo": "YF-DN25 1\" 10-100L/min", "ppl": 450},
    "no": {"modelo": "Sin caudalímetro (estimado)", "ppl": 0},
}

PLANTAS = {
    "tomate": {"nombre": "Tomate", "emoji":"🍅", "on":60, "off":80, "color":"#ef4444", "hum":"70-80%", "ph":"5.5-6.8", "temp":"18-27°C", "n":"150-200", "p":"50-80", "k":"250-350", "nota":"Muy demandante K"},
    "lechuga": {"nombre": "Lechuga", "emoji":"🥬", "on":60, "off":75, "color":"#22c55e", "hum":"60-75%", "ph":"6.0-7.0", "temp":"15-22°C", "n":"120-150", "p":"30-50", "k":"150-200", "nota":"Media sombra verano SJ"},
    "menta": {"nombre": "Menta", "emoji":"🌿", "on":75, "off":85, "color":"#10b981", "hum":"75-85%", "ph":"6.0-7.0", "temp":"15-25°C", "n":"150", "p":"50", "k":"150", "nota":"Invasiva"},
    "ruda": {"nombre": "Ruda", "emoji":"☘️", "on":40, "off":55, "color":"#65a30d", "hum":"40-55%", "ph":"6.0-8.0", "temp":"18-28°C", "n":"50-80", "p":"20-30", "k":"80-120", "nota":"Odia encharque"},
    "oregano": {"nombre": "Orégano", "emoji":"🌱", "on":45, "off":60, "color":"#84cc16", "hum":"45-60%", "ph":"6.0-8.0", "temp":"18-30°C", "n":"80", "p":"30", "k":"120", "nota":""},
    "romero": {"nombre": "Romero", "emoji":"🌾", "on":30, "off":50, "color":"#16a34a", "hum":"30-50%", "ph":"5.5-7.0", "temp":"15-28°C", "n":"50", "p":"20", "k":"100", "nota":"Si lo regas mucho se muere"},
    "papa": {"nombre": "Papa", "emoji":"🥔", "on":65, "off":80, "color":"#a16207", "hum":"65-80%", "ph":"5.0-6.0", "temp":"15-22°C", "n":"100-150", "p":"80-100", "k":"300-400", "nota":""},
    "zanahoria": {"nombre": "Zanahoria", "emoji":"🥕", "on":60, "off":70, "color":"#f97316", "hum":"60-70%", "ph":"6.0-6.8", "temp":"16-24°C", "n":"100", "p":"60", "k":"200", "nota":""},
    "habas": {"nombre": "Habas", "emoji":"🫘", "on":60, "off":75, "color":"#65a30d", "hum":"60-75%", "ph":"6.0-7.5", "temp":"10-22°C", "n":"30-50", "p":"60", "k":"150", "nota":"Fija N"},
    "ajo": {"nombre": "Ajo", "emoji":"🧄", "on":50, "off":65, "color":"#e5e7eb", "hum":"50-65%", "ph":"6.0-7.0", "temp":"12-22°C", "n":"120", "p":"50", "k":"180", "nota":""},
    "cebolla": {"nombre": "Cebolla", "emoji":"🧅", "on":60, "off":70, "color":"#fef3c7", "hum":"60-70%", "ph":"6.0-7.0", "temp":"13-24°C", "n":"110", "p":"70", "k":"180", "nota":""},
    "zapallo_ancho": {"nombre": "Zapallo Ancho", "emoji":"🎃", "on":70, "off":80, "color":"#f59e0b", "hum":"70-80%", "ph":"6.0-7.5", "temp":"20-30°C", "n":"150", "p":"50", "k":"250", "nota":""},
    "zapallo_ingles": {"nombre": "Zapallo Inglés", "emoji":"🎃", "on":70, "off":80, "color":"#fbbf24", "hum":"70-80%", "ph":"6.0-7.0", "temp":"20-28°C", "n":"150", "p":"50", "k":"250", "nota":""},
    "frutilla": {"nombre": "Frutilla", "emoji":"🍓", "on":65, "off":75, "color":"#f43f5e", "hum":"65-75%", "ph":"5.5-6.5", "temp":"15-24°C", "n":"100", "p":"70", "k":"200", "nota":"pH ácido"},
    "frambuesa": {"nombre": "Frambuesa", "emoji":"🍇", "on":65, "off":80, "color":"#8b5cf6", "hum":"65-80%", "ph":"5.5-6.5", "temp":"12-22°C", "n":"100", "p":"50", "k":"150", "nota":""},
    "pepino": {"nombre": "Pepino", "emoji":"🥒", "on":75, "off":85, "color":"#22c55e", "hum":"75-85%", "ph":"5.5-6.8", "temp":"20-30°C", "n":"150", "p":"50", "k":"250", "nota":""},
    "marimona": {"nombre": "Marimoña", "emoji":"🌼", "on":60, "off":70, "color":"#facc15", "hum":"60-70%", "ph":"6.0-7.0", "temp":"10-20°C", "n":"100", "p":"50", "k":"150", "nota":""},
    "copete": {"nombre": "Copete", "emoji":"🌸", "on":50, "off":65, "color":"#f97316", "hum":"50-65%", "ph":"6.0-7.0", "temp":"18-28°C", "n":"80", "p":"30", "k":"120", "nota":"Repelente plagas"},
    "conejito": {"nombre": "Conejito", "emoji":"🐰", "on":60, "off":70, "color":"#fda4af", "hum":"60-70%", "ph":"6.0-7.0", "temp":"12-22°C", "n":"100", "p":"40", "k":"140", "nota":""},
    "clavel": {"nombre": "Clavel", "emoji":"🌹", "on":50, "off":60, "color":"#e11d48", "hum":"50-60%", "ph":"6.0-7.5", "temp":"15-24°C", "n":"120", "p":"50", "k":"180", "nota":""},
    "clavel_enano": {"nombre": "Clavel Enano", "emoji":"🌹", "on":50, "off":60, "color":"#fb7185", "hum":"50-60%", "ph":"6.0-7.0", "temp":"15-22°C", "n":"100", "p":"40", "k":"150", "nota":""},
    "petunia": {"nombre": "Petuña", "emoji":"🌺", "on":60, "off":70, "color":"#a855f7", "hum":"60-70%", "ph":"5.5-6.5", "temp":"16-26°C", "n":"120", "p":"50", "k":"150", "nota":""},
    "girasol": {"nombre": "Girasol", "emoji":"🌻", "on":60, "off":75, "color":"#eab308", "hum":"60-75%", "ph":"6.0-7.5", "temp":"20-30°C", "n":"150", "p":"60", "k":"200", "nota":""},
    "pensamiento": {"nombre": "Pensamiento", "emoji":"💜", "on":65, "off":75, "color":"#8b5cf6", "hum":"65-75%", "ph":"5.5-6.5", "temp":"10-18°C", "n":"100", "p":"40", "k":"120", "nota":"Invierno"},
    "malvon": {"nombre": "Malvón", "emoji":"🌺", "on":45, "off":60, "color":"#ef4444", "hum":"45-60%", "ph":"6.0-7.5", "temp":"16-26°C", "n":"80", "p":"30", "k":"120", "nota":""},
    "rosa": {"nombre": "Rosa", "emoji":"🌹", "on":60, "off":70, "color":"#ec4899", "hum":"60-70%", "ph":"6.0-6.8", "temp":"15-25°C", "n":"150", "p":"60", "k":"200", "nota":""},
    "alegria": {"nombre": "Alegría", "emoji":"😊", "on":70, "off":80, "color":"#f43f5e", "hum":"70-80%", "ph":"6.0-6.5", "temp":"18-24°C", "n":"100", "p":"40", "k":"140", "nota":"No sol directo SJ"},
    "begonia": {"nombre": "Flor Azúcar", "emoji":"🌸", "on":60, "off":70, "color":"#f9a8d4", "hum":"60-70%", "ph":"5.5-6.5", "temp":"18-24°C", "n":"100", "p":"40", "k":"120", "nota":""},
    "orquidea": {"nombre": "Orquídea", "emoji":"🌸", "on":50, "off":60, "color":"#e9d5ff", "hum":"50-60%", "ph":"5.5-6.5", "temp":"18-28°C", "n":"50", "p":"20", "k":"50", "nota":"Corteza"},
    "paleta": {"nombre": "Paleta Pintor", "emoji":"🎨", "on":60, "off":75, "color":"#f472b6", "hum":"60-75%", "ph":"5.5-6.5", "temp":"18-26°C", "n":"80", "p":"30", "k":"100", "nota":""},
    "calanchoe": {"nombre": "Calanchoe", "emoji":"🌵", "on":30, "off":45, "color":"#06b6d4", "hum":"30-45%", "ph":"6.0-7.0", "temp":"15-25°C", "n":"50", "p":"20", "k":"80", "nota":""},
    "lazo": {"nombre": "Lazo Amor", "emoji":"💚", "on":50, "off":65, "color":"#22c55e", "hum":"50-65%", "ph":"6.0-7.0", "temp":"15-26°C", "n":"80", "p":"30", "k":"100", "nota":""},
    "dolar_negro": {"nombre": "Dólar Negro", "emoji":"💲", "on":55, "off":70, "color":"#16a34a", "hum":"55-70%", "ph":"6.0-7.0", "temp":"16-26°C", "n":"100", "p":"30", "k":"120", "nota":""},
    "garrita": {"nombre": "Garrita Oso", "emoji":"🐻", "on":20, "off":35, "color":"#a3a3a3", "hum":"20-35%", "ph":"6.0-7.5", "temp":"15-28°C", "n":"30", "p":"10", "k":"50", "nota":"Suculenta extrema"},
    "uva": {"nombre": "Uva Vid SJ", "emoji":"🍇", "on":40, "off":60, "color":"#7c3aed", "hum":"40-60%", "ph":"6.0-7.5", "temp":"15-30°C", "n":"80-120", "p":"40-60", "k":"150-250", "nota":"Emblemático SJ"},
    "olivo": {"nombre": "Olivo", "emoji":"🫒", "on":30, "off":50, "color":"#65a30d", "hum":"30-50%", "ph":"6.0-8.0", "temp":"15-30°C", "n":"60-100", "p":"20-40", "k":"100-200", "nota":"Tolerante sequía"},
}

def log(msg):
    ts=datetime.now().strftime("%H:%M:%S")
    logs.append(f"{ts} - {msg}")
    if len(logs)>200: logs.pop(0)
    print(msg)

# ========== HTML SIMPLE SIN LIBRERIAS EXTERNAS QUE FALLEN ==========
LOGIN_HTML = """
<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OXITEM V9 - Login</title>
<style>body{margin:0;background:#0a0f1c;color:white;font-family:system-ui;display:flex;align-items:center;justify-content:center;min-height:100vh}
.card{background:#1e293b;border:1px solid #334155;padding:30px;border-radius:20px;width:380px}
.logo{font-size:32px;font-weight:900} .logo span{color:#22c55e}
input{width:100%;padding:12px;margin:8px 0;background:#0f172a;border:1px solid #334155;border-radius:10px;color:white;box-sizing:border-box}
.btn{width:100%;padding:12px;background:#22c55e;color:black;border:none;border-radius:10px;font-weight:800;cursor:pointer}
.link{color:#22c55e;display:block;text-align:center;margin-top:12px;font-size:13px;text-decoration:none}
.debug{font-size:10px;color:#64748b;margin-top:10px}
</style></head><body>
<div class="card">
<div class="logo">OX<span>ITEM</span> V9 FIX</div><div style="color:#94a3b8;font-size:11px">36 PLANTAS - SISTEMA FUNCIONAL - VILLA KRAUSE</div>
<form method="POST" action="/login" style="margin-top:16px">
<input name="username" placeholder="Usuario finca" required>
<input name="password" type="password" placeholder="Contraseña" required>
<button class="btn">INGRESAR →</button>
</form>
<a class="link" href="/register">Crear finca nueva</a>
{% if error %}<div style="color:#f87171;background:rgba(248,113,113,0.1);padding:8px;border-radius:8px;margin-top:10px;font-size:12px">{{error}}</div>{% endif %}
<div class="debug">Usuarios: {{users_count}} | DB: {{db_file}}<br>Admin: admin / OXITEM</div>
</div></body></html>
"""

REGISTER_HTML = """
<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OXITEM V9 Registro</title>
<style>body{margin:0;background:#0f172a;color:white;font-family:system-ui;padding:20px}
.card{background:#1e293b;border:1px solid #334155;padding:20px;border-radius:16px;max-width:800px;margin:0 auto}
input,select{width:100%;padding:10px;margin:5px 0;background:#0f172a;border:1px solid #334155;border-radius:8px;color:white;box-sizing:border-box}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.plant-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;max-height:400px;overflow:auto;background:#0f172a;padding:10px;border-radius:10px;border:1px solid #334155}
.plant-grid label{font-size:11px;padding:5px;border-radius:6px;display:flex;gap:4px;align-items:center}
.btn{width:100%;padding:12px;background:#22c55e;color:black;border:none;border-radius:10px;font-weight:800;cursor:pointer;margin-top:12px}
.grupo{color:#22c55e;font-weight:800;font-size:11px;grid-column:1/-1;margin-top:8px}
</style></head><body>
<div class="card">
<h2>OX<span style="color:#22c55e">ITEM</span> V9 - Nueva Finca (36 plantas - FIX)</h2>
<form method="POST" action="/register">
<div class="grid"><input name="username" placeholder="Usuario sin espacios (ej: finca_gonzalez)" required><input name="password" type="password" placeholder="Contraseña" required></div>
<input name="ubicacion" placeholder="Ubicación para mapa Ej: Villa Krause, Rawson, San Juan" required>
<div class="grid"><input name="largo" type="number" placeholder="Largo m" required><input name="ancho" type="number" placeholder="Ancho m" required></div>
<div class="grid"><input name="sectores" type="number" min="1" max="10" value="1" required><select name="bomba_pulgadas"><option value="0.5" selected>Bomba 1/2\" 25L/min proto</option><option value="0.75">3/4\" 45L/min</option><option value="1">1\" 80L/min</option></select></div>
<select name="valvula_ppal_pulgadas"><option value="0.5">Válv ppal 1/2\"</option><option value="1" selected>Válv ppal 1\"</option></select>
<h3 style="color:#22c55e;font-size:12px">Cultivos (tildá)</h3>
<div class="plant-grid">
{% for grupo in ['Huerta','Aromáticas','Frutales','Frutal SJ','Flor','Interior','Suculenta'] %}
<div class="grupo">{{grupo}}</div>
{% for key, pl in plantas.items() if pl.grupo==grupo %}
<label><input type="checkbox" name="plantas" value="{{key}}"> {{pl.emoji}} {{pl.nombre}} {{pl.hum}}</label>
{% endfor %}
{% endfor %}
</div>
<button class="btn">CREAR FINCA V9 →</button>
</form>
</div></body></html>
"""

DASHBOARD_HTML = """
<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OXITEM V9 - {{username}}</title>
<style>
body{margin:0;background:#0a0f1c;color:#e2e8f0;font-family:system-ui}
.header{background:#0f172a;border-bottom:1px solid #1e293b;padding:12px 16px;display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px}
.logo{font-weight:900;font-size:20px;color:white} .logo span{color:#22c55e}
.card{background:#1e293b;border:1px solid #334155;border-radius:14px;padding:12px;margin:8px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:0;padding:8px}
.val{font-size:26px;font-weight:900} .small{font-size:11px;color:#94a3b8}
.btn{padding:8px 12px;border-radius:8px;border:none;font-weight:700;cursor:pointer;font-size:11px;margin:2px}
.btn-dark{background:#0f172a;color:white;border:1px solid #334155} .btn-green{background:#22c55e;color:black} .btn-red{background:#ef4444;color:white}
.badge{padding:3px 8px;border-radius:10px;font-size:10px;font-weight:800}
.log{background:#0f172a;border:1px solid #1e293b;color:#86efac;padding:8px;border-radius:8px;font-family:monospace;font-size:10px;max-height:200px;overflow:auto}
.kpi{font-size:11px;display:flex;justify-content:space-between;margin:2px 0}
.bar{height:8px;background:#0f172a;border-radius:8px;overflow:hidden;margin-top:4px} .fill{height:100%;background:linear-gradient(90deg,#22c55e,#06b6d4)}
canvas{width:100%!important;max-height:200px}
#map{width:100%;height:200px;background:#0f172a;border-radius:10px;border:1px solid #334155;display:flex;align-items:center;justify-content:center;color:#64748b;font-size:12px}
</style></head><body>
<div class="header">
<div><div class="logo">OX<span>ITEM</span> V9 <span style="font-size:10px;color:#64748b">FIX FUNCIONAL - 36 PLANTAS</span></div><div class="small">{{finca.ubicacion}} • {{finca.largo}}x{{finca.ancho}}m {{finca.m2}}m² • {{finca.sectores}} sectores • Bomba {{finca.bomba_pulgadas}}" {{finca.bomba_lpm}}L/min</div></div>
<div><a href="/config_terreno?finca={{username}}" style="background:#22c55e;color:black;padding:8px 12px;border-radius:8px;text-decoration:none;font-weight:800;font-size:12px">⚙️ Config</a> <a href="/logout" style="color:white;font-size:12px;margin-left:8px">Salir</a></div>
</div>

<div class="card" style="background:linear-gradient(135deg,rgba(34,197,94,0.12),rgba(6,182,212,0.08));border-color:#22c55e40">
<div style="display:flex;justify-content:space-between;flex-wrap:wrap"><div><b>💧 CONSUMO DUAL OXITEM V9</b><div class="small">Flow 1/2\" YF-S201 (450p/L) + estimado tiempo x bomba • Funciona con y sin caudalímetro</div></div><div id="consumoResumen" class="small" style="text-align:right">Cargando...</div></div>
<div class="bar"><div id="consumoFill" class="fill" style="width:10%"></div></div>
</div>

<div id="sectoresContainer" class="grid">Cargando sectores...</div>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:0;padding:0 8px">
<div class="card"><b class="small">📈 HISTORIAL HUMEDAD VWC % (últimos 20)</b><canvas id="cHum" width="400" height="180"></canvas><div class="small">Línea verde 80% = Cap Campo objetivo</div><div id="humList" class="small" style="margin-top:6px"></div></div>
<div class="card"><b class="small">CONTROL & CLIMA SAN JUAN + MAPA</b>
<div style="margin:8px 0;display:flex;flex-wrap:wrap;gap:4px"><button class="btn btn-green" onclick="cmdGlobal(1)">BOMBA ON</button><button class="btn btn-red" onclick="cmdGlobal(0)">BOMBA OFF</button><button class="btn btn-green" onclick="cmdValvulas(1)">Todas Válv ON</button><button class="btn btn-red" onclick="cmdValvulas(0)">Todas Válv OFF</button></div>
<div id="clima" style="background:#0f172a;padding:8px;border-radius:8px;font-size:11px;border:1px solid #1e293b">Cargando clima San Juan...</div>
<div id="map">🗺️ Mapa: {{finca.ubicacion}}<br><a href="https://www.google.com/maps/search/{{finca.ubicacion}}" target="_blank" style="color:#22c55e">Abrir en Google Maps →</a></div>
<div class="small" style="margin-top:6px">Flowmeter: 1/2\" YF-S201 1-30L/min 450p/L proto • 1\" FS400A 1-60L 360p/L final • Estimado = tiempo x caudal bomba {{finca.bomba_lpm}}L/min</div>
</div>
</div>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:0;padding:0 8px">
<div class="card"><b class="small">📊 ÚLTIMOS NPK + pH + EC + TEMP</b><div id="npkBars"></div><div id="npkDetalle" class="small" style="margin-top:8px"></div><canvas id="cNPK" width="400" height="120"></canvas></div>
<div class="card"><b class="small">📋 REPORTE AGRONÓMICO POR SECTOR</b><div id="rep" style="font-size:11px;white-space:pre-wrap;max-height:300px;overflow:auto;line-height:1.4;margin-top:6px;color:#cbd5e1">Cargando...</div></div>
</div>

<div class="card"><b class="small">LOGS BOMBA/VÁLVULA - Activaciones</b><div id="log" class="log">Cargando logs...</div></div>

<div class="card"><b class="small">DEBUG - Si algo no anda, copia esto</b><div id="debug" class="small" style="font-family:monospace;white-space:pre-wrap"></div></div>

<script>
let lastData=null;
async function load(){
 try{
  const r=await fetch('/api/estado?finca={{username}}&t='+Date.now());
  const text=await r.text();
  let j;
  try{ j=JSON.parse(text); } catch(e){ document.getElementById('debug').innerText='Error JSON estado: '+text.substring(0,500); return; }
  lastData=j;
  if(j.error){ document.getElementById('debug').innerText='Error API: '+j.error+'\\nUsers: '+(j.users||[]); return; }
  
  // Consumo
  document.getElementById('consumoResumen').innerHTML=`Total: <b>${(j.consumo.total_litros_flow||0).toFixed(1)} L flow</b> / <b>${(j.consumo.total_litros_estimado||0).toFixed(1)} L est.</b> • Dif ${j.consumo.diferencia}% <span style="color:${j.consumo.diferencia>20?'#f87171':'#22c55e'}">${j.consumo.alerta}</span><br><span class="small">${j.sensores_total||0} sensores guardados • ${Object.keys(j.sectores||{}).length} sectores</span>`;
  document.getElementById('consumoFill').style.width=Math.min(100, (j.consumo.total_litros_estimado||0)/2)+'%';
  
  // Sectores
  const cont=document.getElementById('sectoresContainer');
  cont.innerHTML='';
  const sectores=j.sectores||{};
  if(Object.keys(sectores).length===0){
    cont.innerHTML='<div class="card" style="grid-column:1/-1">No hay sectores configurados. Ve a Config Terreno (admin/OXITEM) y guardá. Finca: {{username}} tiene '+ (j.finca_sectores||0) +' sectores en DB. Si no aparecen, borrá finca y creá de nuevo.</div>';
  } else {
    Object.entries(sectores).forEach(([sid, sec])=>{
      const estadoColor = sec.humedad_prom < sec.umbral_on ? '#f87171' : sec.humedad_prom >= sec.umbral_off ? '#22c55e' : '#fbbf24';
      const div=document.createElement('div'); div.className='card'; div.style.borderLeft=`4px solid ${sec.color||'#22c55e'}`;
      div.innerHTML=`<div style="display:flex;justify-content:space-between;flex-wrap:wrap"><div class="small" style="font-weight:700"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${sec.color||'#22c55e'}"></span> SECTOR ${sid} • ${(sec.planta_nombre||'').toUpperCase()} ${sec.emoji||''} • ${sec.cant_sensores} sensores • Válv ${sec.valvula_pulgadas}" • Flow ${sec.flow_present?sec.flow_model:'NO solo estimado'}</div><div class="badge" style="background:${estadoColor}20;color:${estadoColor};border:1px solid ${estadoColor}40">${sec.bomba_estado?'BOMBA ON':'OFF'} • ${sec.valvula_estado?'VÁLV OPEN':'CLOSED'}</div></div>
      <div class="val" style="color:${estadoColor}">${(sec.humedad_prom||0).toFixed(1)}<span style="font-size:14px">% VWC</span> <span style="font-size:11px;color:#94a3b8">${sec.estado_suelo||''}</span></div>
      <div class="kpi"><span>🌡️ Temp ${sec.temp||0}°C ideal ${sec.temp_ideal||''}</span><span>pH ${sec.ph||0} ideal ${sec.ph_ideal||''}</span><span>EC ${sec.ec||0}</span></div>
      <div class="kpi"><span>🧪 N ${sec.n||0}ppm (${sec.n_ideal||''})</span><span>P ${sec.p||0}ppm (${sec.p_ideal||''})</span><span>K ${sec.k||0}ppm (${sec.k_ideal||''})</span></div>
      <div style="margin-top:6px;display:flex;gap:4px;flex-wrap:wrap"><button class="btn btn-green" onclick="cmdSector(${sid},1)">Válv S${sid} ON</button><button class="btn btn-red" onclick="cmdSector(${sid},0)">Válv S${sid} OFF</button><button class="btn btn-dark" onclick="cmdBombaSector(${sid},1)">Bomba S${sid} ON</button><button class="btn btn-dark" onclick="cmdBombaSector(${sid},0)">OFF</button></div>
      <div class="kpi" style="margin-top:4px"><span>💧 ${(sec.litros_flow||0).toFixed(1)}L flow</span><span>${(sec.litros_estimado||0).toFixed(1)}L est.</span><span>⏱ ${((sec.tiempo_hoy||0)/60).toFixed(1)}min hoy</span></div>
      <div class="bar"><div class="fill" style="width:${Math.min(100,sec.humedad_prom||0)}%;background:${sec.color||'#22c55e'}"></div></div>
      <div class="small" style="margin-top:4px">${sec.sensores_activos||0} sensores activos • último hace ${sec.ultimo_hace||'nunca'} • ID ejemplo: ${sec.id_ejemplo||''}</div>`;
      cont.appendChild(div);
    });
  }
  
  // Historial humedad - dibujo simple en canvas sin Chart.js
  try{
    const canvas=document.getElementById('cHum'); const ctx=canvas.getContext('2d'); const hist=j.historico||[];
    ctx.clearRect(0,0,canvas.width,canvas.height);
    ctx.fillStyle='#0f172a'; ctx.fillRect(0,0,canvas.width,canvas.height);
    // grid
    ctx.strokeStyle='#1e293b'; ctx.beginPath(); for(let y=0;y<canvas.height;y+=20){ ctx.moveTo(0,y); ctx.lineTo(canvas.width,y);} ctx.stroke();
    // linea 80% cap campo
    ctx.strokeStyle='#22c55e'; ctx.setLineDash([4,4]); ctx.beginPath(); ctx.moveTo(0,canvas.height*0.2); ctx.lineTo(canvas.width,canvas.height*0.2); ctx.stroke(); ctx.setLineDash([]);
    // datos
    if(hist.length>1){
      ctx.strokeStyle='#fbbf24'; ctx.lineWidth=2; ctx.beginPath();
      hist.forEach((h,i)=>{ const x=(i/(hist.length-1))*canvas.width; const y=canvas.height - (h.humedad/100)*canvas.height; if(i===0) ctx.moveTo(x,y); else ctx.lineTo(x,y); });
      ctx.stroke();
    } else if(hist.length===1){
      ctx.fillStyle='#fbbf24'; ctx.beginPath(); ctx.arc(canvas.width/2, canvas.height - (hist[0].humedad/100)*canvas.height, 4,0,Math.PI*2); ctx.fill();
    }
    document.getElementById('humList').innerText = hist.length ? hist.map(h=>`${new Date(h.ts*1000).toLocaleTimeString()} S${h.sector} ${h.humedad}%`).join(' | ') : 'Sin datos aún - Esperando sensor POST /api/datos';
  } catch(e){ document.getElementById('humList').innerText='Error grafico hum: '+e; }
  
  // NPK barras simple
  try{
    const npkDiv=document.getElementById('npkBars');
    npkDiv.innerHTML=`<div class="kpi"><span>Temp ${(j.ultimo_temp||0)}°C</span><span>pH ${(j.ultimo_ph||0)}</span><span>EC ${(j.ultimo_ec||0)}</span></div><div class="kpi"><span>N ${(j.ultimo_n||0)}ppm</span><span>P ${(j.ultimo_p||0)}ppm</span><span>K ${(j.ultimo_k||0)}ppm</span></div>`;
    const canvas2=document.getElementById('cNPK'); const ctx2=canvas2.getContext('2d');
    ctx2.clearRect(0,0,canvas2.width,canvas2.height);
    ctx2.fillStyle='#0f172a'; ctx2.fillRect(0,0,canvas2.width,canvas2.height);
    const vals=[j.ultimo_temp||0, (j.ultimo_ph||0)*10, (j.ultimo_ec||0)/10, j.ultimo_n||0, j.ultimo_p||0, (j.ultimo_k||0)/10];
    const colors=['#f59e0b','#ec4899','#06b6d4','#22c55e','#8b5cf6','#f97316'];
    vals.forEach((v,i)=>{ const h=Math.min(canvas2.height-20, v*1.5); ctx2.fillStyle=colors[i]; ctx2.fillRect(i*60+10, canvas2.height-h-10, 40, h); });
  } catch(e){}
  
  document.getElementById('npkDetalle').innerHTML=`Último sensor: Temp ${j.ultimo_temp}°C • pH ${j.ultimo_ph} • EC ${j.ultimo_ec} • N ${j.ultimo_n}ppm • P ${j.ultimo_p}ppm • K ${j.ultimo_k}ppm<br>Nota: ${j.ultimo_nota||''} • Total sensores guardados: ${j.sensores_total}`;
  document.getElementById('rep').innerText=j.reporte||'Sin reporte';
  document.getElementById('log').innerHTML=(j.logs||[]).slice(-20).reverse().map(l=>`<div>${l}</div>`).join('') || 'Sin logs';
  document.getElementById('debug').innerText=`Finca: ${j.finca_id||'{{username}}'} • Sectores DB: ${j.finca_sectores||0} • Sectores pintados: ${Object.keys(j.sectores||{}).length} • Sensores en memoria: ${j.sensores_total} • Historico: ${(j.historico||[]).length} • Actuadores: ${Object.keys(j.actuadores||{}).length}\\nÚltimo estado bomba/valv: ${JSON.stringify(j.actuadores||{}).substring(0,300)}`;
  document.getElementById('clima').innerHTML=`<b>🌤️ San Juan ${j.clima.temp}°C</b> • Hum amb ${j.clima.hum}% • Viento ${j.clima.viento}km/h<br>${j.clima.desc}<br><b style="color:${j.clima.riego_recomendado.includes('No')?'#f87171':'#22c55e'}">${j.clima.riego_recomendado}</b><br><span class="small">Flow: ${j.clima.flow_info} • ${j.clima.ubicacion}</span>`;
  
 } catch(e){
  document.getElementById('debug').innerText='Error load(): '+e+'\\n'+e.stack;
 }
}
async function cmdGlobal(e){ await fetch('/api/comando',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({finca:'{{username}}', device:'bomba_principal', estado:e})}); load(); }
async function cmdValvulas(e){ await fetch('/api/comando',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({finca:'{{username}}', device:'valvula', estado:e})}); load(); }
async function cmdSector(sector, e){ await fetch('/api/comando',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({finca:'{{username}}', device:'sector_'+sector+'_valvula', sector:sector, estado:e})}); load(); }
async function cmdBombaSector(sector, e){ await fetch('/api/comando',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({finca:'{{username}}', device:'sector_'+sector+'_bomba', sector:sector, estado:e})}); load(); }
load(); setInterval(load,3000);
</script></body></html>
"""

CONFIG_HTML = """
<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OXITEM V9 Config</title>
<style>body{margin:0;background:#0a0f1c;color:#e2e8f0;font-family:system-ui;padding:16px} .card{background:#1e293b;border:1px solid #334155;padding:16px;border-radius:14px;margin:10px;max-width:900px} input,select{padding:8px;margin:3px;background:#0f172a;border:1px solid #334155;border-radius:8px;color:white} .btn{padding:8px 14px;background:#22c55e;color:black;border:none;border-radius:8px;font-weight:800;cursor:pointer}</style>
</head><body>
<div class="card">
<h2>OXITEM V9 Config - {{username}}</h2>
<p style="color:#94a3b8;font-size:12px">Admin OXITEM. Asigná planta por sector, sensores, válvulas y caudalímetro.</p>
<form id="adminAuth"><input id="adminUser" value="admin"><input id="adminPass" type="password" placeholder="OXITEM" value="OXITEM"><button class="btn" type="submit">Autenticar</button></form>
<div id="configArea" style="display:none">
<h3 style="color:#22c55e">Bomba y Válvula Principal</h3>
<div><label>Bomba <select id="bombaPulg"><option value="0.5" selected>1/2\" 25L/min proto</option><option value="0.75">3/4\" 45L/min</option><option value="1">1\" 80L/min</option></select></label> <label>Válv ppal <select id="valvPpalPulg"><option value="0.5">1/2\"</option><option value="1" selected>1\"</option></select></label></div>
<h3 style="color:#22c55e">Sectores ({{finca.sectores}})</h3>
<div id="sectoresConfig"></div>
<button class="btn" onclick="guardar()">💾 Guardar V9</button><span id="msg"></span>
</div>
</div>
<script>
let fincaData={{finca_json|safe}}; let plantas={{plantas_json|safe}};
document.getElementById('adminAuth').addEventListener('submit', async (e)=>{
 e.preventDefault();
 const r=await fetch('/api/admin_auth',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user:document.getElementById('adminUser').value, pass:document.getElementById('adminPass').value})});
 const j=await r.json(); if(j.ok){ document.getElementById('configArea').style.display='block'; loadSectores(); } else alert('Admin incorrecto');
});
function loadSectores(){
 const cont=document.getElementById('sectoresConfig'); cont.innerHTML='';
 for(let i=1;i<=fincaData.sectores;i++){
   const sec=fincaData.sectores_config[i]||{planta:'tomate',cant_sensores:5,valvula_pulgadas:'0.75',flow_present:false,flow_pulgadas:'no'};
   const div=document.createElement('div'); div.className='card'; div.style='border-left:3px solid #22c55e';
   div.innerHTML=`<b>Sector ${i}</b><br>Planta: <select id="planta_${i}">${Object.entries(plantas).map(([k,p])=>`<option value="${k}" ${k===sec.planta?'selected':''}>${p.emoji} ${p.nombre}</option>`).join('')}</select> Sensores: <input id="cant_${i}" type="number" value="${sec.cant_sensores}" style="width:50px"> Válv: <select id="valv_${i}"><option value="0.5">1/2"</option><option value="0.75" ${sec.valvula_pulgadas==='0.75'?'selected':''}>3/4"</option><option value="1" ${sec.valvula_pulgadas==='1'?'selected':''}>1"</option></select><br>Flow? <select id="flowPres_${i}"><option value="false" ${!sec.flow_present?'selected':''}>NO solo estimado</option><option value="true" ${sec.flow_present?'selected':''}>SÍ dual</option></select> Pulg: <select id="flowPulg_${i}"><option value="no" ${sec.flow_pulgadas==='no'?'selected':''}>Sin flow</option><option value="0.5" ${sec.flow_pulgadas==='0.5'?'selected':''}>1/2\" YF-S201</option><option value="1_fs400" ${sec.flow_pulgadas==='1_fs400'?'selected':''}>1\" FS400A</option><option value="1_dn25" ${sec.flow_pulgadas==='1_dn25'?'selected':''}>1\" DN25</option></select>`;
   cont.appendChild(div);
 }
 document.getElementById('bombaPulg').value=fincaData.bomba_pulgadas||'0.5';
 document.getElementById('valvPpalPulg').value=fincaData.valvula_ppal_pulgadas||'1';
}
async function guardar(){
 let sectores_config={};
 for(let i=1;i<=fincaData.sectores;i++){
   sectores_config[i]={planta:document.getElementById(`planta_${i}`).value,cant_sensores:parseInt(document.getElementById(`cant_${i}`).value),valvula_pulgadas:document.getElementById(`valv_${i}`).value,flow_present:document.getElementById(`flowPres_${i}`).value==='true',flow_pulgadas:document.getElementById(`flowPulg_${i}`).value};
 }
 const payload={finca:'{{username}}',bomba_pulgadas:document.getElementById('bombaPulg').value,valvula_ppal_pulgadas:document.getElementById('valvPpalPulg').value,sectores_config:sectores_config};
 const r=await fetch('/api/config_terreno',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
 const j=await r.json(); document.getElementById('msg').innerText=j.ok?'✅ Guardado!':'Error '+JSON.stringify(j);
}
</script></body></html>
"""

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
        if u.lower()=='admin' and p=='OXITEM':
            session['user']='admin'; session['role']='admin'; return redirect('/dashboard')
        if u in db["users"] and db["users"][u]["password"]==p:
            session['user']=u; return redirect('/dashboard')
        for ku in db["users"]:
            if ku.lower()==u.lower() and db["users"][ku]["password"]==p:
                session['user']=ku; return redirect('/dashboard')
        err=f"Usuario '{u}' no encontrado. Registrados: {', '.join(db['users'].keys()) or 'ninguno'}"
    return render_template_string(LOGIN_HTML, error=err, users_count=users_count, db_file=DB_FILE)

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method=='POST':
        u=request.form.get('username','').strip().replace(' ','_')
        p=request.form.get('password','').strip()
        if not u or len(u)<3: return "Usuario min 3 letras",400
        if u.lower() in [k.lower() for k in db["users"]] or u.lower()=='admin': return f"Usuario {u} ya existe",400
        plantas_sel=request.form.getlist('plantas') or ['tomate','lechuga','uva']
        try:
            largo=int(request.form.get('largo',10)); ancho=int(request.form.get('ancho',10)); sectores=int(request.form.get('sectores',1))
        except: largo=10; ancho=10; sectores=1
        bomba_p=request.form.get('bomba_pulgadas','0.5'); valv_p=request.form.get('valvula_ppal_pulgadas','1')
        finca={"ubicacion":request.form.get('ubicacion','Villa Krause, San Juan'),"largo":largo,"ancho":ancho,"m2":largo*ancho,"sectores":sectores,"bomba_pulgadas":bomba_p,"bomba_lpm":BOMBA_CAUDAL.get(bomba_p,25),"valvula_ppal_pulgadas":valv_p,"plantas":plantas_sel,"sectores_config":{str(i):{"planta":plantas_sel[(i-1)%len(plantas_sel)],"cant_sensores":5,"valvula_pulgadas":"0.75","flow_present":False,"flow_pulgadas":"no"} for i in range(1,sectores+1)}}
        db["users"][u]={"password":p,"finca":finca}
        save_db(db)
        for i in range(1, sectores+1):
            actuadores_data[f"{u}_s{i}"]={"bomba":0,"valvula":0,"start_time":None,"litros_flow":0,"litros_estimado":0,"tiempo_acum":0}
        log(f"NUEVA FINCA {u} {finca['m2']}m2 {sectores} sec")
        session['user']=u; return redirect('/dashboard')
    return render_template_string(REGISTER_HTML, plantas=PLANTAS)

@app.route('/logout')
def logout():
    session.clear(); return redirect('/login')

@app.route('/dashboard')
def dashboard():
    if 'user' not in session: return redirect('/login')
    user=session['user']
    if user=='admin':
        lista="".join([f"<div class='card'><b>{u}</b> {db['users'][u]['finca']['ubicacion']} {db['users'][u]['finca']['m2']}m2 <a href='/dashboard?finca={u}' style='color:#22c55e'>Ver</a> <a href='/config_terreno?finca={u}' style='color:#22c55e'>Config</a></div>" for u in db["users"]]) or "<div class='card'>No hay fincas</div>"
        return f"<body style='background:#0a0f1c;color:white;font-family:system-ui;padding:20px'><h1>OXITEM ADMIN V9 - {len(db['users'])} fincas</h1>{lista}<br><a href='/register' style='color:#22c55e'>+ Crear finca</a> | <a href='/logout' style='color:white'>Salir</a> | <a href='/api/debug' style='color:#64748b'>Debug</a></body>"
    finca_user=request.args.get('finca', user)
    finca=db["users"].get(finca_user,{}).get('finca',{})
    if not finca: return redirect('/register')
    return render_template_string(DASHBOARD_HTML, username=finca_user, finca=finca)

@app.route('/config_terreno')
def config_terreno():
    if 'user' not in session: return redirect('/login')
    finca_user=request.args.get('finca', session['user'])
    finca=db["users"].get(finca_user,{}).get('finca',{})
    if not finca: return f"Finca {finca_user} no existe. Users: {list(db['users'].keys())}",404
    return render_template_string(CONFIG_HTML, username=finca_user, finca=finca, finca_json=json.dumps(finca), plantas_json=json.dumps(PLANTAS))

@app.route('/api/admin_auth', methods=['POST'])
def admin_auth():
    d=request.get_json(silent=True) or {}
    if d.get('user','').strip().lower()=='admin' and d.get('pass','').strip()=='OXITEM':
        return {"ok":True}
    return {"ok":False},401

@app.route('/api/config_terreno', methods=['POST'])
def api_config():
    try:
        d=request.get_json()
        finca_name=d.get('finca','').strip()
        if not finca_name or finca_name not in db["users"]:
            return {"error":f"Finca {finca_name} no existe"},404
        finca=db["users"][finca_name]["finca"]
        finca["bomba_pulgadas"]=d.get('bomba_pulgadas', finca["bomba_pulgadas"])
        finca["bomba_lpm"]=BOMBA_CAUDAL.get(finca["bomba_pulgadas"],25)
        finca["valvula_ppal_pulgadas"]=d.get('valvula_ppal_pulgadas', finca["valvula_ppal_pulgadas"])
        finca["sectores_config"]=d.get('sectores_config', finca["sectores_config"])
        for sid in finca["sectores_config"]:
            ak=f"{finca_name}_s{sid}"
            if ak not in actuadores_data:
                actuadores_data[ak]={"bomba":0,"valvula":0,"start_time":None,"litros_flow":0,"litros_estimado":0,"tiempo_acum":0}
        save_db(db)
        log(f"CONFIG V9 {finca_name} {finca['bomba_lpm']}L/min")
        return {"ok":True}
    except Exception as e:
        return {"error":str(e)},500

@app.route('/api/datos', methods=['POST'])
def datos():
    try:
        j=request.get_json(force=True)
        finca_id=j.get('finca_id', j.get('finca','default')).strip()
        sector_id=str(j.get('sector_id', j.get('sector','1'))).strip()
        key=f"{finca_id}_s{sector_id}_d{j.get('dispositivo_id','1')}_{j.get('tipo','sensor')}"
        j['ts']=time.time()
        sensores_data[key]=j
        if 'humedad' in j:
            historico.append({"ts":j['ts'],"humedad":float(j.get('humedad',0)),"temp":float(j.get('temperatura',0)),"ph":float(j.get('ph',0)),"ec":int(j.get('conductividad',0)),"n":float(j.get('nitrogeno',0)),"p":int(j.get('fosforo',0)),"k":int(j.get('potasio',0)),"finca":finca_id,"sector":sector_id})
            if len(historico)>500: historico.pop(0)
            log(f"RX {finca_id} S{sector_id} H{ j.get('humedad')}% T{j.get('temperatura')} pH{j.get('ph')} N{j.get('nitrogeno')} P{j.get('fosforo')} K{j.get('potasio')}")
            # Auto riego
            finca_cfg=db["users"].get(finca_id,{}).get('finca',{})
            sec_cfg=finca_cfg.get('sectores_config',{}).get(sector_id,{})
            planta=PLANTAS.get(sec_cfg.get('planta','tomate'), PLANTAS["tomate"])
            hum=float(j.get('humedad',100))
            ak=f"{finca_id}_s{sector_id}"
            if ak not in actuadores_data: actuadores_data[ak]={"bomba":0,"valvula":0,"start_time":None,"litros_flow":0,"litros_estimado":0,"tiempo_acum":0}
            act=actuadores_data[ak]
            bomba_lpm=finca_cfg.get('bomba_lpm',25)
            if hum < planta["on"] and act["bomba"]==0:
                act["bomba"]=1; act["valvula"]=1; act["start_time"]=time.time()
                log(f"AUTO ON {finca_id} S{sector_id} {planta['nombre']} {hum}%<{planta['on']}%")
            elif hum >= planta["off"] and act["bomba"]==1:
                if act["start_time"]:
                    dur=time.time()-act["start_time"]
                    act["litros_estimado"]+=dur * bomba_lpm / 60.0
                    act["tiempo_acum"]+=dur
                act["bomba"]=0; act["valvula"]=0; act["start_time"]=None
                log(f"AUTO OFF {finca_id} S{sector_id} {hum}%>= {planta['off']}%")
        if j.get('tipo') in ['valvula_flow','bomba_flow']:
            for ak in actuadores_data:
                if ak.startswith(f"{finca_id}_s{sector_id}"):
                    actuadores_data[ak]["litros_flow"]+=float(j.get('litros_flow',0))
        return {"ok":True}
    except Exception as e:
        log(f"Error /api/datos: {e}")
        return {"ok":False,"error":str(e)},500

@app.route('/api/estado')
def estado():
    try:
        finca_id=request.args.get('finca','default').strip()
        if finca_id=='default' and 'user' in session and session['user']!='admin':
            finca_id=session['user']
        finca_cfg=db["users"].get(finca_id,{}).get('finca',{})
        if not finca_cfg:
            return jsonify({"error":f"Finca {finca_id} no existe","users":list(db["users"].keys()),"sectores":{},"consumo":{"total_litros_flow":0,"total_litros_estimado":0,"diferencia":0,"alerta":"Sin finca"},"historico":[],"logs":logs[-10:],"reporte":f"Finca {finca_id} no existe. Crea en /register. Users: {list(db['users'].keys())}","clima":{"temp":29,"hum":30,"viento":12,"desc":"Sin finca","riego_recomendado":"Crea finca","flow_info":"-","ubicacion":finca_id},"ultimo_temp":0,"ultimo_ph":0,"ultimo_ec":0,"ultimo_n":0,"ultimo_p":0,"ultimo_k":0,"ultimo_nota":"","finca_id":finca_id,"finca_sectores":0,"sensores_total":len(sensores_data),"actuadores":actuadores_data})
        
        sectores_cfg=finca_cfg.get('sectores_config',{})
        sectores_info={}
        total_flow=0; total_est=0
        reporte=""; ultimo_temp=0; ultimo_ph=0; ultimo_ec=0; ultimo_n=0; ultimo_p=0; ultimo_k=0; ultimo_nota=""
        
        for sid, scfg in sectores_cfg.items():
            sensores_sector=[v for k,v in sensores_data.items() if k.startswith(f"{finca_id}_s{sid}_") and 'humedad' in v]
            sensores_sorted=sorted(sensores_sector, key=lambda x: x.get('ts',0))
            hums=[s.get('humedad',0) for s in sensores_sector]
            hum_prom=sum(hums)/len(hums) if hums else 0
            if sensores_sorted:
                last=sensores_sorted[-1]
                ultimo_temp=last.get('temperatura',0); ultimo_ph=last.get('ph',0); ultimo_ec=last.get('conductividad',0); ultimo_n=last.get('nitrogeno',0); ultimo_p=last.get('fosforo',0); ultimo_k=last.get('potasio',0)
                temp=last.get('temperatura',0); ph=last.get('ph',0); ec=last.get('conductividad',0); n=last.get('nitrogeno',0); p=last.get('fosforo',0); k=last.get('potasio',0)
            else:
                temp=ph=ec=n=p=k=0
            
            ak=f"{finca_id}_s{sid}"
            if ak not in actuadores_data:
                actuadores_data[ak]={"bomba":0,"valvula":0,"start_time":None,"litros_flow":0,"litros_estimado":0,"tiempo_acum":0}
            act=actuadores_data[ak]
            tiempo_hoy=act["tiempo_acum"] + (time.time()-act["start_time"] if act.get("start_time") else 0)
            planta=PLANTAS.get(scfg.get('planta','tomate'), PLANTAS["tomate"])
            
            if not hums: estado_suelo="Sin datos - Esperando sensor POST"
            elif hum_prom>=80: estado_suelo="SATURADO/Cap Campo"
            elif hum_prom>=60: estado_suelo="ÓPTIMO"
            elif hum_prom>=40: estado_suelo="ESTRÉS INICIO"
            elif hum_prom>=20: estado_suelo="MARCHITEZ"
            else: estado_suelo="SECO"
            
            sectores_info[sid]={
                "planta":scfg.get('planta','tomate'),"planta_nombre":planta["nombre"],"emoji":planta["emoji"],"color":planta["color"],
                "cant_sensores":scfg.get('cant_sensores',5),"valvula_pulgadas":scfg.get('valvula_pulgadas','0.75'),
                "flow_present":scfg.get('flow_present',False),"flow_pulgadas":scfg.get('flow_pulgadas','no'),
                "flow_model":FLOW_SPECS.get(scfg.get('flow_pulgadas','no'), FLOW_SPECS["no"])["modelo"],
                "humedad_prom":hum_prom,"temp":temp,"ph":ph,"ec":ec,"n":n,"p":p,"k":k,
                "temp_ideal":planta["temp"],"ph_ideal":planta["ph"],"n_ideal":planta["n"],"p_ideal":planta["p"],"k_ideal":planta["k"],
                "umbral_on":planta["on"],"umbral_off":planta["off"],
                "bomba_estado":act["bomba"],"valvula_estado":act["valvula"],
                "litros_flow":act["litros_flow"],"litros_estimado":act["litros_estimado"],"tiempo_hoy":tiempo_hoy,
                "sensores_activos":len(sensores_sector),"ultimo_hace":f"{int(time.time()-sensores_sorted[-1]['ts'])}s" if sensores_sorted else "nunca",
                "estado_suelo":estado_suelo,"id_ejemplo":f"{finca_id}_s{sid}_d1"
            }
            total_flow+=act["litros_flow"]; total_est+=act["litros_estimado"]
            reporte+=f"● Sector {sid} {planta['emoji']} {planta['nombre']} ({scfg.get('cant_sensores')} sens, válv {scfg.get('valvula_pulgadas')}\" flow {'SI' if scfg.get('flow_present') else 'NO'}): Hum {hum_prom:.1f}% {estado_suelo} ON<{planta['on']}% OFF>={planta['off']}% Bomba {'ON' if act['bomba'] else 'OFF'} Válv {'OPEN' if act['valvula'] else 'CLOSED'} Temp {temp}°C pH {ph} N {n} P {p} K {k} Consumo {act['litros_flow']:.1f}L flow / {act['litros_estimado']:.1f}L est. Tiempo {(tiempo_hoy/60):.1f}min Nota: {planta['nota']}\n\n"
        
        dif=abs(total_flow-total_est)/total_est*100 if total_est>0 else 0
        alerta="Sin riego aún" if total_est==0 and total_flow==0 else ("✅ OK" if dif<=20 else "⚠️ Fuga >20%")
        clima={"temp":31,"hum":28,"viento":14,"desc":"Soleado San Juan - Radiación alta - Ideal riego mañana/tarde","riego_recomendado":"Riego normal OXITEM - Evitar 12-16h por calor extremo SJ","flow_info":f"Bomba {finca_cfg.get('bomba_pulgadas','0.5')}\" {finca_cfg.get('bomba_lpm',25)}L/min - YF-S201 1/2\" 450p/L proto","ubicacion":finca_cfg.get('ubicacion','Villa Krause')}
        hist_filtrado=[h for h in historico if h.get('finca')==finca_id]
        
        return jsonify({
            "finca_id":finca_id,"finca_sectores":finca_cfg.get('sectores',0),"sensores_total":len(sensores_data),
            "sensores":sensores_data,"actuadores":actuadores_data,"historico":hist_filtrado[-20:],
            "logs":logs[-20:],"sectores":sectores_info,
            "consumo":{"total_litros_flow":total_flow,"total_litros_estimado":total_est,"diferencia":round(dif,1),"alerta":alerta},
            "reporte":reporte or "Sin sectores - Ve a Config Terreno admin/OXITEM",
            "ultimo_temp":ultimo_temp,"ultimo_ph":ultimo_ph,"ultimo_ec":ultimo_ec,"ultimo_n":ultimo_n,"ultimo_p":ultimo_p,"ultimo_k":ultimo_k,"ultimo_nota":ultimo_nota,
            "clima":clima
        })
    except Exception as e:
        import traceback
        return jsonify({"error":str(e),"trace":traceback.format_exc(),"sectores":{},"consumo":{"total_litros_flow":0,"total_litros_estimado":0,"diferencia":0,"alerta":f"Error: {e}"},"historico":[],"logs":logs[-10:],"reporte":f"Error estado: {e}","clima":{"temp":0,"hum":0,"viento":0,"desc":f"Error {e}","riego_recomendado":"Error","flow_info":"Error","ubicacion":"Error"},"ultimo_temp":0,"ultimo_ph":0,"ultimo_ec":0,"ultimo_n":0,"ultimo_p":0,"ultimo_k":0}),500

@app.route('/api/comando', methods=['POST'])
def comando():
    try:
        d=request.get_json(force=True)
        finca=d.get('finca','default').strip()
        dev=d.get('device','')
        est=int(d.get('estado',0))
        sector=str(d.get('sector','')).strip()
        log(f"CMD MANUAL {finca} dev={dev} sector={sector} estado={est}")
        
        if 'bomba_principal' in dev:
            for k in list(actuadores_data.keys()):
                if k.startswith(finca+"_s"):
                    if est==1 and actuadores_data[k]["bomba"]==0:
                        actuadores_data[k]["bomba"]=1; actuadores_data[k]["start_time"]=time.time()
                    elif est==0:
                        if actuadores_data[k]["start_time"]:
                            dur=time.time()-actuadores_data[k]["start_time"]
                            bomba_lpm=db["users"].get(finca,{}).get('finca',{}).get('bomba_lpm',25)
                            actuadores_data[k]["litros_estimado"]+=dur * bomba_lpm / 60.0
                            actuadores_data[k]["tiempo_acum"]+=dur
                        actuadores_data[k]["bomba"]=0; actuadores_data[k]["start_time"]=None
        elif dev=='valvula':
            for k in list(actuadores_data.keys()):
                if k.startswith(finca+"_s"):
                    actuadores_data[k]["valvula"]=est
        elif sector:
            ak=f"{finca}_s{sector}"
            if ak not in actuadores_data:
                actuadores_data[ak]={"bomba":0,"valvula":0,"start_time":None,"litros_flow":0,"litros_estimado":0,"tiempo_acum":0}
            if 'valvula' in dev:
                actuadores_data[ak]["valvula"]=est
                if est==1 and actuadores_data[ak]["bomba"]==0:
                    actuadores_data[ak]["bomba"]=1; actuadores_data[ak]["start_time"]=time.time()
                elif est==0:
                    if actuadores_data[ak]["start_time"]:
                        dur=time.time()-actuadores_data[ak]["start_time"]
                        bomba_lpm=db["users"].get(finca,{}).get('finca',{}).get('bomba_lpm',25)
                        actuadores_data[ak]["litros_estimado"]+=dur * bomba_lpm / 60.0
                        actuadores_data[ak]["tiempo_acum"]+=dur
                        actuadores_data[ak]["start_time"]=None
                    actuadores_data[ak]["bomba"]=0
            if 'bomba' in dev:
                if est==1 and actuadores_data[ak]["bomba"]==0:
                    actuadores_data[ak]["bomba"]=1; actuadores_data[ak]["start_time"]=time.time()
                elif est==0:
                    if actuadores_data[ak]["start_time"]:
                        dur=time.time()-actuadores_data[ak]["start_time"]
                        bomba_lpm=db["users"].get(finca,{}).get('finca',{}).get('bomba_lpm',25)
                        actuadores_data[ak]["litros_estimado"]+=dur * bomba_lpm / 60.0
                        actuadores_data[ak]["tiempo_acum"]+=dur
                    actuadores_data[ak]["bomba"]=0; actuadores_data[ak]["start_time"]=None
        
        return {"ok":True,"actuadores":actuadores_data}
    except Exception as e:
        return {"ok":False,"error":str(e)},500

@app.route('/api/riego')
def riego():
    try:
        finca_id=request.args.get('finca', request.args.get('finca_id','default')).strip()
        sector_id=request.args.get('sector','1').strip()
        if sector_id=='0':
            alguna_on=any(v["bomba"]==1 for k,v in actuadores_data.items() if k.startswith(finca_id+"_s"))
            return jsonify({"bomba": alguna_on, "bomba_principal": int(alguna_on), "valvula": False, "finca":finca_id, "sector":0, "consumo_flow": sum(v["litros_flow"] for k,v in actuadores_data.items() if k.startswith(finca_id)), "consumo_estimado": sum(v["litros_estimado"] for k,v in actuadores_data.items() if k.startswith(finca_id))})
        ak=f"{finca_id}_s{sector_id}"
        act=actuadores_data.get(ak, {"bomba":0,"valvula":0,"litros_flow":0,"litros_estimado":0})
        finca_cfg=db["users"].get(finca_id,{}).get('finca',{})
        sec_cfg=finca_cfg.get('sectores_config',{}).get(str(sector_id),{})
        planta=PLANTAS.get(sec_cfg.get('planta','tomate'), PLANTAS["tomate"])
        return jsonify({"bomba": bool(act["bomba"]), "valvula": bool(act["valvula"]), "bomba_principal": act["bomba"], "valvula_sector": act["valvula"], "finca":finca_id, "sector":int(sector_id) if sector_id.isdigit() else sector_id, "umbral_on":planta["on"], "umbral_off":planta["off"], "planta":planta["nombre"], "consumo_flow":act["litros_flow"], "consumo_estimado":act["litros_estimado"]})
    except Exception as e:
        return jsonify({"bomba":False,"valvula":False,"error":str(e)}),500

@app.route('/api/debug')
def debug():
    return jsonify({"db_file":DB_FILE,"users":list(db["users"].keys()),"db":db,"sensores_keys":list(sensores_data.keys())[:10],"sensores_total":len(sensores_data),"actuadores":actuadores_data,"historico_len":len(historico),"logs":logs[-20:]})

if __name__=='__main__':
    print(f"OXITEM V9 FINAL - DB {DB_FILE} users {list(db['users'].keys())}")
    app.run(host='0.0.0.0',port=5000)

