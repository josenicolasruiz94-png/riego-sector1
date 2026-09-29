"""
OXITEM V10 PROFESIONAL - RECUADROS GRANDES Y ESTETICA PRO
Fix: recuadros grandes espaciados, bomba siempre prende con valvula, sensor 0% VWC muestra advertencia
"""
from flask import Flask, request, jsonify, render_template_string, session, redirect
from flask_cors import CORS
import time, json, os
from datetime import datetime

app = Flask(__name__)
app.secret_key = "oxitem_v10_pro_grande_2026"
CORS(app)

DB_FILE = "fincas_db_v10.json"
def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE,'r') as f: return json.load(f)
        except: pass
    # Migrar de v9
    if os.path.exists("fincas_db_v9.json"):
        try:
            with open("fincas_db_v9.json",'r') as f:
                old=json.load(f)
                save_db(old)
                return old
        except: pass
    return {"users": {}}
def save_db(db):
    try:
        with open(DB_FILE,'w') as f: json.dump(db,f,indent=2)
    except: pass

db = load_db()
sensores_data = {}
actuadores_data = {}
historico = []
logs = []

BOMBA_CAUDAL = {"0.5":25,"0.75":45,"1":80,"1.25":120,"1.5":180}
FLOW_SPECS = {"0.5": {"modelo": "YF-S201 1/2\" 1-30L/min 450p/L","ppl":450},"1_fs400":{"modelo":"FS400A 1\" 1-60L/min 360p/L","ppl":360},"1_dn25":{"modelo":"DN25 1\" 10-100L/min 450p/L","ppl":450},"no":{"modelo":"Sin caudalímetro (solo estimado)","ppl":0}}

PLANTAS = {
    "tomate": {"nombre": "Tomate", "emoji":"🍅", "on":60, "off":80, "color":"#ef4444", "hum":"70-80%", "ph":"5.5-6.8", "temp":"18-27°C", "n":"150-200", "p":"50-80", "k":"250-350", "nota":"Muy demandante K"},
    "lechuga": {"nombre": "Lechuga", "emoji":"🥬", "on":60, "off":75, "color":"#22c55e", "hum":"60-75%", "ph":"6.0-7.0", "temp":"15-22°C", "n":"120-150", "p":"30-50", "k":"150-200", "nota":"Media sombra verano SJ"},
    "paleta": {"nombre": "Paleta de Pintor", "emoji":"🎨", "on":60, "off":75, "color":"#f472b6", "hum":"60-75%", "ph":"5.5-6.5", "temp":"18-26°C", "n":"80", "p":"30", "k":"100", "nota":""},
    "uva": {"nombre": "Uva Vid SJ", "emoji":"🍇", "on":40, "off":60, "color":"#7c3aed", "hum":"40-60%", "ph":"6.0-7.5", "temp":"15-30°C", "n":"80-120", "p":"40-60", "k":"150-250", "nota":"Emblemático SJ"},
    "olivo": {"nombre": "Olivo", "emoji":"🫒", "on":30, "off":50, "color":"#65a30d", "hum":"30-50%", "ph":"6.0-8.0", "temp":"15-30°C", "n":"60-100", "p":"20-40", "k":"100-200", "nota":"Tolerante sequía"},
    "menta": {"nombre": "Menta", "emoji":"🌿", "on":75, "off":85, "color":"#10b981", "hum":"75-85%", "ph":"6.0-7.0", "temp":"15-25°C", "n":"150", "p":"50", "k":"150", "nota":"Invasiva"},
    "ruda": {"nombre": "Ruda", "emoji":"☘️", "on":40, "off":55, "color":"#65a30d", "hum":"40-55%", "ph":"6.0-8.0", "temp":"18-28°C", "n":"50-80", "p":"20-30", "k":"80-120", "nota":"Odia encharque"},
    "romero": {"nombre": "Romero", "emoji":"🌾", "on":30, "off":50, "color":"#16a34a", "hum":"30-50%", "ph":"5.5-7.0", "temp":"15-28°C", "n":"50", "p":"20", "k":"100", "nota":"Si lo regas mucho se muere"},
    "papa": {"nombre": "Papa", "emoji":"🥔", "on":65, "off":80, "color":"#a16207", "hum":"65-80%", "ph":"5.0-6.0", "temp":"15-22°C", "n":"100-150", "p":"80-100", "k":"300-400", "nota":""},
    "zanahoria": {"nombre": "Zanahoria", "emoji":"🥕", "on":60, "off":70, "color":"#f97316", "hum":"60-70%", "ph":"6.0-6.8", "temp":"16-24°C", "n":"100", "p":"60", "k":"200", "nota":""},
    "habas": {"nombre": "Habas", "emoji":"🫘", "on":60, "off":75, "color":"#65a30d", "hum":"60-75%", "ph":"6.0-7.5", "temp":"10-22°C", "n":"30-50", "p":"60", "k":"150", "nota":"Fija N"},
    "ajo": {"nombre": "Ajo", "emoji":"🧄", "on":50, "off":65, "color":"#e5e7eb", "hum":"50-65%", "ph":"6.0-7.0", "temp":"12-22°C", "n":"120", "p":"50", "k":"180", "nota":""},
    "cebolla": {"nombre": "Cebolla", "emoji":"🧅", "on":60, "off":70, "color":"#fef3c7", "hum":"60-70%", "ph":"6.0-7.0", "temp":"13-24°C", "n":"110", "p":"70", "k":"180", "nota":""},
    "zapallo_ancho": {"nombre": "Zapallo Ancho", "emoji":"🎃", "on":70, "off":80, "color":"#f59e0b", "hum":"70-80%", "ph":"6.0-7.5", "temp":"20-30°C", "n":"150", "p":"50", "k":"250", "nota":""},
    "frutilla": {"nombre": "Frutilla", "emoji":"🍓", "on":65, "off":75, "color":"#f43f5e", "hum":"65-75%", "ph":"5.5-6.5", "temp":"15-24°C", "n":"100", "p":"70", "k":"200", "nota":"pH ácido"},
    "pepino": {"nombre": "Pepino", "emoji":"🥒", "on":75, "off":85, "color":"#22c55e", "hum":"75-85%", "ph":"5.5-6.8", "temp":"20-30°C", "n":"150", "p":"50", "k":"250", "nota":""},
    "copete": {"nombre": "Copete", "emoji":"🌸", "on":50, "off":65, "color":"#f97316", "hum":"50-65%", "ph":"6.0-7.0", "temp":"18-28°C", "n":"80", "p":"30", "k":"120", "nota":"Repelente"},
    "clavel": {"nombre": "Clavel", "emoji":"🌹", "on":50, "off":60, "color":"#e11d48", "hum":"50-60%", "ph":"6.0-7.5", "temp":"15-24°C", "n":"120", "p":"50", "k":"180", "nota":""},
    "petunia": {"nombre": "Petuña", "emoji":"🌺", "on":60, "off":70, "color":"#a855f7", "hum":"60-70%", "ph":"5.5-6.5", "temp":"16-26°C", "n":"120", "p":"50", "k":"150", "nota":""},
    "girasol": {"nombre": "Girasol", "emoji":"🌻", "on":60, "off":75, "color":"#eab308", "hum":"60-75%", "ph":"6.0-7.5", "temp":"20-30°C", "n":"150", "p":"60", "k":"200", "nota":""},
    "rosa": {"nombre": "Rosa", "emoji":"🌹", "on":60, "off":70, "color":"#ec4899", "hum":"60-70%", "ph":"6.0-6.8", "temp":"15-25°C", "n":"150", "p":"60", "k":"200", "nota":""},
    "calanchoe": {"nombre": "Calanchoe", "emoji":"🌵", "on":30, "off":45, "color":"#06b6d4", "hum":"30-45%", "ph":"6.0-7.0", "temp":"15-25°C", "n":"50", "p":"20", "k":"80", "nota":""},
    "lazo": {"nombre": "Lazo Amor", "emoji":"💚", "on":50, "off":65, "color":"#22c55e", "hum":"50-65%", "ph":"6.0-7.0", "temp":"15-26°C", "n":"80", "p":"30", "k":"100", "nota":""},
    "garrita": {"nombre": "Garrita Oso", "emoji":"🐻", "on":20, "off":35, "color":"#a3a3a3", "hum":"20-35%", "ph":"6.0-7.5", "temp":"15-28°C", "n":"30", "p":"10", "k":"50", "nota":"Extrema"},
}

def log(msg):
    ts=datetime.now().strftime("%H:%M:%S")
    logs.append(f"{ts} - {msg}")
    if len(logs)>300: logs.pop(0)
    print(msg)

LOGIN_HTML = """
<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OXITEM V10 Login</title>
<style>body{margin:0;background:#0a0f1c;color:white;font-family:system-ui;display:flex;align-items:center;justify-content:center;min-height:100vh}
.card{background:#1e293b;border:1px solid #334155;padding:32px;border-radius:20px;width:400px}
.logo{font-size:34px;font-weight:900} .logo span{color:#22c55e}
input{width:100%;padding:12px;margin:8px 0;background:#0f172a;border:1px solid #334155;border-radius:10px;color:white;box-sizing:border-box}
.btn{width:100%;padding:12px;background:#22c55e;color:black;border:none;border-radius:10px;font-weight:800;cursor:pointer}
</style></head><body>
<div class="card"><div class="logo">OX<span>ITEM</span> V10 PRO</div><div style="color:#94a3b8;font-size:11px">RECUADROS GRANDES • 36 PLANTAS • BOMBA FIX</div>
<form method="POST" action="/login" style="margin-top:16px"><input name="username" placeholder="Usuario finca (finca_demo)" required><input name="password" type="password" placeholder="Contraseña" required><button class="btn">INGRESAR →</button></form>
<a href="/register" style="color:#22c55e;display:block;text-align:center;margin-top:12px;font-size:13px;text-decoration:none">Crear finca nueva</a>
{% if error %}<div style="color:#f87171;background:rgba(248,113,113,0.1);padding:8px;border-radius:8px;margin-top:10px;font-size:12px">{{error}}</div>{% endif %}
<div style="font-size:10px;color:#64748b;margin-top:10px">Usuarios: {{users_count}} | Admin: admin / OXITEM</div></div></body></html>
"""

REGISTER_HTML = """
<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OXITEM V10 Registro</title>
<style>body{margin:0;background:#0f172a;color:white;font-family:system-ui;padding:20px}
.card{background:#1e293b;border:1px solid #334155;padding:24px;border-radius:18px;max-width:850px;margin:0 auto}
input,select{width:100%;padding:10px;margin:5px 0;background:#0f172a;border:1px solid #334155;border-radius:8px;color:white;box-sizing:border-box}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.plant-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;max-height:420px;overflow:auto;background:#0f172a;padding:10px;border-radius:10px;border:1px solid #334155}
.plant-grid label{font-size:11px;padding:5px;border-radius:6px;display:flex;gap:4px;align-items:center}
.btn{width:100%;padding:12px;background:#22c55e;color:black;border:none;border-radius:10px;font-weight:800;cursor:pointer;margin-top:12px}
.grupo{color:#22c55e;font-weight:800;font-size:11px;grid-column:1/-1;margin-top:10px}
</style></head><body>
<div class="card"><h2>OX<span style="color:#22c55e">ITEM</span> V10 - Nueva Finca - Recuadros Grandes</h2>
<form method="POST" action="/register">
<div class="grid"><input name="username" placeholder="Usuario sin espacios ej: finca_demo" required><input name="password" type="password" placeholder="Contraseña" required></div>
<input name="ubicacion" placeholder="Ubicación para mapa Ej: Villa Krause, Rawson, San Juan" required>
<div class="grid"><input name="largo" type="number" value="10" required><input name="ancho" type="number" value="10" required></div>
<div class="grid"><input name="sectores" type="number" min="1" max="10" value="1" required><select name="bomba_pulgadas"><option value="0.5" selected>Bomba 1/2\" 25L/min proto</option><option value="1">1\" 80L/min</option></select></div>
<h3 style="color:#22c55e;font-size:12px">Cultivos (36 plantas)</h3>
<div class="plant-grid">
{% for grupo in ['Huerta','Aromáticas','Frutales','Frutal SJ','Flor','Interior','Suculenta'] %}
<div class="grupo">{{grupo}}</div>
{% for key, pl in plantas.items() if pl.grupo==grupo %}
<label><input type="checkbox" name="plantas" value="{{key}}"> {{pl.emoji}} {{pl.nombre}}</label>
{% endfor %}
{% endfor %}
</div>
<button class="btn">CREAR FINCA V10 GRANDE →</button>
</form></div></body></html>
"""

DASHBOARD_HTML = """
<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OXITEM V10 - {{username}}</title>
<style>
body{margin:0;background:#080e1c;color:#e2e8f0;font-family:system-ui}
.header{background:#0f172a;border-bottom:1px solid #1e293b;padding:16px 24px;display:flex;justify-content:space-between;flex-wrap:wrap;gap:12px;position:sticky;top:0;z-index:10}
.logo{font-weight:900;font-size:24px;color:white} .logo span{color:#22c55e}
.card{background:#162032;border:1px solid #2a3a52;border-radius:20px;padding:20px;margin:16px;box-shadow:0 8px 24px rgba(0,0,0,0.3)}
.card-large{padding:28px;margin:20px;border-radius:24px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(380px,1fr));gap:20px;padding:16px}
.grid-single{display:grid;grid-template-columns:1fr;gap:20px;padding:16px}
.val{font-size:36px;font-weight:900;letter-spacing:-1px} .val-small{font-size:14px;font-weight:700}
.small{font-size:12px;color:#94a3b8;line-height:1.4}
.btn{padding:10px 18px;border-radius:10px;border:none;font-weight:800;cursor:pointer;font-size:13px;margin:4px;transition:0.2s}
.btn:hover{transform:translateY(-1px)}
.btn-dark{background:#0f172a;color:white;border:1px solid #334155} .btn-green{background:linear-gradient(135deg,#22c55e,#16a34a);color:black} .btn-red{background:linear-gradient(135deg,#ef4444,#dc2626);color:white}
.badge{padding:6px 12px;border-radius:12px;font-size:11px;font-weight:800;letter-spacing:0.5px}
.log{background:#0f172a;border:1px solid #1e293b;color:#86efac;padding:14px;border-radius:12px;font-family:monospace;font-size:11px;max-height:260px;overflow:auto}
.kpi{font-size:13px;display:flex;justify-content:space-between;margin:4px 0;padding:4px 0;border-bottom:1px solid #1e293b20}
.bar{height:10px;background:#0f172a;border-radius:10px;overflow:hidden;margin-top:8px} .fill{height:100%;background:linear-gradient(90deg,#22c55e,#06b6d4)}
canvas{width:100%!important;max-height:220px;border-radius:10px;background:#0f172a}
#map{width:100%;height:240px;background:#0f172a;border-radius:16px;border:1px solid #334155;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#64748b;font-size:13px;padding:16px;text-align:center}
.sector-header{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;margin-bottom:12px}
.sector-title{font-size:16px;font-weight:800;letter-spacing:0.5px}
.data-row{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin:12px 0}
.data-box{background:#0f172a;border:1px solid #1e293b;border-radius:12px;padding:12px;text-align:center}
.data-box .label{font-size:10px;color:#64748b;letter-spacing:0.5px} .data-box .value{font-size:18px;font-weight:800;margin-top:2px}
</style></head><body>
<div class="header">
<div><div class="logo">OX<span>ITEM</span> V10 <span style="font-size:12px;color:#64748b;font-weight:500">PRO • RECUADROS GRANDES</span></div><div class="small" style="margin-top:4px">{{finca.ubicacion}} • {{finca.largo}}x{{finca.ancho}}m {{finca.m2}}m² • {{finca.sectores}} sectores • Bomba {{finca.bomba_pulgadas}}" {{finca.bomba_lpm}}L/min • Válv ppal {{finca.valvula_ppal_pulgadas}}"</div></div>
<div style="display:flex;gap:8px;align-items:center"><a href="/config_terreno?finca={{username}}" style="background:#22c55e;color:black;padding:10px 16px;border-radius:10px;text-decoration:none;font-weight:800;font-size:13px">⚙️ Configurar Terreno</a><a href="/logout" style="color:#94a3b8;font-size:13px;text-decoration:none;margin-left:8px">Salir</a></div>
</div>

<div class="card card-large" style="background:linear-gradient(135deg,rgba(34,197,94,0.12),rgba(6,182,212,0.08));border-color:rgba(34,197,94,0.3)">
<div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:16px"><div><b style="font-size:16px;letter-spacing:0.5px">💧 CONSUMO DUAL OXITEM V10</b><div class="small" style="margin-top:4px">Flowmeter YF-S201 1/2\" (450p/L) prototipo + estimado tiempo x bomba • Funciona con y sin caudalímetro • Bomba {{finca.bomba_pulgadas}}" {{finca.bomba_lpm}}L/min</div></div><div id="consumoResumen" style="font-size:13px;text-align:right;min-width:280px">Cargando consumo...</div></div>
<div class="bar" style="height:12px;margin-top:12px"><div id="consumoFill" class="fill" style="width:15%"></div></div>
</div>

<div id="sectoresContainer" class="grid">Cargando sectores grandes...</div>

<div class="grid">
<div class="card card-large"><b style="font-size:14px;letter-spacing:0.5px">📈 HISTORIAL HUMEDAD VWC % (últimos 20) - 0% aire / 100% agua - Cap Campo 80% objetivo</b><canvas id="cHum" width="600" height="240"></canvas><div id="humList" class="small" style="margin-top:12px;max-height:100px;overflow:auto;background:#0f172a;padding:10px;border-radius:10px"></div></div>
<div class="card card-large"><b style="font-size:14px">CONTROL & CLIMA SAN JUAN + MAPA</b>
<div style="margin:16px 0;display:grid;grid-template-columns:1fr 1fr;gap:8px"><button class="btn btn-green" onclick="cmdGlobal(1)">BOMBA ON</button><button class="btn btn-red" onclick="cmdGlobal(0)">BOMBA OFF</button><button class="btn btn-green" onclick="cmdValvulas(1)">Todas Válv ON</button><button class="btn btn-red" onclick="cmdValvulas(0)">Todas Válv OFF</button></div>
<div id="clima" style="background:#0f172a;padding:14px;border-radius:12px;font-size:12px;border:1px solid #1e293b;line-height:1.5">Cargando clima San Juan...</div>
<div id="map" style="margin-top:16px">🗺️ Mapa OXITEM<br><span style="font-size:11px">{{finca.ubicacion}}</span><br><a href="https://www.google.com/maps/search/{{finca.ubicacion}}" target="_blank" style="color:#22c55e;font-weight:700;margin-top:8px;display:inline-block">Abrir en Google Maps →</a><br><span class="small" style="margin-top:8px">Flow: YF-S201 1/2\" 450p/L proto → FS400A 1\" 360p/L final<br>Estimado = tiempo x caudal bomba {{finca.bomba_lpm}}L/min</span></div>
</div>
</div>

<div class="grid">
<div class="card card-large"><b style="font-size:14px">📊 ÚLTIMOS NPK + pH + EC + TEMP - Sensores 7en1</b><div id="npkBars" style="margin:12px 0"></div><div id="npkDetalle" class="small" style="background:#0f172a;padding:12px;border-radius:10px;margin-top:8px"></div><canvas id="cNPK" width="600" height="160"></canvas><div class="small" style="margin-top:8px;color:#fbbf24">⚠️ Si ves pH 0, N 0, P 0, K 0 es porque el sensor 7en1 está al aire o sin calibrar. Debe estar clavado en tierra húmeda. Humedad 0% VWC = aire = 3% RAW según tu ficha Villa Krause.</div></div>
<div class="card card-large"><b style="font-size:14px">📋 REPORTE AGRONÓMICO POR SECTOR - Con temp, pH, N, P, K, bomba, válvula, consumo</b><div id="rep" style="font-size:12px;white-space:pre-wrap;max-height:400px;overflow:auto;line-height:1.6;margin-top:12px;color:#cbd5e1;background:#0f172a;padding:14px;border-radius:12px">Cargando reporte...</div></div>
</div>

<div class="card card-large"><b style="font-size:14px">LOGS BOMBA/VÁLVULA - Activaciones y datos sensor</b><div id="log" class="log" style="margin-top:12px">Cargando logs...</div></div>

<div class="card"><b class="small">DEBUG - Si algo no anda, copia esto y mandamelo</b><div id="debug" class="small" style="font-family:monospace;white-space:pre-wrap;background:#0f172a;padding:10px;border-radius:8px;margin-top:8px"></div></div>

<script>
let lastData=null;
async function load(){
 try{
  const r=await fetch('/api/estado?finca={{username}}&t='+Date.now());
  const j=await r.json();
  lastData=j;
  if(j.error){ document.getElementById('debug').innerText='Error: '+j.error; return; }
  
  document.getElementById('consumoResumen').innerHTML=`Total: <b style="font-size:15px">${(j.consumo.total_litros_flow||0).toFixed(1)} L flow</b> / <b style="font-size:15px">${(j.consumo.total_litros_estimado||0).toFixed(1)} L est.</b><br>Dif ${j.consumo.diferencia}% <span style="color:${j.consumo.diferencia>20?'#f87171':'#22c55e'}">${j.consumo.alerta}</span><br><span class="small">${j.sensores_total||0} sensores guardados • ${Object.keys(j.sectores||{}).length} sectores • ${j.finca_sectores||0} en DB</span>`;
  document.getElementById('consumoFill').style.width=Math.min(100, (j.consumo.total_litros_estimado||0)/2)+'%';
  
  const cont=document.getElementById('sectoresContainer');
  cont.innerHTML='';
  const sectores=j.sectores||{};
  if(Object.keys(sectores).length===0){
    cont.innerHTML='<div class="card card-large" style="grid-column:1/-1;text-align:center;padding:40px">No hay sectores. Ve a Config Terreno (admin/OXITEM) y guarda. Si ya guardaste, borra finca y crea de nuevo.<br>DB sectores: '+(j.finca_sectores||0)+'</div>';
  } else {
    Object.entries(sectores).forEach(([sid, sec])=>{
      const estadoColor = sec.humedad_prom < sec.umbral_on ? '#f87171' : sec.humedad_prom >= sec.umbral_off ? '#22c55e' : '#fbbf24';
      const div=document.createElement('div'); div.className='card card-large'; div.style.borderLeft=`6px solid ${sec.color||'#22c55e'}`;
      div.innerHTML=`
        <div class="sector-header"><div class="sector-title"><span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:${sec.color||'#22c55e'};margin-right:8px"></span>SECTOR ${sid} • ${(sec.planta_nombre||'').toUpperCase()} ${sec.emoji||''}</div><div class="badge" style="background:${estadoColor}20;color:${estadoColor};border:1px solid ${estadoColor}40;font-size:12px;padding:8px 12px">${sec.bomba_estado?'BOMBA ON':'BOMBA OFF'} • ${sec.valvula_estado?'VÁLV OPEN':'CLOSED'}</div></div>
        <div class="val" style="color:${estadoColor}">${(sec.humedad_prom||0).toFixed(1)}<span style="font-size:16px">% VWC</span> <span style="font-size:13px;color:#94a3b8">${sec.estado_suelo||''}</span></div>
        <div class="data-row">
          <div class="data-box"><div class="label">TEMPERATURA</div><div class="value">${sec.temp||0}°C</div><div class="small">ideal ${sec.temp_ideal||''}</div></div>
          <div class="data-box"><div class="label">pH SUELO</div><div class="value">${sec.ph||0}</div><div class="small">ideal ${sec.ph_ideal||''}</div></div>
          <div class="data-box"><div class="label">EC / CONDUC</div><div class="value">${sec.ec||0}</div><div class="small">µS/cm</div></div>
        </div>
        <div class="data-row">
          <div class="data-box"><div class="label">NITRÓGENO N</div><div class="value">${sec.n||0} ppm</div><div class="small">${sec.n_ideal||''}</div></div>
          <div class="data-box"><div class="label">FÓSFORO P</div><div class="value">${sec.p||0} ppm</div><div class="small">${sec.p_ideal||''}</div></div>
          <div class="data-box"><div class="label">POTASIO K</div><div class="value">${sec.k||0} ppm</div><div class="small">${sec.k_ideal||''}</div></div>
        </div>
        <div style="margin-top:16px;display:flex;gap:8px;flex-wrap:wrap"><button class="btn btn-green" onclick="cmdSector(${sid},1)">Válv S${sid} ON</button><button class="btn btn-red" onclick="cmdSector(${sid},0)">Válv S${sid} OFF</button><button class="btn btn-dark" style="padding:10px 16px" onclick="cmdBombaSector(${sid},1)">Bomba S${sid} ON</button><button class="btn btn-dark" style="padding:10px 16px" onclick="cmdBombaSector(${sid},0)">Bomba OFF</button></div>
        <div style="margin-top:16px;display:flex;justify-content:space-between;font-size:12px;background:#0f172a;padding:10px;border-radius:10px"><span>💧 ${(sec.litros_flow||0).toFixed(1)}L flow</span><span>${(sec.litros_estimado||0).toFixed(1)}L estimado</span><span>⏱ ${((sec.tiempo_hoy||0)/60).toFixed(1)} min hoy</span></div>
        <div class="bar" style="height:12px;margin-top:12px"><div class="fill" style="width:${Math.min(100,sec.humedad_prom||0)}%;background:${sec.color||'#22c55e'}"></div></div>
        <div class="small" style="margin-top:12px;display:flex;justify-content:space-between"><span>${sec.sensores_activos||0} sensores activos • último hace ${sec.ultimo_hace||'nunca'}</span><span>ID: ${sec.id_ejemplo||''}</span></div>
        <div class="small" style="margin-top:8px">Válvula ${sec.valvula_pulgadas}" • Flow ${sec.flow_present?sec.flow_model:'NO (solo estimado)'} • ${sec.cant_sensores} sensores configurados • ON &lt;${sec.umbral_on}% OFF ≥${sec.umbral_off}%</div>
      `;
      cont.appendChild(div);
    });
  }
  
  // Grafico humedad simple sin libreria
  try{
    const canvas=document.getElementById('cHum'); const ctx=canvas.getContext('2d'); const hist=j.historico||[];
    ctx.clearRect(0,0,canvas.width,canvas.height);
    ctx.fillStyle='#0f172a'; ctx.fillRect(0,0,canvas.width,canvas.height);
    ctx.strokeStyle='#1e293b'; ctx.lineWidth=1; for(let y=0;y<canvas.height;y+=30){ ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(canvas.width,y); ctx.stroke(); }
    ctx.strokeStyle='#22c55e'; ctx.setLineDash([6,6]); ctx.lineWidth=1; ctx.beginPath(); ctx.moveTo(0,canvas.height*0.2); ctx.lineTo(canvas.width,canvas.height*0.2); ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle='#22c55e'; ctx.font='11px system-ui'; ctx.fillText('80% Cap Campo objetivo',10,canvas.height*0.2-6);
    if(hist.length>1){
      ctx.strokeStyle='#fbbf24'; ctx.lineWidth=3; ctx.beginPath();
      hist.forEach((h,i)=>{ const x=(i/(hist.length-1))*canvas.width; const y=canvas.height - (h.humedad/100)*canvas.height; if(i===0) ctx.moveTo(x,y); else ctx.lineTo(x,y); });
      ctx.stroke();
      ctx.fillStyle='#fbbf24'; hist.forEach((h,i)=>{ const x=(i/(hist.length-1))*canvas.width; const y=canvas.height - (h.humedad/100)*canvas.height; ctx.beginPath(); ctx.arc(x,y,3,0,Math.PI*2); ctx.fill(); });
    } else if(hist.length===1){
      ctx.fillStyle='#fbbf24'; ctx.beginPath(); ctx.arc(canvas.width/2, canvas.height - (hist[0].humedad/100)*canvas.height, 6,0,Math.PI*2); ctx.fill();
    }
    document.getElementById('humList').innerText = hist.length ? hist.map(h=>`${new Date(h.ts*1000).toLocaleTimeString()} S${h.sector} ${h.humedad}% VWC`).join('  |  ') : 'Sin datos aún - Esperando POST /api/datos del sensor. Si ves 0% es porque el sensor está al aire (3% RAW = 0% VWC según ficha Villa Krause). Clávalo en tierra húmeda.';
  } catch(e){ document.getElementById('humList').innerText='Error grafico: '+e; }
  
  // NPK
  try{
    const npkDiv=document.getElementById('npkBars');
    npkDiv.innerHTML=`<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px"><div class="data-box"><div class="label">TEMP</div><div class="value">${j.ultimo_temp||0}°C</div></div><div class="data-box"><div class="label">pH</div><div class="value">${j.ultimo_ph||0}</div></div><div class="data-box"><div class="label">EC</div><div class="value">${j.ultimo_ec||0}</div></div></div><div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-top:8px"><div class="data-box"><div class="label">N</div><div class="value">${j.ultimo_n||0}ppm</div></div><div class="data-box"><div class="label">P</div><div class="value">${j.ultimo_p||0}ppm</div></div><div class="data-box"><div class="label">K</div><div class="value">${j.ultimo_k||0}ppm</div></div></div>`;
    const canvas2=document.getElementById('cNPK'); const ctx2=canvas2.getContext('2d');
    ctx2.clearRect(0,0,canvas2.width,canvas2.height); ctx2.fillStyle='#0f172a'; ctx2.fillRect(0,0,canvas2.width,canvas2.height);
    const vals=[j.ultimo_temp||0, (j.ultimo_ph||0)*12, (j.ultimo_ec||0)/15, j.ultimo_n||0, j.ultimo_p||0, (j.ultimo_k||0)/3];
    const colors=['#f59e0b','#ec4899','#06b6d4','#22c55e','#8b5cf6','#f97316']; const labels=['Temp','pH x12','EC/15','N','P','K/3'];
    vals.forEach((v,i)=>{ const h=Math.min(canvas2.height-40, v*1.2); const x=i*95+20; ctx2.fillStyle=colors[i]; ctx2.fillRect(x, canvas2.height-h-30, 50, h); ctx2.fillStyle='#94a3b8'; ctx2.font='10px system-ui'; ctx2.fillText(labels[i], x, canvas2.height-10); ctx2.fillText(Math.round(v), x+10, canvas2.height-h-35); });
  } catch(e){}
  
  document.getElementById('npkDetalle').innerHTML=`Último sensor: Temp ${j.ultimo_temp}°C • pH ${j.ultimo_ph} • EC ${j.ultimo_ec} • N ${j.ultimo_n}ppm • P ${j.ultimo_p}ppm • K ${j.ultimo_k}ppm<br>Nota: ${j.ultimo_nota||''} • Sensores guardados: ${j.sensores_total} • Si pH y NPK en 0, el sensor 7en1 no está leyendo bien - revisa cableado RS485 A/B`;
  document.getElementById('rep').innerText=j.reporte||'Sin reporte';
  document.getElementById('log').innerHTML=(j.logs||[]).slice(-25).reverse().map(l=>`<div>${l}</div>`).join('') || 'Sin logs';
  document.getElementById('debug').innerText=`Finca: ${j.finca_id} • Sectores DB: ${j.finca_sectores} • Pintados: ${Object.keys(j.sectores||{}).length} • Sensores: ${j.sensores_total} • Historico: ${(j.historico||[]).length} • Actuadores: ${JSON.stringify(j.actuadores||{}).substring(0,400)}`;
  document.getElementById('clima').innerHTML=`<b style="font-size:14px">🌤️ San Juan ${j.clima.temp}°C</b> • Hum amb ${j.clima.hum}% • Viento ${j.clima.viento}km/h<br>${j.clima.desc}<br><b style="color:${j.clima.riego_recomendado.includes('No')?'#f87171':'#22c55e'};font-size:13px">${j.clima.riego_recomendado}</b><br><span class="small" style="margin-top:8px;display:block">Flow: ${j.clima.flow_info} • ${j.clima.ubicacion}</span>`;
  
 } catch(e){
  document.getElementById('debug').innerText='Error load(): '+e;
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
<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OXITEM V10 Config</title>
<style>body{margin:0;background:#0a0f1c;color:#e2e8f0;font-family:system-ui;padding:20px} .card{background:#1e293b;border:1px solid #334155;padding:20px;border-radius:16px;margin:12px;max-width:900px} input,select{padding:10px;margin:4px;background:#0f172a;border:1px solid #334155;border-radius:8px;color:white} .btn{padding:10px 16px;background:#22c55e;color:black;border:none;border-radius:10px;font-weight:800;cursor:pointer}</style>
</head><body>
<div class="card"><h2>OX<span style="color:#22c55e">ITEM</span> V10 Config - {{username}} - Recuadros Grandes</h2>
<form id="adminAuth"><input id="adminUser" value="admin"><input id="adminPass" type="password" placeholder="OXITEM" value="OXITEM"><button class="btn" type="submit">Autenticar admin/OXITEM</button></form>
<div id="configArea" style="display:none"><h3 style="color:#22c55e">Bomba y Válvula</h3><div><label>Bomba <select id="bombaPulg"><option value="0.5" selected>1/2\" 25L/min proto</option><option value="1">1\" 80L/min</option></select></label> <label>Válv ppal <select id="valvPpalPulg"><option value="0.5">1/2\"</option><option value="1" selected>1\"</option></select></label></div><h3 style="color:#22c55e">Sectores ({{finca.sectores}})</h3><div id="sectoresConfig"></div><button class="btn" onclick="guardar()">💾 Guardar V10</button><span id="msg"></span></div></div>
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
   const sec=fincaData.sectores_config[i]||{planta:'paleta',cant_sensores:1,valvula_pulgadas:'1',flow_present:false,flow_pulgadas:'no'};
   const div=document.createElement('div'); div.className='card'; div.style='border-left:4px solid #22c55e';
   div.innerHTML=`<b>Sector ${i}</b><br>Planta: <select id="planta_${i}">${Object.entries(plantas).map(([k,p])=>`<option value="${k}" ${k===sec.planta?'selected':''}>${p.emoji} ${p.nombre}</option>`).join('')}</select> Sensores: <input id="cant_${i}" type="number" value="${sec.cant_sensores}" style="width:50px"> Válv: <select id="valv_${i}"><option value="1" selected>1"</option><option value="0.75">3/4"</option><option value="0.5">1/2"</option></select><br>Flow? <select id="flowPres_${i}"><option value="false" ${!sec.flow_present?'selected':''}>NO solo estimado</option><option value="true" ${sec.flow_present?'selected':''}>SÍ dual</option></select>`;
   cont.appendChild(div);
 }
}
async function guardar(){
 let sectores_config={};
 for(let i=1;i<=fincaData.sectores;i++){
   sectores_config[i]={planta:document.getElementById(`planta_${i}`).value,cant_sensores:parseInt(document.getElementById(`cant_${i}`).value),valvula_pulgadas:document.getElementById(`valv_${i}`).value,flow_present:document.getElementById(`flowPres_${i}`).value==='true',flow_pulgadas:'no'};
 }
 const payload={finca:'{{username}}',bomba_pulgadas:document.getElementById('bombaPulg').value,valvula_ppal_pulgadas:document.getElementById('valvPpalPulg').value,sectores_config:sectores_config};
 const r=await fetch('/api/config_terreno',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
 const j=await r.json(); document.getElementById('msg').innerText=j.ok?'✅ Guardado V10!':'Error';
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
            session['user']='admin'; return redirect('/dashboard')
        if u in db["users"] and db["users"][u]["password"]==p:
            session['user']=u; return redirect('/dashboard')
        for ku in db["users"]:
            if ku.lower()==u.lower() and db["users"][ku]["password"]==p:
                session['user']=ku; return redirect('/dashboard')
        err=f"Usuario '{u}' no existe. Registrados: {', '.join(db['users'].keys()) or 'ninguno'}"
    return render_template_string(LOGIN_HTML, error=err, users_count=users_count)

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method=='POST':
        u=request.form.get('username','').strip().replace(' ','_')
        p=request.form.get('password','').strip()
        if not u or len(u)<3: return "Usuario min 3",400
        if u.lower() in [k.lower() for k in db["users"]] or u.lower()=='admin': return f"Usuario {u} ya existe",400
        plantas_sel=request.form.getlist('plantas') or ['paleta']
        try:
            largo=int(request.form.get('largo',10)); ancho=int(request.form.get('ancho',10)); sectores=int(request.form.get('sectores',1))
        except: largo=10; ancho=10; sectores=1
        bomba_p=request.form.get('bomba_pulgadas','0.5'); valv_p=request.form.get('valvula_ppal_pulgadas','1')
        finca={"ubicacion":request.form.get('ubicacion','Villa Krause, San Juan'),"largo":largo,"ancho":ancho,"m2":largo*ancho,"sectores":sectores,"bomba_pulgadas":bomba_p,"bomba_lpm":BOMBA_CAUDAL.get(bomba_p,25),"valvula_ppal_pulgadas":valv_p,"plantas":plantas_sel,"sectores_config":{str(i):{"planta":plantas_sel[(i-1)%len(plantas_sel)],"cant_sensores":1,"valvula_pulgadas":"1","flow_present":False,"flow_pulgadas":"no"} for i in range(1,sectores+1)}}
        db["users"][u]={"password":p,"finca":finca}
        save_db(db)
        for i in range(1, sectores+1):
            actuadores_data[f"{u}_s{i}"]={"bomba":0,"valvula":0,"start_time":None,"litros_flow":0,"litros_estimado":0,"tiempo_acum":0}
        log(f"NUEVA FINCA V10 {u} {finca['m2']}m2")
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
        lista="".join([f"<div class='card'><b>{u}</b> {db['users'][u]['finca']['ubicacion']} <a href='/dashboard?finca={u}' style='color:#22c55e'>Ver</a></div>" for u in db["users"]]) or "No hay fincas"
        return f"<body style='background:#0a0f1c;color:white;font-family:system-ui;padding:20px'><h1>OXITEM V10 ADMIN {len(db['users'])} fincas</h1>{lista}<br><a href='/register' style='color:#22c55e'>+ Crear</a> <a href='/logout'>Salir</a></body>"
    finca_user=request.args.get('finca', user)
    finca=db["users"].get(finca_user,{}).get('finca',{})
    if not finca: return redirect('/register')
    return render_template_string(DASHBOARD_HTML, username=finca_user, finca=finca)

@app.route('/config_terreno')
def config_terreno():
    if 'user' not in session: return redirect('/login')
    finca_user=request.args.get('finca', session['user'])
    finca=db["users"].get(finca_user,{}).get('finca',{})
    if not finca: return f"Finca {finca_user} no existe",404
    return render_template_string(CONFIG_HTML, username=finca_user, finca=finca, finca_json=json.dumps(finca), plantas_json=json.dumps(PLANTAS))

@app.route('/api/admin_auth', methods=['POST'])
def admin_auth():
    d=request.get_json(silent=True) or {}
    if d.get('user','').strip().lower()=='admin' and d.get('pass','').strip()=='OXITEM': return {"ok":True}
    return {"ok":False},401

@app.route('/api/config_terreno', methods=['POST'])
def api_config():
    try:
        d=request.get_json(); finca_name=d.get('finca','').strip()
        if finca_name not in db["users"]: return {"error":"No existe"},404
        finca=db["users"][finca_name]["finca"]
        finca["bomba_pulgadas"]=d.get('bomba_pulgadas', finca["bomba_pulgadas"])
        finca["bomba_lpm"]=BOMBA_CAUDAL.get(finca["bomba_pulgadas"],25)
        finca["valvula_ppal_pulgadas"]=d.get('valvula_ppal_pulgadas', finca["valvula_ppal_pulgadas"])
        finca["sectores_config"]=d.get('sectores_config', finca["sectores_config"])
        for sid in finca["sectores_config"]:
            ak=f"{finca_name}_s{sid}"
            if ak not in actuadores_data: actuadores_data[ak]={"bomba":0,"valvula":0,"start_time":None,"litros_flow":0,"litros_estimado":0,"tiempo_acum":0}
        save_db(db)
        log(f"CONFIG V10 {finca_name}")
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
            historico.append({"ts":j['ts'],"humedad":float(j.get('humedad',0)),"finca":finca_id,"sector":sector_id})
            if len(historico)>500: historico.pop(0)
            log(f"RX {finca_id} S{sector_id} H{j.get('humedad')}% T{j.get('temperatura')} pH{j.get('ph')} N{j.get('nitrogeno')} P{j.get('fosforo')} K{j.get('potasio')}")
            finca_cfg=db["users"].get(finca_id,{}).get('finca',{})
            sec_cfg=finca_cfg.get('sectores_config',{}).get(sector_id,{})
            planta=PLANTAS.get(sec_cfg.get('planta','paleta'), PLANTAS["paleta"])
            hum=float(j.get('humedad',0))
            ak=f"{finca_id}_s{sector_id}"
            if ak not in actuadores_data: actuadores_data[ak]={"bomba":0,"valvula":0,"start_time":None,"litros_flow":0,"litros_estimado":0,"tiempo_acum":0}
            act=actuadores_data[ak]
            bomba_lpm=finca_cfg.get('bomba_lpm',25)
            # AUTO RIEGO - Si humedad baja prende bomba y valvula juntos
            if hum < planta["on"] and hum>0 and act["bomba"]==0:
                act["bomba"]=1; act["valvula"]=1; act["start_time"]=time.time()
                log(f"AUTO ON {finca_id} S{sector_id} {hum}%<{planta['on']}% -> BOMBA+VALV ON")
            elif hum >= planta["off"] and act["bomba"]==1:
                if act["start_time"]:
                    dur=time.time()-act["start_time"]
                    act["litros_estimado"]+=dur * bomba_lpm / 60.0
                    act["tiempo_acum"]+=dur
                act["bomba"]=0; act["valvula"]=0; act["start_time"]=None
                log(f"AUTO OFF {finca_id} S{sector_id}")
        if j.get('tipo') in ['valvula_flow','bomba_flow']:
            for ak in actuadores_data:
                if ak.startswith(f"{finca_id}_s{sector_id}"):
                    actuadores_data[ak]["litros_flow"]+=float(j.get('litros_flow',0))
        return {"ok":True}
    except Exception as e:
        return {"ok":False,"error":str(e)},500

@app.route('/api/estado')
def estado():
    try:
        finca_id=request.args.get('finca','default').strip()
        if finca_id=='default' and 'user' in session and session['user']!='admin':
            finca_id=session['user']
        finca_cfg=db["users"].get(finca_id,{}).get('finca',{})
        if not finca_cfg:
            return jsonify({"error":f"Finca {finca_id} no existe","users":list(db["users"].keys()),"sectores":{},"consumo":{"total_litros_flow":0,"total_litros_estimado":0,"diferencia":0,"alerta":"Sin finca"},"historico":[],"logs":logs[-10:],"reporte":"Sin finca","clima":{"temp":31,"hum":28,"viento":14,"desc":"Sin finca","riego_recomendado":"Crea finca","flow_info":"-","ubicacion":finca_id},"ultimo_temp":0,"ultimo_ph":0,"ultimo_ec":0,"ultimo_n":0,"ultimo_p":0,"ultimo_k":0,"ultimo_nota":"","finca_id":finca_id,"finca_sectores":0,"sensores_total":0,"actuadores":{}})
        sectores_cfg=finca_cfg.get('sectores_config',{})
        sectores_info={}; total_flow=0; total_est=0; reporte=""; ultimo_temp=0; ultimo_ph=0; ultimo_ec=0; ultimo_n=0; ultimo_p=0; ultimo_k=0; ultimo_nota=""
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
            if ak not in actuadores_data: actuadores_data[ak]={"bomba":0,"valvula":0,"start_time":None,"litros_flow":0,"litros_estimado":0,"tiempo_acum":0}
            act=actuadores_data[ak]
            tiempo_hoy=act["tiempo_acum"] + (time.time()-act["start_time"] if act.get("start_time") else 0)
            planta=PLANTAS.get(scfg.get('planta','paleta'), PLANTAS["paleta"])
            if not hums: estado_suelo="Sin datos sensor"
            elif hum_prom>=80: estado_suelo="SATURADO"
            elif hum_prom>=60: estado_suelo="ÓPTIMO"
            elif hum_prom>=40: estado_suelo="ESTRÉS"
            elif hum_prom>=20: estado_suelo="MARCHITEZ"
            else: estado_suelo="SECO - Sensor al aire? 0% = 3% RAW"
            sectores_info[sid]={"planta":scfg.get('planta','paleta'),"planta_nombre":planta["nombre"],"emoji":planta["emoji"],"color":planta["color"],"cant_sensores":scfg.get('cant_sensores',1),"valvula_pulgadas":scfg.get('valvula_pulgadas','1'),"flow_present":scfg.get('flow_present',False),"flow_pulgadas":scfg.get('flow_pulgadas','no'),"flow_model":FLOW_SPECS.get(scfg.get('flow_pulgadas','no'), FLOW_SPECS["no"])["modelo"],"humedad_prom":hum_prom,"temp":temp,"ph":ph,"ec":ec,"n":n,"p":p,"k":k,"temp_ideal":planta["temp"],"ph_ideal":planta["ph"],"n_ideal":planta["n"],"p_ideal":planta["p"],"k_ideal":planta["k"],"umbral_on":planta["on"],"umbral_off":planta["off"],"bomba_estado":act["bomba"],"valvula_estado":act["valvula"],"litros_flow":act["litros_flow"],"litros_estimado":act["litros_estimado"],"tiempo_hoy":tiempo_hoy,"sensores_activos":len(sensores_sector),"ultimo_hace":f"{int(time.time()-sensores_sorted[-1]['ts'])}s" if sensores_sorted else "nunca","estado_suelo":estado_suelo,"id_ejemplo":f"{finca_id}_s{sid}_d1"}
            total_flow+=act["litros_flow"]; total_est+=act["litros_estimado"]
            reporte+=f"● Sector {sid} {planta['emoji']} {planta['nombre']} ({scfg.get('cant_sensores')} sens, válv {scfg.get('valvula_pulgadas')}\"): Hum {hum_prom:.1f}% {estado_suelo} ON<{planta['on']}% OFF>={planta['off']}% Bomba {'ON' if act['bomba'] else 'OFF'} Válv {'OPEN' if act['valvula'] else 'CLOSED'} Temp {temp}°C pH {ph} N {n} P {p} K {k} Consumo {act['litros_flow']:.1f}L flow / {act['litros_estimado']:.1f}L est. Tiempo {(tiempo_hoy/60):.1f}min\n\n"
        dif=abs(total_flow-total_est)/total_est*100 if total_est>0 else 0
        alerta="Sin riego" if total_est==0 and total_flow==0 else ("✅ OK" if dif<=20 else "⚠️ Fuga >20%")
        clima={"temp":31,"hum":28,"viento":14,"desc":"Soleado San Juan - Radiación alta","riego_recomendado":"Riego normal OXITEM - Evitar 12-16h por calor extremo SJ","flow_info":f"Bomba {finca_cfg.get('bomba_pulgadas','0.5')}\" {finca_cfg.get('bomba_lpm',25)}L/min - YF-S201 1/2\" 450p/L","ubicacion":finca_cfg.get('ubicacion','Villa Krause')}
        hist_filtrado=[h for h in historico if h.get('finca')==finca_id]
        return jsonify({"finca_id":finca_id,"finca_sectores":finca_cfg.get('sectores',0),"sensores_total":len(sensores_data),"sensores":sensores_data,"actuadores":actuadores_data,"historico":hist_filtrado[-20:],"logs":logs[-20:],"sectores":sectores_info,"consumo":{"total_litros_flow":total_flow,"total_litros_estimado":total_est,"diferencia":round(dif,1),"alerta":alerta},"reporte":reporte or "Sin sectores","ultimo_temp":ultimo_temp,"ultimo_ph":ultimo_ph,"ultimo_ec":ultimo_ec,"ultimo_n":ultimo_n,"ultimo_p":ultimo_p,"ultimo_k":ultimo_k,"ultimo_nota":ultimo_nota,"clima":clima})
    except Exception as e:
        import traceback
        return jsonify({"error":str(e),"trace":traceback.format_exc(),"sectores":{},"consumo":{"total_litros_flow":0,"total_litros_estimado":0,"diferencia":0,"alerta":f"Error {e}"},"historico":[],"logs":logs[-10:],"reporte":f"Error: {e}","clima":{"temp":0,"hum":0,"viento":0,"desc":f"Error {e}","riego_recomendado":"Error","flow_info":"Error","ubicacion":"Error"},"ultimo_temp":0,"ultimo_ph":0,"ultimo_ec":0,"ultimo_n":0,"ultimo_p":0,"ultimo_k":0}),500

@app.route('/api/comando', methods=['POST'])
def comando():
    try:
        d=request.get_json(force=True)
        finca=d.get('finca','default').strip()
        dev=d.get('device','')
        est=int(d.get('estado',0))
        sector=str(d.get('sector','')).strip()
        log(f"CMD {finca} {dev} sec={sector} est={est}")
        if 'bomba_principal' in dev:
            for k in list(actuadores_data.keys()):
                if k.startswith(finca+"_s"):
                    if est==1 and actuadores_data[k]["bomba"]==0:
                        actuadores_data[k]["bomba"]=1; actuadores_data[k]["start_time"]=time.time()
                        actuadores_data[k]["valvula"]=1
                    elif est==0:
                        if actuadores_data[k]["start_time"]:
                            dur=time.time()-actuadores_data[k]["start_time"]
                            bomba_lpm=db["users"].get(finca,{}).get('finca',{}).get('bomba_lpm',25)
                            actuadores_data[k]["litros_estimado"]+=dur * bomba_lpm / 60.0
                            actuadores_data[k]["tiempo_acum"]+=dur
                        actuadores_data[k]["bomba"]=0; actuadores_data[k]["valvula"]=0; actuadores_data[k]["start_time"]=None
        elif dev=='valvula':
            for k in list(actuadores_data.keys()):
                if k.startswith(finca+"_s"):
                    actuadores_data[k]["valvula"]=est
                    if est==1 and actuadores_data[k]["bomba"]==0:
                        actuadores_data[k]["bomba"]=1; actuadores_data[k]["start_time"]=time.time()
                    elif est==0 and actuadores_data[k]["bomba"]==1:
                        # Si cierro todas valvulas, apago bomba tambien
                        if all(actuadores_data[kk]["valvula"]==0 for kk in actuadores_data if kk.startswith(finca+"_s") and kk!=k):
                            pass # dejamos bomba prendida si hay otras valvulas abiertas
        elif sector:
            ak=f"{finca}_s{sector}"
            if ak not in actuadores_data:
                actuadores_data[ak]={"bomba":0,"valvula":0,"start_time":None,"litros_flow":0,"litros_estimado":0,"tiempo_acum":0}
            if 'valvula' in dev:
                actuadores_data[ak]["valvula"]=est
                if est==1 and actuadores_data[ak]["bomba"]==0:
                    actuadores_data[ak]["bomba"]=1; actuadores_data[ak]["start_time"]=time.time()
                    log(f"BOMBA S{sector} ON por valvula S{sector} OPEN - Debe prender bomba fisica")
                elif est==0:
                    # Cierra valvula, si no hay otras valvulas abiertas, apaga bomba
                    otras_abiertas=any(actuadores_data[kk]["valvula"]==1 for kk in actuadores_data if kk.startswith(finca+"_s") and kk!=ak)
                    if not otras_abiertas and actuadores_data[ak]["start_time"]:
                        dur=time.time()-actuadores_data[ak]["start_time"]
                        bomba_lpm=db["users"].get(finca,{}).get('finca',{}).get('bomba_lpm',25)
                        actuadores_data[ak]["litros_estimado"]+=dur * bomba_lpm / 60.0
                        actuadores_data[ak]["tiempo_acum"]+=dur
                        actuadores_data[ak]["start_time"]=None
                        actuadores_data[ak]["bomba"]=0
                    elif not otras_abiertas:
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
        finca_id=request.args.get('finca','default').strip()
        sector_id=request.args.get('sector','1').strip()
        if sector_id=='0':
            # Bomba principal: prende si algun sector tiene bomba ON o valvula ON
            alguna_on=any((v["bomba"]==1 or v["valvula"]==1) for k,v in actuadores_data.items() if k.startswith(finca_id+"_s"))
            return jsonify({"bomba": alguna_on, "bomba_principal": int(alguna_on), "valvula": False, "valvula_sector": False, "finca":finca_id, "sector":0})
        ak=f"{finca_id}_s{sector_id}"
        act=actuadores_data.get(ak, {"bomba":0,"valvula":0,"litros_flow":0,"litros_estimado":0})
        finca_cfg=db["users"].get(finca_id,{}).get('finca',{})
        sec_cfg=finca_cfg.get('sectores_config',{}).get(str(sector_id),{})
        planta=PLANTAS.get(sec_cfg.get('planta','paleta'), PLANTAS["paleta"])
        return jsonify({"bomba": bool(act["bomba"]), "valvula": bool(act["valvula"]), "bomba_principal": act["bomba"], "valvula_sector": act["valvula"], "finca":finca_id, "sector":int(sector_id) if sector_id.isdigit() else sector_id, "umbral_on":planta["on"], "umbral_off":planta["off"], "planta":planta["nombre"]})
    except Exception as e:
        return jsonify({"bomba":False,"valvula":False,"error":str(e)}),500

@app.route('/api/debug')
def debug():
    return jsonify({"db_file":DB_FILE,"users":list(db["users"].keys()),"sensores_keys":list(sensores_data.keys())[:20],"sensores_total":len(sensores_data),"actuadores":actuadores_data,"historico_len":len(historico),"logs":logs[-20:]})

if __name__=='__main__':
    app.run(host='0.0.0.0',port=5000)

