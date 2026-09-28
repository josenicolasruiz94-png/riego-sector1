"""
OXITEM V7 PRO - DASHBOARD PROFESIONAL AGROTECH
Nombre: OXITEM - Sistema Inteligente de Riego Villa Krause
Estetica: Dark mode pro, tarjetas con color por cultivo, consumo dual agua
"""
from flask import Flask, request, jsonify, render_template_string, session, redirect
from flask_cors import CORS
import time, json, os
from datetime import datetime

app = Flask(__name__)
app.secret_key = "oxitem_v7_pro_2026_villa_krause"
CORS(app)

DB_FILE = "/tmp/fincas_db_v7_oxitem.json"
def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE,'r') as f: return json.load(f)
        except: pass
    return {"users": {}}
def save_db(db):
    try:
        with open(DB_FILE,'w') as f: json.dump(db,f)
    except: pass

db = load_db()
sensores_data = {}
actuadores_data = {}
historico = []
logs = []
consumo_historico = []

FLOW_SPECS = {
    "0.5": {"modelo": "YF-S201 1/2\"", "ppl": 450, "k": 7.5, "rango": "1-30 L/min"},
    "1_fs400": {"modelo": "FS400A 1\"", "ppl": 360, "k": 6.0, "rango": "1-60 L/min"},
    "1_dn25": {"modelo": "YF-DN25 1\"", "ppl": 450, "k": 7.5, "rango": "10-100 L/min"},
}
BOMBA_CAUDAL = {"0.5":25,"0.75":45,"1":80,"1.25":120,"1.5":180}

PLANTAS = {
    "tomate": {"nombre": "Tomate", "emoji":"🍅", "on":60, "off":80, "grupo":"Huerta", "color":"#ef4444", "hum":"70-80%", "ph":"5.5-6.8", "temp":"18-27°C", "n":"150-200", "p":"50-80", "k":"250-350", "nota":"Muy demandante de K en floración"},
    "lechuga": {"nombre": "Lechuga", "emoji":"🥬", "on":60, "off":75, "grupo":"Huerta", "color":"#22c55e", "hum":"60-75%", "ph":"6.0-7.0", "temp":"15-22°C", "n":"120-150", "p":"30-50", "k":"150-200", "nota":"Media sombra obligatoria verano SJ"},
    "pimiento": {"nombre": "Pimiento", "emoji":"🌶️", "on":28, "off":45, "grupo":"Huerta", "color":"#f97316", "hum":"60-75%", "ph":"5.5-6.5", "temp":"20-28°C", "n":"150", "p":"50", "k":"200", "nota":""},
    "uva": {"nombre": "Uva Vid", "emoji":"🍇", "on":40, "off":60, "grupo":"Frutal SJ", "color":"#8b5cf6", "hum":"40-60%", "ph":"6.0-7.5", "temp":"15-30°C", "n":"80-120", "p":"40-60", "k":"150-250", "nota":"Riego deficitario mejora azúcar - Emblemático SJ"},
    "olivo": {"nombre": "Olivo", "emoji":"🫒", "on":30, "off":50, "grupo":"Frutal SJ", "color":"#84cc16", "hum":"30-50%", "ph":"6.0-8.0", "temp":"15-30°C", "n":"60-100", "p":"20-40", "k":"100-200", "nota":"Tolerante sequía, odia encharque"},
    "menta": {"nombre": "Menta", "emoji":"🌿", "on":75, "off":85, "grupo":"Aromáticas", "color":"#10b981", "hum":"75-85%", "ph":"6.0-7.0", "temp":"15-25°C", "n":"150", "p":"50", "k":"150", "nota":"Invasiva"},
    "ruda": {"nombre": "Ruda", "emoji":"☘️", "on":40, "off":55, "grupo":"Aromáticas", "color":"#65a30d", "hum":"40-55%", "ph":"6.0-8.0", "temp":"18-28°C", "n":"50-80", "p":"20-30", "k":"80-120", "nota":"Autóctona"},
    "romero": {"nombre": "Romero", "emoji":"🌾", "on":30, "off":50, "grupo":"Aromáticas", "color":"#16a34a", "hum":"30-50%", "ph":"5.5-7.0", "temp":"15-28°C", "n":"50", "p":"20", "k":"100", "nota":"Si lo regás mucho se muere"},
    "frutilla": {"nombre": "Frutilla", "emoji":"🍓", "on":65, "off":75, "grupo":"Frutales", "color":"#f43f5e", "hum":"65-75%", "ph":"5.5-6.5", "temp":"15-24°C", "n":"100", "p":"70", "k":"200", "nota":"pH ácido fundamental"},
    "calanchoe": {"nombre": "Calanchoe", "emoji":"🌵", "on":30, "off":45, "grupo":"Suculenta", "color":"#06b6d4", "hum":"30-45%", "ph":"6.0-7.0", "temp":"15-25°C", "n":"50", "p":"20", "k":"80", "nota":""},
    "rosa": {"nombre": "Rosa", "emoji":"🌹", "on":60, "off":70, "grupo":"Flor", "color":"#ec4899", "hum":"60-70%", "ph":"6.0-6.8", "temp":"15-25°C", "n":"150", "p":"60", "k":"200", "nota":""},
}

def log(msg):
    ts=datetime.now().strftime("%H:%M:%S")
    logs.append(f"{ts} - {msg}")
    if len(logs)>200: logs.pop(0)

LOGIN_HTML = """
<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>OXITEM - Login</title>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;500;700;900&display=swap" rel="stylesheet">
<style>
*{font-family:'Outfit',system-ui} body{margin:0;background:#0a0f1c;min-height:100vh;display:flex;align-items:center;justify-content:center;position:relative;overflow:hidden}
.bg{position:absolute;inset:0;background:radial-gradient(600px at 20% 20%,rgba(34,197,94,0.15),transparent),radial-gradient(800px at 80% 80%,rgba(16,185,129,0.12),transparent),#0a0f1c}
.card{background:rgba(255,255,255,0.06);backdrop-filter:blur(20px);border:1px solid rgba(255,255,255,0.1);padding:40px;border-radius:24px;width:380px;position:relative;z-index:1;box-shadow:0 20px 60px rgba(0,0,0,0.5)}
.logo{font-size:42px;font-weight:900;letter-spacing:-1px;color:white} .logo span{color:#22c55e}
.sub{color:#94a3b8;font-size:13px;margin-top:6px;letter-spacing:0.5px}
input{width:100%;padding:14px 16px;margin:10px 0;background:rgba(255,255,255,0.07);border:1px solid rgba(255,255,255,0.12);border-radius:12px;color:white;box-sizing:border-box;outline:none;transition:0.2s} input:focus{border-color:#22c55e;background:rgba(255,255,255,0.1)}
.btn{width:100%;padding:14px;background:linear-gradient(135deg,#22c55e,#16a34a);color:black;border:none;border-radius:12px;font-weight:800;font-size:15px;cursor:pointer;margin-top:12px;letter-spacing:0.5px;transition:0.2s} .btn:hover{transform:translateY(-1px);box-shadow:0 10px 20px rgba(34,197,94,0.3)}
.link{color:#22c55e;text-align:center;display:block;margin-top:18px;font-size:13px;text-decoration:none;font-weight:500}
.badge{display:inline-block;background:rgba(34,197,94,0.15);color:#22c55e;padding:4px 10px;border-radius:20px;font-size:10px;font-weight:800;margin-top:20px;letter-spacing:0.5px}
</style></head><body>
<div class="bg"></div>
<div class="card">
<div class="logo">OX<span>ITEM</span></div>
<div class="sub">SISTEMA INTELIGENTE DE RIEGO • VILLA KRAUSE • SAN JUAN</div>
<form method="POST" action="/login" style="margin-top:24px">
<input name="username" placeholder="Usuario de finca" required>
<input name="password" type="password" placeholder="Contraseña" required>
<button class="btn">INGRESAR A MI FINCA →</button>
</form>
<a class="link" href="/register">¿Primera vez? Crear finca nueva</a>
{% if error %}<div style="color:#f87171;font-size:12px;margin-top:12px;background:rgba(248,113,113,0.1);padding:8px;border-radius:8px">{{error}}</div>{% endif %}
<div class="badge">● ADMIN CONFIG: admin / OXITEM</div>
<div style="color:#475569;font-size:10px;margin-top:16px;text-align:center">V7 PRO • 0% aire / 100% agua • Caudalímetro dual 1/2\" + 1\"</div>
</div></body></html>
"""

REGISTER_HTML = """
<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>OXITEM - Nueva Finca</title>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;500;700;900&display=swap" rel="stylesheet">
<style>
*{font-family:'Outfit',system-ui;box-sizing:border-box} body{margin:0;background:#0f172a;min-height:100vh;padding:20px}
.card{background:#1e293b;border:1px solid #334155;padding:28px;border-radius:20px;max-width:700px;margin:0 auto;color:white}
h2{margin:0 0 8px;font-weight:900;letter-spacing:-0.5px} h3{color:#22c55e;font-size:14px;letter-spacing:1px;margin:24px 0 12px}
input,select{width:100%;padding:12px;background:#0f172a;border:1px solid #334155;border-radius:10px;color:white;margin:6px 0} .grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.plant-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;max-height:320px;overflow:auto;background:#0f172a;padding:14px;border-radius:12px;border:1px solid #334155}
.plant-grid label{display:flex;align-items:center;gap:8px;font-size:13px;padding:6px 8px;border-radius:8px;cursor:pointer;transition:0.2s} .plant-grid label:hover{background:#1e293b}
.btn{width:100%;padding:14px;background:linear-gradient(135deg,#22c55e,#16a34a);color:black;border:none;border-radius:12px;font-weight:800;cursor:pointer;margin-top:20px}
.logo{font-weight:900;font-size:28px} .logo span{color:#22c55e}
</style></head><body>
<div class="card">
<div class="logo">OX<span>ITEM</span> <span style="font-size:12px;color:#94a3b8;font-weight:500">NUEVA FINCA</span></div>
<form method="POST" action="/register">
<h3>1. ACCESO</h3>
<div class="grid"><input name="username" placeholder="Usuario finca (ej: finca_gonzalez)" required><input name="password" type="password" placeholder="Contraseña" required></div>
<h3>2. TERRENO</h3>
<input name="ubicacion" placeholder="Ubicación - Ej: Villa Krause, Rawson, San Juan" required>
<div class="grid"><input name="largo" type="number" placeholder="Largo (m)" required><input name="ancho" type="number" placeholder="Ancho (m)" required></div>
<div class="grid"><input name="sectores" type="number" min="1" max="12" placeholder="Sectores (ej: 3)" required>
<select name="bomba_pulgadas"><option value="0.5">Bomba 1/2\" - 25 L/min (prototipo)</option><option value="0.75">Bomba 3/4\" - 45 L/min</option><option value="1" selected>Bomba 1\" - 80 L/min (recomendado)</option><option value="1.25">Bomba 1 1/4\" - 120 L/min</option></select></div>
<select name="valvula_ppal_pulgadas"><option value="0.5">Válvula principal 1/2\"</option><option value="0.75">Válvula principal 3/4\"</option><option value="1" selected>Válvula principal 1\"</option></select>
<h3>3. CULTIVOS QUE TENÉS (tildá todos)</h3>
<div class="plant-grid">
{% for key, pl in plantas.items() %}
<label><input type="checkbox" name="plantas" value="{{key}}"> {{pl.emoji}} {{pl.nombre}} <span style="color:#64748b;font-size:11px">{{pl.hum}}</span></label>
{% endfor %}
</div>
<button class="btn">CREAR FINCA Y ENTRAR A OXITEM →</button>
</form>
</div></body></html>
"""

DASHBOARD_HTML = """
<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>OXITEM - {{username}}</title>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;500;700;900&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
*{font-family:'Outfit',system-ui;box-sizing:border-box} body{margin:0;background:#0a0f1c;color:#e2e8f0}
.header{background:linear-gradient(180deg,#0f172a 0%,#0a0f1c 100%);border-bottom:1px solid #1e293b;padding:18px 24px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:10;backdrop-filter:blur(10px)}
.logo{font-weight:900;font-size:24px;letter-spacing:-0.5px;color:white} .logo span{color:#22c55e}
.badge{padding:6px 12px;border-radius:20px;font-size:11px;font-weight:800;letter-spacing:0.5px}
.card{background:linear-gradient(180deg,#1e293b 0%,#172030 100%);border:1px solid #2a3a52;border-radius:18px;padding:18px;margin:12px;box-shadow:0 8px 24px rgba(0,0,0,0.3);transition:0.2s}
.card:hover{border-color:#334155;transform:translateY(-1px)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:0;padding:12px}
.val{font-size:32px;font-weight:900;letter-spacing:-1px} .small{font-size:11px;color:#94a3b8;letter-spacing:0.3px}
.btn{padding:10px 16px;border-radius:10px;border:none;font-weight:700;cursor:pointer;font-size:13px;transition:0.2s}
.btn-dark{background:#0f172a;color:white;border:1px solid #334155} .btn-green{background:linear-gradient(135deg,#22c55e,#16a34a);color:black}
.plant-dot{width:10px;height:10px;border-radius:50%;display:inline-block;margin-right:6px}
.consumo-bar{height:8px;background:#0f172a;border-radius:10px;overflow:hidden;margin-top:8px}
.consumo-fill{height:100%;background:linear-gradient(90deg,#22c55e,#06b6d4);transition:width 0.5s}
.log{background:#0f172a;border:1px solid #1e293b;color:#86efac;padding:12px;border-radius:12px;font-family:monospace;font-size:11px;max-height:200px;overflow:auto}
.tag{display:inline-block;padding:3px 8px;border-radius:20px;font-size:10px;font-weight:700;margin:2px;background:#0f172a;border:1px solid #334155;color:#94a3b8}
</style></head><body>
<div class="header">
<div>
<div class="logo">OX<span>ITEM</span> <span style="font-size:11px;color:#64748b;font-weight:500;letter-spacing:1px">PRO V7</span></div>
<div style="font-size:12px;color:#94a3b8;margin-top:2px">{{finca.ubicacion}} • {{finca.largo}}x{{finca.ancho}}m • {{finca.m2}}m² • {{finca.sectores}} sectores • Bomba {{finca.bomba_pulgadas}}" {{finca.bomba_lpm}}L/min</div>
</div>
<div style="display:flex;gap:8px;align-items:center">
<a href="/config_terreno" class="btn btn-green">⚙️ Configurar Terreno</a>
<a href="/logout" class="btn btn-dark">Salir</a>
</div>
</div>

<div class="card" style="background:linear-gradient(135deg,rgba(34,197,94,0.15),rgba(6,182,212,0.12));border-color:rgba(34,197,94,0.3)">
<div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:12px">
<div><b style="letter-spacing:0.5px">💧 CONSUMO DUAL OXITEM</b><div class="small">Flowmeter 1/2\" prototipo + Estimado por tiempo bomba • Detección fugas</div></div>
<div id="consumoResumen" style="font-size:13px;text-align:right"></div>
</div>
<div class="consumo-bar"><div id="consumoFill" class="consumo-fill" style="width:35%"></div></div>
</div>

<div id="sectoresContainer" class="grid"></div>

<div style="display:grid;grid-template-columns:2fr 1fr;gap:0;padding:0 12px">
<div class="card"><canvas id="cHum" height="120"></canvas><div class="small" style="margin-top:8px">Línea verde punteada = Capacidad de Campo 80% (objetivo, no 100% saturado)</div></div>
<div class="card">
<b style="letter-spacing:0.5px">CONTROL & CLIMA SAN JUAN</b><br>
<div style="margin:12px 0;display:flex;gap:8px"><button class="btn btn-dark" onclick="cmdGlobal(1)">BOMBA ON</button><button class="btn btn-dark" onclick="cmdGlobal(0)">OFF</button></div>
<div id="clima" style="background:#0f172a;padding:12px;border-radius:12px;font-size:12px;border:1px solid #1e293b">Cargando clima...</div>
<div style="margin-top:12px" class="small">Flowmeter: YF-S201 1/2\" 450p/L prototipo → 1\" FS400A/DN25 final. Tiempo x caudal bomba en paralelo.</div>
</div>
</div>

<div class="card" style="background:linear-gradient(180deg,#0f172a,#0a0f1c);border-color:#1e293b">
<b style="color:#22c55e;letter-spacing:1px">📋 REPORTE AGRONÓMICO OXITEM POR SECTOR</b>
<div id="rep" style="font-size:12px;white-space:pre-wrap;margin-top:10px;line-height:1.6;color:#cbd5e1"></div>
</div>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:0;padding:0 12px">
<div class="card"><canvas id="cOtros" height="90"></canvas></div>
<div class="card"><b class="small" style="letter-spacing:1px">LOGS SISTEMA OXITEM</b><div id="log" class="log" style="margin-top:8px"></div></div>
</div>

<script>
let ch;
async function init(){
 ch=new Chart(document.getElementById('cHum'),{type:'line',data:{labels:[],[STRIPPED] VWC 0% aire / 100% agua',data:[],[STRIPPED] Cap Campo 80% objetivo',data:[],[STRIPPED] Riego ON',data:[],[STRIPPED]
 cOtros=new Chart(document.getElementById('cOtros'),{type:'bar',data:{labels:['Temp',[STRIPPED] x10','EC/10','N','P','K/10'],datasets:[{label:'Sensores',data:[0,[STRIPPED] backgroundColor:['#f59e0b','#ec4899','#06b6d4','#22c55e','#8b5cf6','#f97316']}]},options:{plugins:{legend:{display:false}},scales:{y:{display:false},x:{grid:{color:'#1e293b'}}}}});
 load(); setInterval(load,4000);
}
async function load(){
 const r=await fetch('/api/estado?finca={{username}}'); const j=await r.json();
 document.getElementById('consumoResumen').innerHTML=`Total: <b>${j.consumo.total_litros_flow.toFixed(1)} L</b> flow / <b>${j.consumo.total_litros_estimado.toFixed(1)} L</b> est. • Hoy: ${j.consumo.total_litros_flow.toFixed(1)} L • Dif: ${j.consumo.diferencia}% <span style="color:${j.consumo.diferencia>20?'#f87171':'#22c55e'}">${j.consumo.alerta}</span>`;
 document.getElementById('consumoFill').style.width=Math.min(100,j.consumo.total_litros_flow/10)+'%';
 const cont=document.getElementById('sectoresContainer'); cont.innerHTML='';
 Object.entries(j.sectores).forEach(([sid, sec])=>{
   const div=document.createElement('div'); div.className='card'; div.style.borderLeft=`4px solid ${sec.color}`;
   const estadoColor=sec.humedad_prom < sec.umbral_on ? '#f87171' : sec.humedad_prom >= sec.umbral_off ? '#22c55e' : '#fbbf24';
   div.innerHTML=`<div style="display:flex;justify-content:space-between"><div class="small" style="font-weight:700;letter-spacing:0.5px"><span class="plant-dot" style="background:${sec.color}"></span>SECTOR ${sid} • ${sec.planta_nombre.toUpperCase()} • ${sec.cant_sensores} sensores</div><div class="badge" style="background:${estadoColor}20;color:${estadoColor};border:1px solid ${estadoColor}40">${sec.bomba_estado?'BOMBA ON':'OFF'} • ${sec.valvula_estado?'OPEN':'CLOSED'}</div></div>
   <div class="val" style="color:${estadoColor}">${sec.humedad_prom.toFixed(1)}<span style="font-size:16px">% VWC</span></div>
   <div class="small">ON <${sec.umbral_on}% • OFF ≥${sec.umbral_off}% • Válv ${sec.valvula_pulgadas}" • Flow ${sec.flow_present?sec.flow_model+' ✔':'NO (solo est.)'}</div>
   <div style="margin-top:10px;display:flex;justify-content:space-between;font-size:11px"><span>💧 ${sec.litros_flow.toFixed(1)} L flow</span><span>${sec.litros_estimado.toFixed(1)} L est.</span><span>⏱ ${(sec.tiempo_hoy/60).toFixed(1)} min</span></div>
   <div class="consumo-bar"><div class="consumo-fill" style="width:${Math.min(100,sec.humedad_prom)}%;background:${sec.color}"></div></div>
   <div class="small" style="margin-top:6px">${sec.sensores_activos} sensores activos • último hace ${sec.ultimo_hace}</div>`;
   cont.appendChild(div);
 });
 ch.data.labels=j.historico.map(h=>new Date(h.ts*1000).toLocaleTimeString());
 ch.data.datasets[0].data=j.historico.map(h=>h.humedad);
 ch.data.datasets[1].data=j.historico.map(()=>80);
 ch.data.datasets[2].data=j.historico.map(h=>j.sectores[h.sector]?.umbral_on||30);
 ch.update();
 cOtros.data.datasets[0].data=[j.ultimo_temp||20, (j.ultimo_ph||6.5)*10, (j.ultimo_ec||400)/10, j.ultimo_n||100, j.ultimo_p||50, (j.ultimo_k||150)/10];
 cOtros.update();
 document.getElementById('rep').innerText=j.reporte;
 document.getElementById('log').innerHTML=j.logs.slice(-12).reverse().map(l=>`<div>${l}</div>`).join('');
 document.getElementById('clima').innerHTML=`<b>🌤️ San Juan ${j.clima.temp}°C</b> • Hum ${j.clima.hum}% • Viento ${j.clima.viento}km/h<br>${j.clima.desc}<br><span style="color:${j.clima.riego_recomendado.includes('No')?'#f87171':'#22c55e'}">${j.clima.riego_recomendado}</span><br><span class="small">Flow: ${j.clima.flow_info}</span>`;
}
async function cmdGlobal(e){ await fetch('/api/comando',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({finca:'{{username}}', device:'bomba_principal', estado:e})}); }
init();
</script></body></html>
"""

CONFIG_HTML = """
<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>OXITEM Config</title>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;500;700;900&display=swap" rel="stylesheet">
<style>*{font-family:'Outfit',system-ui;box-sizing:border-box} body{margin:0;background:#0a0f1c;color:#e2e8f0;padding:20px} .card{background:#1e293b;border:1px solid #334155;padding:20px;border-radius:16px;margin:12px;max-width:900px} input,select{padding:10px;margin:4px;background:#0f172a;border:1px solid #334155;border-radius:8px;color:white} .btn{padding:10px 16px;background:#22c55e;color:black;border:none;border-radius:10px;font-weight:800;cursor:pointer} .logo{font-weight:900;font-size:22px} .logo span{color:#22c55e}</style>
</head><body>
<div class="card">
<div class="logo">OX<span>ITEM</span> CONFIG TERRENO</div>
<p style="color:#94a3b8;font-size:13px">Solo admin OXITEM. Asigná planta por sector, sensores, pulgadas válvula y caudalímetro dual.</p>
<form id="adminAuth"><input id="adminUser" placeholder="admin" value="admin"><input id="adminPass" type="password" placeholder="OXITEM"><button class="btn" type="submit">Autenticar</button></form>
<div id="configArea" style="display:none">
<h3 style="color:#22c55e">Bomba y Válvula Principal</h3>
<div style="display:flex;gap:10px;flex-wrap:wrap">
<label>Bomba <select id="bombaPulg"><option value="0.5">1/2" 25L/min proto</option><option value="0.75">3/4" 45L/min</option><option value="1" selected>1" 80L/min final</option><option value="1.25">1 1/4" 120L/min</option></select></label>
<label>Válvula ppal <select id="valvPpalPulg"><option value="0.5">1/2"</option><option value="0.75">3/4"</option><option value="1" selected>1"</option></select></label>
</div>
<h3 style="color:#22c55e">Sectores ({{finca.sectores}})</h3>
<div id="sectoresConfig"></div>
<button class="btn" onclick="guardar()">💾 Guardar Config OXITEM</button><span id="msg" style="margin-left:12px"></span>
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
   const sec=fincaData.sectores_config[i]||{planta:'tomate',cant_sensores:5,valvula_pulgadas:'0.75',flow_present:true,flow_pulgadas:'0.5'};
   const div=document.createElement('div'); div.className='card'; div.style='border-left:3px solid #22c55e';
   div.innerHTML=`<b>Sector ${i}</b><br>
   Planta: <select id="planta_${i}">${Object.entries(plantas).map(([k,p])=>`<option value="${k}" ${k===sec.planta?'selected':''}>${p.emoji} ${p.nombre}</option>`).join('')}</select>
   Sensores: <input id="cant_${i}" type="number" value="${sec.cant_sensores}" style="width:60px">
   Válv sec: <select id="valv_${i}"><option value="0.5" ${sec.valvula_pulgadas==='0.5'?'selected':''}>1/2"</option><option value="0.75" ${sec.valvula_pulgadas==='0.75'?'selected':''}>3/4"</option><option value="1" ${sec.valvula_pulgadas==='1'?'selected':''}>1"</option></select><br>
   Flow? <select id="flowPres_${i}"><option value="false" ${!sec.flow_present?'selected':''}>NO (solo estimado bomba)</option><option value="true" ${sec.flow_present?'selected':''}>SÍ (dual)</option></select>
   Pulg flow: <select id="flowPulg_${i}"><option value="0.5" ${sec.flow_pulgadas==='0.5'?'selected':''}>1/2" YF-S201 proto 1-30L</option><option value="1_fs400" ${sec.flow_pulgadas==='1_fs400'?'selected':''}>1" FS400A 1-60L final</option><option value="1_dn25" ${sec.flow_pulgadas==='1_dn25'?'selected':''}>1" DN25 10-100L final</option></select>`;
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
 const j=await r.json(); document.getElementById('msg').innerText=j.ok?'✅ OXITEM Guardado!':'Error';
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
    if request.method=='POST':
        u=request.form.get('username'); p=request.form.get('password')
        if u=='admin' and p=='OXITEM':
            session['user']='admin'; session['role']='admin'; return redirect('/dashboard')
        if u in db["users"] and db["users"][u]["password"]==p:
            session['user']=u; session['role']='cliente'; return redirect('/dashboard')
        err="Usuario o contraseña incorrecto OXITEM"
    return render_template_string(LOGIN_HTML, error=err)

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method=='POST':
        u=request.form.get('username'); p=request.form.get('password')
        if not u or u in db["users"]: return "Usuario ya existe OXITEM",400
        plantas_sel=request.form.getlist('plantas') or ['tomate','lechuga']
        try: largo=int(request.form.get('largo',10)); ancho=int(request.form.get('ancho',10)); sectores=int(request.form.get('sectores',3))
        except: largo=10; ancho=10; sectores=3
        bomba_p=request.form.get('bomba_pulgadas','1'); valv_p=request.form.get('valvula_ppal_pulgadas','1')
        finca={"ubicacion":request.form.get('ubicacion','Villa Krause, San Juan'),"largo":largo,"ancho":ancho,"m2":largo*ancho,"sectores":sectores,"bomba_pulgadas":bomba_p,"bomba_lpm":BOMBA_CAUDAL.get(bomba_p,80),"valvula_ppal_pulgadas":valv_p,"plantas":plantas_sel,"sectores_config":{str(i):{"planta":plantas_sel[0],"cant_sensores":5,"valvula_pulgadas":"0.75","flow_present":True,"flow_pulgadas":"0.5"} for i in range(1,sectores+1)}}
        db["users"][u]={"password":p,"role":"cliente","finca":finca}
        save_db(db)
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
        lista="<br>".join([f"<div class='card'><b>{u}</b> - {db['users'][u]['finca']['ubicacion']} - {db['users'][u]['finca']['m2']}m2 - <a href='/dashboard?finca={u}' style='color:#22c55e'>Ver finca</a></div>" for u in db["users"]])
        return f"<body style='background:#0a0f1c;color:white;font-family:system-ui;padding:20px'><h1>OXITEM ADMIN - {len(db['users'])} fincas</h1>{lista}<br><a href='/logout' style='color:white'>Salir</a></body>"
    finca_user=request.args.get('finca', user)
    finca=get_finca(finca_user)
    if not finca: return redirect('/register')
    return render_template_string(DASHBOARD_HTML, username=finca_user, finca=finca)

@app.route('/config_terreno')
def config_terreno():
    if 'user' not in session: return redirect('/login')
    user=session['user']; finca_user=request.args.get('finca', user)
    finca=get_finca(finca_user)
    if not finca: return "Finca no existe",404
    return render_template_string(CONFIG_HTML, username=finca_user, finca=finca, finca_json=json.dumps(finca), plantas_json=json.dumps(PLANTAS))

@app.route('/api/admin_auth', methods=['POST'])
def admin_auth():
    d=request.get_json()
    if d.get('user')=='admin' and d.get('pass')=='OXITEM': return {"ok":True}
    return {"ok":False},401

@app.route('/api/config_terreno', methods=['POST'])
def api_config():
    d=request.get_json(); finca_name=d.get('finca')
    if finca_name not in db["users"]: return {"error":"no existe"},404
    finca=db["users"][finca_name]["finca"]
    finca["bomba_pulgadas"]=d.get('bomba_pulgadas', finca["bomba_pulgadas"])
    finca["bomba_lpm"]=BOMBA_CAUDAL.get(finca["bomba_pulgadas"],80)
    finca["valvula_ppal_pulgadas"]=d.get('valvula_ppal_pulgadas', finca["valvula_ppal_pulgadas"])
    finca["sectores_config"]=d.get('sectores_config', finca["sectores_config"])
    save_db(db); log(f"OXITEM CONFIG {finca_name} bomba {finca['bomba_pulgadas']}\" {finca['bomba_lpm']}L/min")
    return {"ok":True}

@app.route('/api/datos', methods=['POST'])
def datos():
    j=request.get_json()
    if not j: return {"error":"no json"},400
    finca_id=j.get('finca_id', j.get('finca','default'))
    sector_id=str(j.get('sector_id', j.get('sector','1')))
    key=f"{finca_id}_s{sector_id}_d{j.get('dispositivo_id','1')}_{j.get('tipo','sensor')}"
    j['ts']=time.time(); sensores_data[key]=j
    historico.append({"ts":j['ts'],"humedad":j.get('humedad',0),"finca":finca_id,"sector":sector_id})
    if len(historico)>300: historico.pop(0)
    pulsos=j.get('pulsos',0)
    if pulsos: log(f"OXITEM {finca_id} S{sector_id} {j.get('tipo')} {pulsos}p = {j.get('litros_flow',0)}L")
    else: log(f"OXITEM {finca_id} S{sector_id} Hum {j.get('humedad')}%")
    # Logica riego
    finca_cfg=db["users"].get(finca_id,{}).get('finca',{})
    sec_cfg=finca_cfg.get('sectores_config',{}).get(sector_id,{})
    planta_key=sec_cfg.get('planta','tomate')
    planta=PLANTAS.get(planta_key, PLANTAS["tomate"])
    hum=float(j.get('humedad',100)) if 'humedad' in j else 100
    act_key=f"{finca_id}_s{sector_id}"
    if act_key not in actuadores_data: actuadores_data[act_key]={"bomba":0,"valvula":0,"start_time":None,"litros_flow":0,"litros_estimado":0,"tiempo_acum":0}
    actuador=actuadores_data[act_key]
    bomba_lpm=finca_cfg.get('bomba_lpm',80)
    if 'humedad' in j:
        if hum < planta["on"] and actuador["bomba"]==0:
            actuador["bomba"]=1; actuador["valvula"]=1; actuador["start_time"]=time.time()
            log(f"OXITEM AUTO {finca_id} S{sector_id} {planta['nombre']} {hum}%<{planta['on']}% -> ON")
        elif hum >= planta["off"] and actuador["bomba"]==1:
            if actuador["start_time"]:
                dur=time.time()-actuador["start_time"]
                litros_est=dur * bomba_lpm / 60.0
                actuador["tiempo_acum"]+=dur; actuador["litros_estimado"]+=litros_est
                consumo_historico.append({"finca":finca_id,"sector":sector_id,"litros_estimado":litros_est,"tiempo":dur})
            actuador["bomba"]=0; actuador["valvula"]=0; actuador["start_time"]=None
            log(f"OXITEM AUTO {finca_id} S{sector_id} {hum}%>= {planta['off']}% -> OFF")
    if j.get('tipo') in ['valvula_flow','bomba_flow']:
        actuador["litros_flow"]+=j.get('litros_flow',0)
    return {"ok":True}

@app.route('/api/estado')
def estado():
    finca_id=request.args.get('finca','default')
    if finca_id=='default' and 'user' in session and session['user']!='admin': finca_id=session['user']
    finca_cfg=db["users"].get(finca_id,{}).get('finca',{})
    sectores_cfg=finca_cfg.get('sectores_config',{})
    sectores_info={}; total_flow=0; total_est=0; reporte=""; ultimo_temp=0; ultimo_ph=0; ultimo_ec=0; ultimo_n=0; ultimo_p=0; ultimo_k=0
    for sid, scfg in sectores_cfg.items():
        sensores_sector=[v for k,v in sensores_data.items() if k.startswith(f"{finca_id}_s{sid}_") and 'humedad' in v]
        hums=[s.get('humedad',0) for s in sensores_sector]
        hum_prom=sum(hums)/len(hums) if hums else 0
        if hums: ultimo_temp=sensores_sector[-1].get('temperatura',0); ultimo_ph=sensores_sector[-1].get('ph',0); ultimo_ec=sensores_sector[-1].get('conductividad',0); ultimo_n=sensores_sector[-1].get('nitrogeno',0); ultimo_p=sensores_sector[-1].get('fosforo',0); ultimo_k=sensores_sector[-1].get('potasio',0)
        act_key=f"{finca_id}_s{sid}"; actuador=actuadores_data.get(act_key, {"bomba":0,"valvula":0,"litros_flow":0,"litros_estimado":0,"tiempo_acum":0,"start_time":None})
        tiempo_hoy=actuador["tiempo_acum"] + (time.time()-actuador["start_time"] if actuador.get("start_time") else 0)
        planta_key=scfg.get('planta','tomate'); planta=PLANTAS.get(planta_key, PLANTAS["tomate"])
        sectores_info[sid]={"planta":planta_key,"planta_nombre":planta["nombre"],"color":planta["color"],"cant_sensores":scfg.get('cant_sensores',5),"valvula_pulgadas":scfg.get('valvula_pulgadas','0.75'),"flow_present":scfg.get('flow_present',False),"flow_pulgadas":scfg.get('flow_pulgadas','0.5'),"flow_model":FLOW_SPECS.get(scfg.get('flow_pulgadas','0.5'), FLOW_SPECS["0.5"])["modelo"],"humedad_prom":hum_prom,"umbral_on":planta["on"],"umbral_off":planta["off"],"bomba_estado":actuador["bomba"],"valvula_estado":actuador["valvula"],"litros_flow":actuador["litros_flow"],"litros_estimado":actuador["litros_estimado"],"tiempo_hoy":tiempo_hoy,"sensores_activos":len(sensores_sector),"ultimo_hace":f"{int(time.time()-sensores_sector[-1]['ts'])}s" if sensores_sector else "nunca"}
        total_flow+=actuador["litros_flow"]; total_est+=actuador["litros_estimado"]
        reporte+=f"● Sector {sid} {planta['emoji']} {planta['nombre']} ({scfg.get('cant_sensores')} sens, válv {scfg.get('valvula_pulgadas')}\" flow {'SI '+scfg.get('flow_pulgadas') if scfg.get('flow_present') else 'NO'}): {hum_prom:.1f}% VWC - ON<{planta['on']}% OFF≥{planta['off']}% - Bomba {'ON' if actuador['bomba'] else 'OFF'} - {actuador['litros_flow']:.1f}L flow / {actuador['litros_estimado']:.1f}L est. - {(tiempo_hoy/60):.1f}min hoy - pH {ultimo_ph} N{ultimo_n} P{ultimo_p} K{ultimo_k}\n"
    dif=abs(total_flow-total_est)/total_est*100 if total_est>0 else 0
    alerta="✅ Calibración OK" if dif<=20 else "⚠️ Fuga/filtro tapado >20%"
    clima={"temp":29,"hum":32,"viento":12,"desc":"Soleado San Juan - Ideal riego","riego_recomendado":"Riego normal OXITEM","flow_info":f"Flow 1/2\" {FLOW_SPECS['0.5']['rango']} proto / 1\" {FLOW_SPECS['1_fs400']['rango']} final"}
    return {"sensores":sensores_data,"actuadores":actuadores_data,"historico":[h for h in historico if h.get('finca')==finca_id][-30:],"logs":logs[-15:],"sectores":sectores_info,"consumo":{"total_litros_flow":total_flow,"total_litros_estimado":total_est,"diferencia":round(dif,1),"alerta":alerta},"reporte":reporte,"ultimo_temp":ultimo_temp,"ultimo_ph":ultimo_ph,"ultimo_ec":ultimo_ec,"ultimo_n":ultimo_n,"ultimo_p":ultimo_p,"ultimo_k":ultimo_k,"clima":clima}

@app.route('/api/comando', methods=['POST'])
def comando():
    d=request.get_json(); finca=d.get('finca','default'); dev=d.get('device'); est=d.get('estado',0)
    for key in actuadores_data:
        if key.startswith(finca):
            if 'bomba' in dev: actuadores_data[key]['bomba']=est
            if 'valvula' in dev: actuadores_data[key]['valvula']=est
    log(f"OXITEM MANUAL {finca} {dev}->{est}"); return {"ok":True}

@app.route('/api/riego')
def riego():
    finca_id=request.args.get('finca', request.args.get('finca_id','default'))
    sector_id=request.args.get('sector','1')
    if sector_id=='0':
        # Bomba principal: prende si algun sector tiene bomba ON
        alguna_on=any(v["bomba"]==1 for k,v in actuadores_data.items() if k.startswith(finca_id))
        return jsonify({"bomba": alguna_on, "bomba_principal": int(alguna_on), "valvula": False, "finca":finca_id, "sector":0})
    act_key=f"{finca_id}_s{sector_id}"
    actuador=actuadores_data.get(act_key, {"bomba":0,"valvula":0})
    finca_cfg=db["users"].get(finca_id,{}).get('finca',{})
    sec_cfg=finca_cfg.get('sectores_config',{}).get(str(sector_id),{})
    planta_key=sec_cfg.get('planta','tomate'); planta=PLANTAS.get(planta_key, PLANTAS["tomate"])
    return jsonify({"bomba": bool(actuador["bomba"]), "valvula": bool(actuador["valvula"]), "bomba_principal": actuador["bomba"], "valvula_sector": actuador["valvula"], "finca":finca_id, "sector":int(sector_id), "umbral_on":planta["on"], "umbral_off":planta["off"], "planta":planta_key})

if __name__=='__main__':
    app.run(host='0.0.0.0',port=5000)



