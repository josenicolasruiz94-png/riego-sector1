"""
OXITEM V11 MEJORADO - SOBRE V10, NO DESDE CERO
Mejoras pedidas:
1. Config Terreno pregunta: cuantas bombas en terreno, cuantas valvulas por cada sector, y que planta tiene cada sector (tomate del 1-4, lechuga del 5-10)
2. Muestra parametros ideales de la planta elegida en cada sector
3. Bomba y valvula independientes por ID: sector + valvula_id + bomba_id. No se prenden todas juntas
4. Recuadros grandes V10 mantenidos
"""
from flask import Flask, request, jsonify, render_template_string, session, redirect
from flask_cors import CORS
import time, json, os
from datetime import datetime

app = Flask(__name__)
app.secret_key = "oxitem_v11_mejorado_sector_valvula_bomba_id"
CORS(app)

DB_FILE = "fincas_db_v11.json"
def load_db():
    for f in ["fincas_db_v11.json","fincas_db_v10.json","fincas_db_v9.json"]:
        if os.path.exists(f):
            try:
                with open(f,'r') as fp: return json.load(fp)
            except: pass
    return {"users": {}}
def save_db(db):
    try:
        with open(DB_FILE,'w') as f: json.dump(db,f,indent=2)
    except: pass

db = load_db()
sensores_data = {}
actuadores_valvulas = {} # key: finca_s{sector}_v{valv_id} -> {valvula, start, litros_flow, litros_est, tiempo}
actuadores_bombas = {}   # key: finca_b{bomba_id} -> {bomba, start, litros}
historico = []
logs = []

BOMBA_CAUDAL = {"0.5":25,"0.75":45,"1":80,"1.25":120,"1.5":180}
FLOW_SPECS = {"0.5":{"modelo":"YF-S201 1/2\" 1-30L 450p/L"},"1_fs400":{"modelo":"FS400A 1\" 1-60L 360p/L"},"1_dn25":{"modelo":"DN25 1\" 10-100L 450p/L"},"no":{"modelo":"Sin flow (estimado)"}}

PLANTAS = {
    "tomate": {"nombre": "Tomate", "emoji":"🍅", "grupo":"Huerta", "on":60, "off":80, "color":"#ef4444", "hum":"70-80%", "hum_amb":"60-70%", "ph":"5.5-6.8", "temp":"18-27°C", "n":"150-200 ALTO", "p":"50-80 MEDIO", "k":"250-350 MUY ALTO", "nota":"Muy demandante de K en floración - ON<60% OFF>=80%"},
    "lechuga": {"nombre": "Lechuga", "emoji":"🥬", "grupo":"Huerta", "on":60, "off":75, "color":"#22c55e", "hum":"60-75%", "hum_amb":"50-70%", "ph":"6.0-7.0", "temp":"15-22°C", "n":"120-150 ALTO", "p":"30-50 BAJO", "k":"150-200 MEDIO", "nota":"Media sombra obligatoria verano SJ"},
    "paleta": {"nombre": "Paleta de Pintor", "emoji":"🎨", "grupo":"Interior", "on":60, "off":75, "color":"#f472b6", "hum":"60-75%", "hum_amb":"60-80%", "ph":"5.5-6.5", "temp":"18-26°C", "n":"80", "p":"30", "k":"100", "nota":""},
    "uva": {"nombre": "Uva Vid SJ", "emoji":"🍇", "grupo":"Frutal SJ", "on":40, "off":60, "color":"#7c3aed", "hum":"40-60%", "hum_amb":"40-60%", "ph":"6.0-7.5", "temp":"15-30°C", "n":"80-120", "p":"40-60", "k":"150-250", "nota":"Emblemático SJ - deficitario mejora azúcar"},
    "olivo": {"nombre": "Olivo", "emoji":"🫒", "grupo":"Frutal SJ", "on":30, "off":50, "color":"#65a30d", "hum":"30-50%", "hum_amb":"30-50%", "ph":"6.0-8.0", "temp":"15-30°C", "n":"60-100", "p":"20-40", "k":"100-200", "nota":"Tolerante sequía, odia encharque"},
    "menta": {"nombre": "Menta", "emoji":"🌿", "grupo":"Aromáticas", "on":75, "off":85, "color":"#10b981", "hum":"75-85%", "hum_amb":"60-80%", "ph":"6.0-7.0", "temp":"15-25°C", "n":"150", "p":"50", "k":"150", "nota":"Invasiva"},
    "ruda": {"nombre": "Ruda", "emoji":"☘️", "grupo":"Aromáticas", "on":40, "off":55, "color":"#65a30d", "hum":"40-55%", "hum_amb":"40-50%", "ph":"6.0-8.0", "temp":"18-28°C", "n":"50-80", "p":"20-30", "k":"80-120", "nota":"Autóctona"},
    "oregano": {"nombre": "Orégano", "emoji":"🌱", "grupo":"Aromáticas", "on":45, "off":60, "color":"#84cc16", "hum":"45-60%", "hum_amb":"40-60%", "ph":"6.0-8.0", "temp":"18-30°C", "n":"80", "p":"30", "k":"120", "nota":""},
    "romero": {"nombre": "Romero", "emoji":"🌾", "grupo":"Aromáticas", "on":30, "off":50, "color":"#16a34a", "hum":"30-50%", "ph":"5.5-7.0", "temp":"15-28°C", "n":"50", "p":"20", "k":"100", "nota":"Si lo regas mucho se muere"},
    "papa": {"nombre": "Papa", "emoji":"🥔", "grupo":"Huerta", "on":65, "off":80, "color":"#a16207", "hum":"65-80%", "hum_amb":"60-70%", "ph":"5.0-6.0", "temp":"15-22°C", "n":"100-150", "p":"80-100", "k":"300-400", "nota":""},
    "zanahoria": {"nombre": "Zanahoria", "emoji":"🥕", "grupo":"Huerta", "on":60, "off":70, "color":"#f97316", "hum":"60-70%", "ph":"6.0-6.8", "temp":"16-24°C", "n":"100", "p":"60", "k":"200", "nota":""},
    "frutilla": {"nombre": "Frutilla", "emoji":"🍓", "grupo":"Frutales", "on":65, "off":75, "color":"#f43f5e", "hum":"65-75%", "hum_amb":"60-75%", "ph":"5.5-6.5", "temp":"15-24°C", "n":"100", "p":"70", "k":"200", "nota":"pH ácido fundamental"},
}

def log(msg):
    ts=datetime.now().strftime("%H:%M:%S")
    logs.append(f"{ts} - {msg}")
    if len(logs)>400: logs.pop(0)
    print(msg)

LOGIN_HTML = """
<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OXITEM V11 Login</title>
<style>body{margin:0;background:#0a0f1c;color:white;font-family:system-ui;display:flex;align-items:center;justify-content:center;min-height:100vh}
.card{background:#1e293b;border:1px solid #334155;padding:32px;border-radius:20px;width:400px}
.logo{font-size:32px;font-weight:900} .logo span{color:#22c55e}
input{width:100%;padding:12px;margin:8px 0;background:#0f172a;border:1px solid #334155;border-radius:10px;color:white;box-sizing:border-box}
.btn{width:100%;padding:12px;background:#22c55e;color:black;border:none;border-radius:10px;font-weight:800;cursor:pointer}
</style></head><body>
<div class="card"><div class="logo">OX<span>ITEM</span> V11</div><div style="color:#94a3b8;font-size:11px">MEJORADO • VALVULA ID + BOMBA ID por sector</div>
<form method="POST" action="/login" style="margin-top:16px"><input name="username" placeholder="Usuario finca (finca_demo)" required><input name="password" type="password" placeholder="Contraseña" required><button class="btn">INGRESAR →</button></form>
<a href="/register" style="color:#22c55e;display:block;text-align:center;margin-top:12px;font-size:13px;text-decoration:none">Crear finca nueva</a>
{% if error %}<div style="color:#f87171;background:rgba(248,113,113,0.1);padding:8px;border-radius:8px;margin-top:10px;font-size:12px">{{error}}</div>{% endif %}
<div style="font-size:10px;color:#64748b;margin-top:10px">Usuarios: {{users_count}} | Admin: admin / OXITEM</div></div></body></html>
"""

REGISTER_HTML = """
<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OXITEM V11 Registro</title>
<style>body{margin:0;background:#0f172a;color:white;font-family:system-ui;padding:20px}
.card{background:#1e293b;border:1px solid #334155;padding:24px;border-radius:18px;max-width:850px;margin:0 auto}
input,select{width:100%;padding:10px;margin:5px 0;background:#0f172a;border:1px solid #334155;border-radius:8px;color:white;box-sizing:border-box}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.btn{width:100%;padding:12px;background:#22c55e;color:black;border:none;border-radius:10px;font-weight:800;cursor:pointer;margin-top:12px}
</style></head><body>
<div class="card"><h2>OX<span style="color:#22c55e">ITEM</span> V11 - Nueva Finca</h2><p style="color:#94a3b8;font-size:12px">Después en Config Terreno vas a definir cuántas válvulas por sector y cuántas bombas totales, y qué planta tiene cada sector (ej: S1-S4 tomate, S5-S10 lechuga)</p>
<form method="POST" action="/register">
<div class="grid"><input name="username" placeholder="Usuario sin espacios ej: finca_demo" required><input name="password" type="password" placeholder="Contraseña" required></div>
<input name="ubicacion" placeholder="Ubicación Ej: Villa Krause, Rawson, San Juan" required>
<div class="grid"><input name="largo" type="number" value="10" required><input name="ancho" type="number" value="10" required></div>
<div class="grid"><input name="sectores" type="number" min="1" max="20" value="2" required><input name="bombas" type="number" min="1" max="10" value="1" placeholder="Cuántas bombas en todo el terreno"></div>
<select name="bomba_pulgadas"><option value="0.5" selected>Bomba 1/2\" 25L/min proto</option><option value="1">1\" 80L/min</option><option value="1.25">1 1/4\" 120L/min</option></select>
<button class="btn">CREAR FINCA V11 → Config Terreno después</button>
</form></div></body></html>
"""

CONFIG_HTML = """
<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OXITEM V11 Config</title>
<style>body{margin:0;background:#0a0f1c;color:#e2e8f0;font-family:system-ui;padding:20px}
.card{background:#1e293b;border:1px solid #334155;padding:20px;border-radius:16px;margin:12px;max-width:1000px}
input,select{padding:10px;margin:4px;background:#0f172a;border:1px solid #334155;border-radius:8px;color:white}
.btn{padding:10px 16px;background:#22c55e;color:black;border:none;border-radius:10px;font-weight:800;cursor:pointer}
.sector-box{background:#0f172a;border:1px solid #1e293b;border-radius:14px;padding:16px;margin:12px 0;border-left:4px solid #22c55e}
.valv-box{background:#162032;border:1px dashed #334155;border-radius:10px;padding:10px;margin:8px 0}
</style></head><body>
<div class="card">
<h2>OX<span style="color:#22c55e">ITEM</span> V11 Config Terreno - {{username}} - Valvula ID + Bomba ID</h2>
<p style="color:#94a3b8;font-size:12px">Definí por sector: qué planta tiene (puede ser tomate S1-S4 y lechuga S5-S10), cuántos sensores, cuántas electroválvulas tiene ese sector, y cuántas bombas tiene todo el terreno. Cada electroválvula y cada bomba tiene su propio ID para activar independiente.</p>
<form id="adminAuth"><input id="adminUser" value="admin" placeholder="admin"><input id="adminPass" type="password" placeholder="OXITEM" value="OXITEM"><button class="btn" type="submit">Autenticar admin/OXITEM</button></form>
<div id="configArea" style="display:none">
<h3 style="color:#22c55e">Bombas de todo el terreno ({{finca.bombas_totales}} bombas)</h3>
<div id="bombasConfig"></div>
<h3 style="color:#22c55e">Sectores ({{finca.sectores}} sectores) - Para cada sector definí planta y cuántas válvulas tiene</h3>
<div id="sectoresConfig"></div>
<button class="btn" onclick="guardar()" style="margin-top:16px;padding:14px 24px;font-size:14px">💾 Guardar Config V11 Mejorada</button><span id="msg" style="margin-left:12px"></span>
</div>
</div>
<script>
let fincaData={{finca_json|safe}}; let plantas={{plantas_json|safe}};
document.getElementById('adminAuth').addEventListener('submit', async (e)=>{
 e.preventDefault();
 const r=await fetch('/api/admin_auth',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user:document.getElementById('adminUser').value, pass:document.getElementById('adminPass').value})});
 const j=await r.json(); if(j.ok){ document.getElementById('configArea').style.display='block'; loadConfig(); } else alert('Admin incorrecto');
});
function loadConfig(){
 // Bombas
 const bombasCont=document.getElementById('bombasConfig'); bombasCont.innerHTML='';
 const totalBombas=fincaData.bombas_totales||1;
 for(let b=1;b<=totalBombas;b++){
   const bCfg=(fincaData.bombas||[])[b-1]||{id:b,pulgadas:'0.5',flow_pulgadas:'no',sector_asignado:0};
   const div=document.createElement('div'); div.className='valv-box';
   div.innerHTML=`<b>Bomba ID ${b}</b> - Pulgadas: <select id="bomba_pulg_${b}"><option value="0.5" ${bCfg.pulgadas==='0.5'?'selected':''}>1/2" 25L/min</option><option value="1" ${bCfg.pulgadas==='1'?'selected':''}>1" 80L/min</option><option value="1.25" ${bCfg.pulgadas==='1.25'?'selected':''}>1 1/4" 120L/min</option></select> Flow: <select id="bomba_flow_${b}"><option value="no" ${bCfg.flow_pulgadas==='no'?'selected':''}>Sin flow (solo estimado)</option><option value="0.5" ${bCfg.flow_pulgadas==='0.5'?'selected':''}>YF-S201 1/2"</option><option value="1_fs400" ${bCfg.flow_pulgadas==='1_fs400'?'selected':''}>FS400A 1"</option></select> Sector que alimenta (0=todos): <input id="bomba_sector_${b}" type="number" value="${bCfg.sector_asignado||0}" style="width:60px"> - Codigo ESP: FINCA_ID="{{username}}" BOMBA_ID=${b}`;
   bombasCont.appendChild(div);
 }
 // Sectores
 const cont=document.getElementById('sectoresConfig'); cont.innerHTML='';
 for(let i=1;i<=fincaData.sectores;i++){
   const sec=fincaData.sectores_config[i]||{planta:'tomate',cant_sensores:1,cant_valvulas:1,valvulas:[{id:1,pulgadas:'1',flow_present:false}]};
   const div=document.createElement('div'); div.className='sector-box';
   let valvulasHtml='';
   const cantValv=sec.cant_valvulas|| (sec.valvulas?sec.valvulas.length:1);
   for(let v=1;v<=cantValv;v++){
     const vCfg=(sec.valvulas||[])[v-1]||{id:v,pulgadas:'1',flow_present:false,flow_pulgadas:'no'};
     valvulasHtml+=`<div class="valv-box"><b>Electroválvula ID ${v} del Sector ${i}</b> - Pulg: <select id="valv_pulg_${i}_${v}"><option value="0.5" ${vCfg.pulgadas==='0.5'?'selected':''}>1/2"</option><option value="0.75" ${vCfg.pulgadas==='0.75'?'selected':''}>3/4"</option><option value="1" ${vCfg.pulgadas==='1'?'selected':''}>1"</option></select> Flow? <select id="valv_flow_present_${i}_${v}"><option value="false" ${!vCfg.flow_present?'selected':''}>NO solo estimado</option><option value="true" ${vCfg.flow_present?'selected':''}>SÍ dual</option></select> <span style="font-size:10px;color:#64748b">Codigo ESP: FINCA_ID="{{username}}" SECTOR_ID=${i} VALVULA_ID=${v}</span></div>`;
   }
   div.innerHTML=`<b>Sector ${i}</b> - Qué planta tiene este sector? <select id="planta_${i}" style="min-width:160px">${Object.entries(plantas).map(([k,p])=>`<option value="${k}" ${k===sec.planta?'selected':''}>${p.emoji} ${p.nombre} ${p.hum} ON<${p.on}% OFF>=${p.off}%</option>`).join('')}</select> Sensores en este sector: <input id="cant_sens_${i}" type="number" min="1" max="20" value="${sec.cant_sensores||1}" style="width:50px"> Electroválvulas en este sector: <input id="cant_valv_${i}" type="number" min="1" max="10" value="${cantValv}" style="width:50px" onchange="loadConfig()"> <span style="font-size:10px;color:#94a3b8">Ej: S1-S4 tomate, S5-S10 lechuga</span><div style="margin-top:10px" id="valvs_${i}">${valvulasHtml}</div>`;
   cont.appendChild(div);
 }
 // Listener para cant valvulas
 for(let i=1;i<=fincaData.sectores;i++){
   const inp=document.getElementById(`cant_valv_${i}`);
   if(inp){ inp.addEventListener('change', ()=>{ 
     // Reconstruir solo ese sector
     const sec=fincaData.sectores_config[i]||{planta:'tomate',cant_sensores:1};
     sec.cant_valvulas=parseInt(inp.value);
     fincaData.sectores_config[i]=sec;
     loadConfig();
   }); }
 }
}
async function guardar(){
 let bombas=[];
 const totalBombas=fincaData.bombas_totales||1;
 for(let b=1;b<=totalBombas;b++){
   bombas.push({id:b,pulgadas:document.getElementById(`bomba_pulg_${b}`).value,flow_pulgadas:document.getElementById(`bomba_flow_${b}`).value,sector_asignado:parseInt(document.getElementById(`bomba_sector_${b}`).value||0)});
 }
 let sectores_config={};
 for(let i=1;i<=fincaData.sectores;i++){
   const cantValv=parseInt(document.getElementById(`cant_valv_${i}`).value||1);
   let valvulas=[];
   for(let v=1;v<=cantValv;v++){
     valvulas.push({id:v,pulgadas:document.getElementById(`valv_pulg_${i}_${v}`).value,flow_present:document.getElementById(`valv_flow_present_${i}_${v}`).value==='true',flow_pulgadas:'no'});
   }
   sectores_config[i]={planta:document.getElementById(`planta_${i}`).value,cant_sensores:parseInt(document.getElementById(`cant_sens_${i}`).value||1),cant_valvulas:cantValv,valvulas:valvulas};
 }
 const payload={finca:'{{username}}',bombas:bombas,sectores_config:sectores_config};
 const r=await fetch('/api/config_terreno',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
 const j=await r.json(); document.getElementById('msg').innerText=j.ok?'✅ Guardado V11! Cada válvula y bomba con su ID independiente':'Error '+JSON.stringify(j);
}
</script></body></html>
"""

DASHBOARD_HTML = """
<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OXITEM V11 - {{username}}</title>
<style>
body{margin:0;background:#080e1c;color:#e2e8f0;font-family:system-ui}
.header{background:#0f172a;border-bottom:1px solid #1e293b;padding:16px 24px;display:flex;justify-content:space-between;flex-wrap:wrap;gap:12px;position:sticky;top:0;z-index:10}
.logo{font-weight:900;font-size:24px;color:white} .logo span{color:#22c55e}
.card{background:#162032;border:1px solid #2a3a52;border-radius:20px;padding:24px;margin:16px;box-shadow:0 8px 24px rgba(0,0,0,0.3)}
.card-large{padding:28px;margin:20px;border-radius:24px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(400px,1fr));gap:20px;padding:16px}
.val{font-size:36px;font-weight:900} .small{font-size:12px;color:#94a3b8;line-height:1.4}
.btn{padding:10px 18px;border-radius:10px;border:none;font-weight:800;cursor:pointer;font-size:12px;margin:4px}
.btn-dark{background:#0f172a;color:white;border:1px solid #334155} .btn-green{background:linear-gradient(135deg,#22c55e,#16a34a);color:black} .btn-red{background:linear-gradient(135deg,#ef4444,#dc2626);color:white}
.badge{padding:6px 12px;border-radius:12px;font-size:11px;font-weight:800}
.log{background:#0f172a;border:1px solid #1e293b;color:#86efac;padding:12px;border-radius:12px;font-family:monospace;font-size:11px;max-height:260px;overflow:auto}
.kpi{font-size:13px;display:flex;justify-content:space-between;margin:4px 0}
.bar{height:10px;background:#0f172a;border-radius:10px;overflow:hidden;margin-top:8px} .fill{height:100%;background:linear-gradient(90deg,#22c55e,#06b6d4)}
canvas{width:100%!important;max-height:220px;background:#0f172a;border-radius:10px}
.data-row{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin:10px 0}
.data-box{background:#0f172a;border:1px solid #1e293b;border-radius:12px;padding:10px;text-align:center}
.data-box .label{font-size:10px;color:#64748b} .data-box .value{font-size:16px;font-weight:800}
.valv-card{background:#0f172a;border:1px solid #1e293b;border-radius:14px;padding:14px;margin:10px 0;border-left:4px solid #22c55e}
</style></head><body>
<div class="header">
<div><div class="logo">OX<span>ITEM</span> V11 <span style="font-size:11px;color:#64748b">MEJORADO • VALVULA ID + BOMBA ID</span></div><div class="small">{{finca.ubicacion}} • {{finca.largo}}x{{finca.ancho}}m {{finca.m2}}m² • {{finca.sectores}} sectores • {{finca.bombas_totales}} bombas • Bomba {{finca.bomba_pulgadas}}" {{finca.bomba_lpm}}L/min</div></div>
<div><a href="/config_terreno?finca={{username}}" style="background:#22c55e;color:black;padding:10px 16px;border-radius:10px;text-decoration:none;font-weight:800;font-size:13px">⚙️ Config Terreno: Valvulas por sector + Bombas + Planta por sector</a> <a href="/logout" style="color:#94a3b8;margin-left:8px">Salir</a></div>
</div>

<div class="card card-large" style="background:linear-gradient(135deg,rgba(34,197,94,0.12),rgba(6,182,212,0.08));border-color:rgba(34,197,94,0.3)">
<div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:16px"><div><b>💧 CONSUMO DUAL V11 - Con VALVULA ID y BOMBA ID independientes</b><div class="small">Cada válvula S1-V1, S1-V2, S2-V1 tiene su propio ID. Cada bomba B1, B2 tiene su ID. Se activan independientes, no todas juntas.</div></div><div id="consumoResumen" style="font-size:13px;text-align:right">Cargando...</div></div>
<div class="bar" style="height:12px;margin-top:12px"><div id="consumoFill" class="fill" style="width:15%"></div></div>
</div>

<div id="sectoresContainer" class="grid">Cargando sectores con válvulas ID...</div>

<div id="bombasContainer" class="grid" style="grid-template-columns:repeat(auto-fit,minmax(300px,1fr))"></div>

<div class="grid">
<div class="card card-large"><b>📈 HISTORIAL HUMEDAD VWC %</b><canvas id="cHum" width="600" height="240"></canvas><div id="humList" class="small" style="margin-top:12px;background:#0f172a;padding:10px;border-radius:10px;max-height:100px;overflow:auto"></div></div>
<div class="card card-large"><b>CONTROL & CLIMA SAN JUAN</b>
<div style="margin:12px 0;display:grid;grid-template-columns:1fr 1fr;gap:8px"><button class="btn btn-green" onclick="cmdGlobalBomba(1)">Todas Bombas ON</button><button class="btn btn-red" onclick="cmdGlobalBomba(0)">Todas OFF</button><button class="btn btn-green" onclick="cmdGlobalValv(1)">Todas Válv ON</button><button class="btn btn-red" onclick="cmdGlobalValv(0)">Todas OFF</button></div>
<div id="clima" style="background:#0f172a;padding:12px;border-radius:12px;font-size:12px;border:1px solid #1e293b">Cargando clima...</div>
<div style="margin-top:12px;background:#0f172a;padding:12px;border-radius:12px"><b class="small">MAPA FINCA</b><div style="margin-top:8px"><a href="https://www.google.com/maps/search/{{finca.ubicacion}}" target="_blank" style="color:#22c55e">📍 {{finca.ubicacion}} - Abrir en Maps →</a></div><div class="small" style="margin-top:8px">Cada ESP debe tener: FINCA_ID="{{username}}" SECTOR_ID=X VALVULA_ID=Y o BOMBA_ID=Z<br>Ej: S1-V1 = Sector 1 Valvula 1, B1 = Bomba 1 alimenta todos o sector asignado</div></div>
</div>
</div>

<div class="grid">
<div class="card card-large"><b>📊 NPK + pH + EC</b><div id="npkBars"></div><canvas id="cNPK" width="600" height="160"></canvas><div id="npkDetalle" class="small" style="margin-top:8px;background:#0f172a;padding:10px;border-radius:10px"></div></div>
<div class="card card-large"><b>📋 REPORTE AGRONÓMICO POR SECTOR Y VÁLVULA ID</b><div id="rep" style="font-size:11px;white-space:pre-wrap;max-height:400px;overflow:auto;background:#0f172a;padding:12px;border-radius:12px;margin-top:8px"></div></div>
</div>

<div class="card card-large"><b>LOGS</b><div id="log" class="log"></div></div>
<div class="card"><b class="small">DEBUG</b><div id="debug" class="small" style="font-family:monospace;white-space:pre-wrap;background:#0f172a;padding:10px;border-radius:8px"></div></div>

<script>
async function load(){
 try{
  const r=await fetch('/api/estado?finca={{username}}&t='+Date.now());
  const j=await r.json();
  if(j.error){ document.getElementById('debug').innerText=j.error; return; }
  
  document.getElementById('consumoResumen').innerHTML=`Flow ${(j.consumo.total_litros_flow||0).toFixed(1)}L / Est ${(j.consumo.total_litros_estimado||0).toFixed(1)}L • Dif ${j.consumo.diferencia}% ${j.consumo.alerta}<br><span class="small">${j.sensores_total} sensores • ${Object.keys(j.sectores||{}).length} sectores • ${j.bombas_total} bombas • ${j.valvulas_total} válvulas totales</span>`;
  document.getElementById('consumoFill').style.width=Math.min(100,(j.consumo.total_litros_estimado||0)/2)+'%';
  
  // Sectores con valvulas ID
  const cont=document.getElementById('sectoresContainer');
  cont.innerHTML='';
  Object.entries(j.sectores||{}).forEach(([sid, sec])=>{
    const estadoColor = sec.humedad_prom < sec.umbral_on ? '#f87171' : sec.humedad_prom >= sec.umbral_off ? '#22c55e' : '#fbbf24';
    const div=document.createElement('div'); div.className='card card-large'; div.style.borderLeft=`6px solid ${sec.color}`;
    let valvulasHtml='';
    (sec.valvulas||[]).forEach(v=>{
      const vAct = j.actuadores_valvulas[`${j.finca_id}_s${sid}_v${v.id}`] || {valvula:0,litros_flow:0,litros_estimado:0,tiempo_acum:0};
      valvulasHtml+=`<div class="valv-card" style="border-left-color:${vAct.valvula?'#22c55e':'#334155'}"><div style="display:flex;justify-content:space-between"><b>Electroválvula ID ${v.id} del Sector ${sid} (S${sid}-V${v.id})</b><span class="badge" style="background:${vAct.valvula?'#22c55e20':'#1e293b'};color:${vAct.valvula?'#22c55e':'#64748b'}">${vAct.valvula?'VÁLV OPEN':'CLOSED'} • ${v.pulgadas}"</span></div><div class="small">Codigo ESP: FINCA_ID="${j.finca_id}" SECTOR_ID=${sid} VALVULA_ID=${v.id} • Flow ${v.flow_present?'SÍ':'NO solo estimado'}</div><div style="margin-top:8px;display:flex;gap:6px"><button class="btn ${vAct.valvula?'btn-red':'btn-green'}" onclick="cmdValvId(${sid},${v.id},${vAct.valvula?0:1})">${vAct.valvula?'Cerrar V'+v.id:'Abrir V'+v.id+' ON'}</button><span class="small">💧 ${vAct.litros_flow.toFixed(1)}L flow / ${vAct.litros_estimado.toFixed(1)}L est. ⏱ ${(vAct.tiempo_acum/60).toFixed(1)}min</span></div></div>`;
    });
    div.innerHTML=`
      <div style="display:flex;justify-content:space-between;flex-wrap:wrap"><div style="font-weight:800;font-size:16px"><span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:${sec.color};margin-right:6px"></span>SECTOR ${sid} • ${sec.planta_nombre.toUpperCase()} ${sec.emoji} • ${sec.cant_sensores} sensores • ${sec.cant_valvulas} válvulas</div><div class="badge" style="background:${estadoColor}20;color:${estadoColor}">${sec.estado_suelo} • ${sec.humedad_prom.toFixed(1)}% VWC</div></div>
      <div class="val" style="color:${estadoColor};margin-top:8px">${sec.humedad_prom.toFixed(1)}<span style="font-size:14px">% VWC</span> <span style="font-size:12px;color:#94a3b8">ON&lt;${sec.umbral_on}% OFF&gt;=${sec.umbral_off}%</span></div>
      <div style="background:#0f172a;border-radius:12px;padding:12px;margin:12px 0"><b style="font-size:12px;color:#22c55e">PARÁMETROS IDEALES PARA ${sec.planta_nombre.toUpperCase()} ${sec.emoji} (para saber cuándo riega)</b><div class="data-row" style="margin-top:8px"><div class="data-box"><div class="label">HUM SUSTRATO IDEAL</div><div class="value" style="font-size:14px">${sec.hum_ideal}</div><div class="small">Actual ${sec.humedad_prom.toFixed(1)}%</div></div><div class="data-box"><div class="label">TEMP IDEAL</div><div class="value" style="font-size:14px">${sec.temp_ideal}</div><div class="small">Actual ${sec.temp}°C</div></div><div class="data-box"><div class="label">pH IDEAL</div><div class="value" style="font-size:14px">${sec.ph_ideal}</div><div class="small">Actual ${sec.ph}</div></div></div><div class="data-row"><div class="data-box"><div class="label">N IDEAL</div><div class="value" style="font-size:14px">${sec.n_ideal}</div><div class="small">Actual ${sec.n}ppm</div></div><div class="data-box"><div class="label">P IDEAL</div><div class="value" style="font-size:14px">${sec.p_ideal}</div><div class="small">Actual ${sec.p}ppm</div></div><div class="data-box"><div class="label">K IDEAL</div><div class="value" style="font-size:14px">${sec.k_ideal}</div><div class="small">Actual ${sec.k}ppm</div></div></div><div class="small" style="margin-top:8px">Nota: ${sec.nota} • Hum amb ideal ${sec.hum_amb_ideal} • EC ideal ${sec.ec_ideal||'-'}</div></div>
      <div style="margin-top:8px"><b class="small">VÁLVULAS DE ESTE SECTOR (cada una con su ID independiente)</b>${valvulasHtml}</div>
      <div class="small" style="margin-top:12px">${sec.sensores_activos} sensores activos • último hace ${sec.ultimo_hace} • Ejemplo ID: ${sec.id_ejemplo}</div>
    `;
    cont.appendChild(div);
  });
  
  // Bombas
  const bombasCont=document.getElementById('bombasContainer');
  bombasCont.innerHTML='';
  (j.bombas||[]).forEach(b=>{
    const bAct = j.actuadores_bombas[`${j.finca_id}_b${b.id}`] || {bomba:0,litros_flow:0,litros_estimado:0};
    const div=document.createElement('div'); div.className='card';
    div.style.borderLeft=`4px solid ${bAct.bomba?'#22c55e':'#334155'}`;
    div.innerHTML=`<b>Bomba ID ${b.id} (B${b.id})</b> • ${b.pulgadas}" • ${b.flow_model} • Sector asignado: ${b.sector_asignado==0?'Todos':b.sector_asignado}<br><span class="badge" style="background:${bAct.bomba?'#22c55e20':'#1e293b'};color:${bAct.bomba?'#22c55e':'#64748b'}">${bAct.bomba?'BOMBA ON':'OFF'}</span> 💧 ${bAct.litros_flow.toFixed(1)}L flow / ${bAct.litros_estimado.toFixed(1)}L est.<br><span class="small">Codigo ESP: FINCA_ID="${j.finca_id}" BOMBA_ID=${b.id} SECTOR_ASIGNADO=${b.sector_asignado} (0=todos)</span><br><div style="margin-top:8px"><button class="btn ${bAct.bomba?'btn-red':'btn-green'}" onclick="cmdBombaId(${b.id},${bAct.bomba?0:1})">${bAct.bomba?'Apagar B'+b.id:'Prender B'+b.id+' ON'}</button></div>`;
    bombasCont.appendChild(div);
  });
  
  // Grafico simple
  try{
    const canvas=document.getElementById('cHum'); const ctx=canvas.getContext('2d'); const hist=j.historico||[];
    ctx.clearRect(0,0,canvas.width,canvas.height); ctx.fillStyle='#0f172a'; ctx.fillRect(0,0,canvas.width,canvas.height);
    ctx.strokeStyle='#1e293b'; for(let y=0;y<canvas.height;y+=30){ ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(canvas.width,y); ctx.stroke(); }
    ctx.strokeStyle='#22c55e'; ctx.setLineDash([6,6]); ctx.beginPath(); ctx.moveTo(0,canvas.height*0.2); ctx.lineTo(canvas.width,canvas.height*0.2); ctx.stroke(); ctx.setLineDash([]);
    if(hist.length>1){ ctx.strokeStyle='#fbbf24'; ctx.lineWidth=3; ctx.beginPath(); hist.forEach((h,i)=>{ const x=(i/(hist.length-1))*canvas.width; const y=canvas.height - (h.humedad/100)*canvas.height; if(i===0) ctx.moveTo(x,y); else ctx.lineTo(x,y); }); ctx.stroke(); }
    document.getElementById('humList').innerText=hist.length?hist.map(h=>`${new Date(h.ts*1000).toLocaleTimeString()} S${h.sector} ${h.humedad}%`).join(' | '):'Sin datos';
  } catch(e){}
  
  document.getElementById('rep').innerText=j.reporte||'';
  document.getElementById('log').innerHTML=(j.logs||[]).slice(-20).reverse().map(l=>`<div>${l}</div>`).join('');
  document.getElementById('debug').innerText=`Finca ${j.finca_id} Sectores ${j.finca_sectores} Bombas ${j.bombas_total} Valvulas ${j.valvulas_total} Sensores ${j.sensores_total}`;
  document.getElementById('clima').innerHTML=`<b>🌤️ San Juan ${j.clima.temp}°C</b> • ${j.clima.hum}% hum amb • ${j.clima.viento}km/h<br>${j.clima.desc}<br><b style="color:#22c55e">${j.clima.riego_recomendado}</b>`;
 } catch(e){ document.getElementById('debug').innerText='Error: '+e; }
}
async function cmdGlobalBomba(e){ await fetch('/api/comando',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({finca:'{{username}}', device:'todas_bombas', estado:e})}); load(); }
async function cmdGlobalValv(e){ await fetch('/api/comando',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({finca:'{{username}}', device:'todas_valvulas', estado:e})}); load(); }
async function cmdValvId(sector, valvId, estado){ await fetch('/api/comando',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({finca:'{{username}}', device:'valvula_id', sector:sector, valvula_id:valvId, estado:estado})}); load(); }
async function cmdBombaId(bombaId, estado){ await fetch('/api/comando',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({finca:'{{username}}', device:'bomba_id', bomba_id:bombaId, estado:estado})}); load(); }
load(); setInterval(load,3000);
</script></body></html>
"""

CONFIG_HTML = """
<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OXITEM V11 Config</title>
<style>body{margin:0;background:#0a0f1c;color:#e2e8f0;font-family:system-ui;padding:20px}
.card{background:#1e293b;border:1px solid #334155;padding:20px;border-radius:16px;margin:12px;max-width:1000px}
input,select{padding:10px;margin:4px;background:#0f172a;border:1px solid #334155;border-radius:8px;color:white}
.btn{padding:10px 16px;background:#22c55e;color:black;border:none;border-radius:10px;font-weight:800;cursor:pointer}
.sector-box{background:#0f172a;border:1px solid #1e293b;border-radius:14px;padding:16px;margin:12px 0;border-left:4px solid #22c55e}
.valv-box{background:#162032;border:1px dashed #334155;border-radius:10px;padding:10px;margin:8px 0}
</style></head><body>
<div class="card">
<h2>OX<span style="color:#22c55e">ITEM</span> V11 Config Terreno - {{username}} - Valvula ID + Bomba ID</h2>
<p style="color:#94a3b8;font-size:12px">Definí por sector: qué planta tiene (puede ser tomate S1-S4 y lechuga S5-S10), cuántos sensores, cuántas electroválvulas tiene ese sector, y cuántas bombas tiene todo el terreno. Cada electroválvula y cada bomba tiene su propio ID para activar independiente.</p>
<form id="adminAuth"><input id="adminUser" value="admin" placeholder="admin"><input id="adminPass" type="password" placeholder="OXITEM" value="OXITEM"><button class="btn" type="submit">Autenticar admin/OXITEM</button></form>
<div id="configArea" style="display:none">
<h3 style="color:#22c55e">Bombas de todo el terreno ({{finca.bombas_totales}} bombas)</h3>
<div id="bombasConfig"></div>
<h3 style="color:#22c55e">Sectores ({{finca.sectores}} sectores) - Para cada sector definí planta y cuántas válvulas tiene</h3>
<div id="sectoresConfig"></div>
<button class="btn" onclick="guardar()" style="margin-top:16px;padding:14px 24px;font-size:14px">💾 Guardar Config V11 Mejorada</button><span id="msg" style="margin-left:12px"></span>
</div>
</div>
<script>
let fincaData={{finca_json|safe}}; let plantas={{plantas_json|safe}};
document.getElementById('adminAuth').addEventListener('submit', async (e)=>{
 e.preventDefault();
 const r=await fetch('/api/admin_auth',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user:document.getElementById('adminUser').value, pass:document.getElementById('adminPass').value})});
 const j=await r.json(); if(j.ok){ document.getElementById('configArea').style.display='block'; loadConfig(); } else alert('Admin incorrecto');
});
function loadConfig(){
 // Bombas
 const bombasCont=document.getElementById('bombasConfig'); bombasCont.innerHTML='';
 const totalBombas=fincaData.bombas_totales||1;
 for(let b=1;b<=totalBombas;b++){
   const bCfg=(fincaData.bombas||[])[b-1]||{id:b,pulgadas:'0.5',flow_pulgadas:'no',sector_asignado:0};
   const div=document.createElement('div'); div.className='valv-box';
   div.innerHTML=`<b>Bomba ID ${b}</b> - Pulgadas: <select id="bomba_pulg_${b}"><option value="0.5" ${bCfg.pulgadas==='0.5'?'selected':''}>1/2" 25L/min</option><option value="1" ${bCfg.pulgadas==='1'?'selected':''}>1" 80L/min</option><option value="1.25" ${bCfg.pulgadas==='1.25'?'selected':''}>1 1/4" 120L/min</option></select> Flow: <select id="bomba_flow_${b}"><option value="no" ${bCfg.flow_pulgadas==='no'?'selected':''}>Sin flow (solo estimado)</option><option value="0.5" ${bCfg.flow_pulgadas==='0.5'?'selected':''}>YF-S201 1/2"</option><option value="1_fs400" ${bCfg.flow_pulgadas==='1_fs400'?'selected':''}>FS400A 1"</option></select> Sector que alimenta (0=todos): <input id="bomba_sector_${b}" type="number" value="${bCfg.sector_asignado||0}" style="width:60px"> - Codigo ESP: FINCA_ID="{{username}}" BOMBA_ID=${b}`;
   bombasCont.appendChild(div);
 }
 // Sectores
 const cont=document.getElementById('sectoresConfig'); cont.innerHTML='';
 for(let i=1;i<=fincaData.sectores;i++){
   const sec=fincaData.sectores_config[i]||{planta:'tomate',cant_sensores:1,cant_valvulas:1,valvulas:[{id:1,pulgadas:'1',flow_present:false}]};
   const div=document.createElement('div'); div.className='sector-box';
   let valvulasHtml='';
   const cantValv=sec.cant_valvulas|| (sec.valvulas?sec.valvulas.length:1);
   for(let v=1;v<=cantValv;v++){
     const vCfg=(sec.valvulas||[])[v-1]||{id:v,pulgadas:'1',flow_present:false,flow_pulgadas:'no'};
     valvulasHtml+=`<div class="valv-box"><b>Electroválvula ID ${v} del Sector ${i}</b> - Pulg: <select id="valv_pulg_${i}_${v}"><option value="0.5" ${vCfg.pulgadas==='0.5'?'selected':''}>1/2"</option><option value="0.75" ${vCfg.pulgadas==='0.75'?'selected':''}>3/4"</option><option value="1" ${vCfg.pulgadas==='1'?'selected':''}>1"</option></select> Flow? <select id="valv_flow_present_${i}_${v}"><option value="false" ${!vCfg.flow_present?'selected':''}>NO solo estimado</option><option value="true" ${vCfg.flow_present?'selected':''}>SÍ dual</option></select> <span style="font-size:10px;color:#64748b">Codigo ESP: FINCA_ID="{{username}}" SECTOR_ID=${i} VALVULA_ID=${v}</span></div>`;
   }
   div.innerHTML=`<b>Sector ${i}</b> - Qué planta tiene este sector? <select id="planta_${i}" style="min-width:160px">${Object.entries(plantas).map(([k,p])=>`<option value="${k}" ${k===sec.planta?'selected':''}>${p.emoji} ${p.nombre} ${p.hum} ON<${p.on}% OFF>=${p.off}%</option>`).join('')}</select> Sensores en este sector: <input id="cant_sens_${i}" type="number" min="1" max="20" value="${sec.cant_sensores||1}" style="width:50px"> Electroválvulas en este sector: <input id="cant_valv_${i}" type="number" min="1" max="10" value="${cantValv}" style="width:50px" onchange="loadConfig()"> <span style="font-size:10px;color:#94a3b8">Ej: S1-S4 tomate, S5-S10 lechuga</span><div style="margin-top:10px" id="valvs_${i}">${valvulasHtml}</div>`;
   cont.appendChild(div);
 }
 // Listener para cant valvulas
 for(let i=1;i<=fincaData.sectores;i++){
   const inp=document.getElementById(`cant_valv_${i}`);
   if(inp){ inp.addEventListener('change', ()=>{ 
     // Reconstruir solo ese sector
     const sec=fincaData.sectores_config[i]||{planta:'tomate',cant_sensores:1};
     sec.cant_valvulas=parseInt(inp.value);
     fincaData.sectores_config[i]=sec;
     loadConfig();
   }); }
 }
}
async function guardar(){
 let bombas=[];
 const totalBombas=fincaData.bombas_totales||1;
 for(let b=1;b<=totalBombas;b++){
   bombas.push({id:b,pulgadas:document.getElementById(`bomba_pulg_${b}`).value,flow_pulgadas:document.getElementById(`bomba_flow_${b}`).value,sector_asignado:parseInt(document.getElementById(`bomba_sector_${b}`).value||0)});
 }
 let sectores_config={};
 for(let i=1;i<=fincaData.sectores;i++){
   const cantValv=parseInt(document.getElementById(`cant_valv_${i}`).value||1);
   let valvulas=[];
   for(let v=1;v<=cantValv;v++){
     valvulas.push({id:v,pulgadas:document.getElementById(`valv_pulg_${i}_${v}`).value,flow_present:document.getElementById(`valv_flow_present_${i}_${v}`).value==='true',flow_pulgadas:'no'});
   }
   sectores_config[i]={planta:document.getElementById(`planta_${i}`).value,cant_sensores:parseInt(document.getElementById(`cant_sens_${i}`).value||1),cant_valvulas:cantValv,valvulas:valvulas};
 }
 const payload={finca:'{{username}}',bombas:bombas,sectores_config:sectores_config};
 const r=await fetch('/api/config_terreno',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
 const j=await r.json(); document.getElementById('msg').innerText=j.ok?'✅ Guardado V11! Cada válvula y bomba con su ID independiente':'Error '+JSON.stringify(j);
}
</script></body></html>
"""

@app.route('/')
def idx():
    if 'user' in session: return redirect('/dashboard')
    return redirect('/login')

@app.route('/login', methods=['GET','POST'])
def login():
    err=None; users_count=len(db["users"])
    if request.method=='POST':
        u=request.form.get('username','').strip(); p=request.form.get('password','').strip()
        if u.lower()=='admin' and p=='OXITEM': session['user']='admin'; return redirect('/dashboard')
        if u in db["users"] and db["users"][u]["password"]==p: session['user']=u; return redirect('/dashboard')
        for ku in db["users"]:
            if ku.lower()==u.lower() and db["users"][ku]["password"]==p: session['user']=ku; return redirect('/dashboard')
        err=f"Usuario '{u}' no existe. Registrados: {', '.join(db['users'].keys()) or 'ninguno'}"
    return render_template_string(LOGIN_HTML, error=err, users_count=users_count)

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method=='POST':
        u=request.form.get('username','').strip().replace(' ','_'); p=request.form.get('password','').strip()
        if not u or len(u)<3: return "Usuario min 3",400
        if u.lower() in [k.lower() for k in db["users"]] or u.lower()=='admin': return f"Usuario {u} ya existe",400
        try:
            largo=int(request.form.get('largo',10)); ancho=int(request.form.get('ancho',10)); sectores=int(request.form.get('sectores',2)); bombas_totales=int(request.form.get('bombas',1))
        except: largo=10; ancho=10; sectores=2; bombas_totales=1
        bomba_p=request.form.get('bomba_pulgadas','0.5')
        finca={"ubicacion":request.form.get('ubicacion','Villa Krause, San Juan'),"largo":largo,"ancho":ancho,"m2":largo*ancho,"sectores":sectores,"bombas_totales":bombas_totales,"bomba_pulgadas":bomba_p,"bomba_lpm":BOMBA_CAUDAL.get(bomba_p,25),"bombas":[{"id":i+1,"pulgadas":bomba_p,"flow_pulgadas":"no","sector_asignado":0} for i in range(bombas_totales)],"sectores_config":{str(i):{"planta":"tomate","cant_sensores":1,"cant_valvulas":1,"valvulas":[{"id":1,"pulgadas":"1","flow_present":False,"flow_pulgadas":"no"}]} for i in range(1,sectores+1)}}
        db["users"][u]={"password":p,"finca":finca}
        save_db(db)
        # Inicializar actuadores
        for i in range(1, sectores+1):
            actuadores_valvulas[f"{u}_s{i}_v1"]={"valvula":0,"start_time":None,"litros_flow":0,"litros_estimado":0,"tiempo_acum":0}
        for b in range(1, bombas_totales+1):
            actuadores_bombas[f"{u}_b{b}"]={"bomba":0,"start_time":None,"litros_flow":0,"litros_estimado":0,"tiempo_acum":0}
        log(f"NUEVA FINCA V11 {u} {sectores} sec {bombas_totales} bombas")
        session['user']=u; return redirect('/dashboard')
    return render_template_string(REGISTER_HTML)

@app.route('/logout')
def logout():
    session.clear(); return redirect('/login')

@app.route('/dashboard')
def dashboard():
    if 'user' not in session: return redirect('/login')
    user=session['user']
    if user=='admin':
        lista="".join([f"<div style='background:#1e293b;border:1px solid #334155;padding:12px;border-radius:12px;margin:8px'><b>{u}</b> {db['users'][u]['finca']['ubicacion']} {db['users'][u]['finca']['sectores']} sectores {db['users'][u]['finca']['bombas_totales']} bombas <a href='/dashboard?finca={u}' style='color:#22c55e'>Ver</a></div>" for u in db["users"]]) or "No hay fincas"
        return f"<body style='background:#0a0f1c;color:white;font-family:system-ui;padding:20px'><h1>OXITEM V11 ADMIN {len(db['users'])} fincas</h1>{lista}<br><a href='/register' style='color:#22c55e'>+ Crear finca</a> <a href='/logout'>Salir</a></body>"
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
        bombas=d.get('bombas', finca.get('bombas',[]))
        sectores_config=d.get('sectores_config', finca.get('sectores_config',{}))
        finca["bombas"]=bombas
        finca["bombas_totales"]=len(bombas)
        finca["sectores_config"]=sectores_config
        finca["sectores"]=len(sectores_config)
        # Recalcular actuadores
        # Bombas
        for b in bombas:
            ak=f"{finca_name}_b{b['id']}"
            if ak not in actuadores_bombas: actuadores_bombas[ak]={"bomba":0,"start_time":None,"litros_flow":0,"litros_estimado":0,"tiempo_acum":0}
        # Valvulas
        for sid, scfg in sectores_config.items():
            for v in scfg.get('valvulas',[]):
                ak=f"{finca_name}_s{sid}_v{v['id']}"
                if ak not in actuadores_valvulas: actuadores_valvulas[ak]={"valvula":0,"start_time":None,"litros_flow":0,"litros_estimado":0,"tiempo_acum":0}
        save_db(db)
        log(f"CONFIG V11 {finca_name} {len(sectores_config)} sectores {len(bombas)} bombas")
        return {"ok":True}
    except Exception as e:
        return {"error":str(e)},500

@app.route('/api/datos', methods=['POST'])
def datos():
    try:
        j=request.get_json(force=True)
        finca_id=j.get('finca_id', j.get('finca','default')).strip()
        sector_id=str(j.get('sector_id', j.get('sector','1'))).strip()
        valvula_id=str(j.get('valvula_id', j.get('dispositivo_id','1'))).strip()
        bomba_id=str(j.get('bomba_id', j.get('dispositivo_id','1'))).strip()
        tipo=j.get('tipo','sensor')
        if tipo in ['valvula_flow','sensor']:
            key=f"{finca_id}_s{sector_id}_d{valvula_id}_{tipo}"
        elif tipo=='bomba_flow':
            key=f"{finca_id}_b{bomba_id}_d{bomba_id}_{tipo}"
        else:
            key=f"{finca_id}_s{sector_id}_d{valvula_id}_{tipo}"
        j['ts']=time.time()
        sensores_data[key]=j
        if 'humedad' in j:
            historico.append({"ts":j['ts'],"humedad":float(j.get('humedad',0)),"finca":finca_id,"sector":sector_id})
            if len(historico)>500: historico.pop(0)
            log(f"RX {finca_id} S{sector_id} H{j.get('humedad')}% T{j.get('temperatura')} pH{j.get('ph')} N{j.get('nitrogeno')}")
            # Auto riego por sector: si humedad < ON, prende TODAS las valvulas de ese sector y bomba asignada
            finca_cfg=db["users"].get(finca_id,{}).get('finca',{})
            sec_cfg=finca_cfg.get('sectores_config',{}).get(sector_id,{})
            planta=PLANTAS.get(sec_cfg.get('planta','tomate'), PLANTAS["tomate"])
            hum=float(j.get('humedad',0))
            if hum>0 and hum < planta["on"]:
                for v in sec_cfg.get('valvulas',[{"id":1}]):
                    ak=f"{finca_id}_s{sector_id}_v{v['id']}"
                    if ak not in actuadores_valvulas: actuadores_valvulas[ak]={"valvula":0,"start_time":None,"litros_flow":0,"litros_estimado":0,"tiempo_acum":0}
                    if actuadores_valvulas[ak]["valvula"]==0:
                        actuadores_valvulas[ak]["valvula"]=1
                        actuadores_valvulas[ak]["start_time"]=time.time()
                        log(f"AUTO ON {finca_id} S{sector_id} V{v['id']} {planta['nombre']} {hum}%<{planta['on']}%")
                # Prende bombas asignadas a este sector o todas si sector_asignado=0
                for b in finca_cfg.get('bombas',[{"id":1,"sector_asignado":0}]):
                    if b["sector_asignado"]==0 or str(b["sector_asignado"])==sector_id:
                        bak=f"{finca_id}_b{b['id']}"
                        if bak not in actuadores_bombas: actuadores_bombas[bak]={"bomba":0,"start_time":None,"litros_flow":0,"litros_estimado":0,"tiempo_acum":0}
                        if actuadores_bombas[bak]["bomba"]==0:
                            actuadores_bombas[bak]["bomba"]=1
                            actuadores_bombas[bak]["start_time"]=time.time()
            elif hum >= planta["off"]:
                for v in sec_cfg.get('valvulas',[{"id":1}]):
                    ak=f"{finca_id}_s{sector_id}_v{v['id']}"
                    if ak in actuadores_valvulas and actuadores_valvulas[ak]["valvula"]==1:
                        if actuadores_valvulas[ak]["start_time"]:
                            dur=time.time()-actuadores_valvulas[ak]["start_time"]
                            bomba_lpm=finca_cfg.get('bomba_lpm',25)
                            actuadores_valvulas[ak]["litros_estimado"]+=dur * bomba_lpm / 60.0
                            actuadores_valvulas[ak]["tiempo_acum"]+=dur
                        actuadores_valvulas[ak]["valvula"]=0
                        actuadores_valvulas[ak]["start_time"]=None
                        log(f"AUTO OFF {finca_id} S{sector_id} V{v['id']} {hum}%>= {planta['off']}%")
                # Si todas valvulas del sector cerradas, apaga bombas asignadas
                todas_cerradas=all(actuadores_valvulas.get(f"{finca_id}_s{sector_id}_v{v['id']}",{"valvula":0})["valvula"]==0 for v in sec_cfg.get('valvulas',[]))
                if todas_cerradas:
                    for b in finca_cfg.get('bombas',[]):
                        if b["sector_asignado"]==0 or str(b["sector_asignado"])==sector_id:
                            bak=f"{finca_id}_b{b['id']}"
                            if bak in actuadores_bombas and actuadores_bombas[bak]["bomba"]==1:
                                if actuadores_bombas[bak]["start_time"]:
                                    dur=time.time()-actuadores_bombas[bak]["start_time"]
                                    bomba_lpm=finca_cfg.get('bomba_lpm',25)
                                    actuadores_bombas[bak]["litros_estimado"]+=dur * bomba_lpm / 60.0
                                    actuadores_bombas[bak]["tiempo_acum"]+=dur
                                actuadores_bombas[bak]["bomba"]=0
                                actuadores_bombas[bak]["start_time"]=None
        if tipo=='valvula_flow':
            ak=f"{finca_id}_s{sector_id}_v{valvula_id}"
            if ak in actuadores_valvulas: actuadores_valvulas[ak]["litros_flow"]+=float(j.get('litros_flow',0))
        if tipo=='bomba_flow':
            ak=f"{finca_id}_b{bomba_id}"
            if ak in actuadores_bombas: actuadores_bombas[ak]["litros_flow"]+=float(j.get('litros_flow',0))
        return {"ok":True}
    except Exception as e:
        import traceback
        log(f"Error datos: {e}")
        return {"ok":False,"error":str(e),"trace":traceback.format_exc()},500

@app.route('/api/estado')
def estado():
    try:
        finca_id=request.args.get('finca','default').strip()
        if finca_id=='default' and 'user' in session and session['user']!='admin': finca_id=session['user']
        finca_cfg=db["users"].get(finca_id,{}).get('finca',{})
        if not finca_cfg:
            return jsonify({"error":f"Finca {finca_id} no existe","users":list(db["users"].keys()),"sectores":{},"bombas":[],"consumo":{"total_litros_flow":0,"total_litros_estimado":0,"diferencia":0,"alerta":"Sin finca"},"historico":[],"logs":logs[-10:],"reporte":"Sin finca","clima":{"temp":31,"hum":28,"viento":14,"desc":"Sin finca","riego_recomendado":"Crea finca","flow_info":"-","ubicacion":finca_id},"ultimo_temp":0,"ultimo_ph":0,"ultimo_ec":0,"ultimo_n":0,"ultimo_p":0,"ultimo_k":0,"finca_id":finca_id,"finca_sectores":0,"bombas_total":0,"valvulas_total":0,"sensores_total":0,"actuadores_valvulas":{},"actuadores_bombas":{}})
        sectores_cfg=finca_cfg.get('sectores_config',{})
        bombas_cfg=finca_cfg.get('bombas',[])
        sectores_info={}; total_flow=0; total_est=0; reporte=""; ultimo_temp=0; ultimo_ph=0; ultimo_ec=0; ultimo_n=0; ultimo_p=0; ultimo_k=0; valvulas_total=0
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
            planta=PLANTAS.get(scfg.get('planta','tomate'), PLANTAS["tomate"])
            valvulas_cfg=scfg.get('valvulas',[{"id":1,"pulgadas":"1","flow_present":False}])
            valvulas_total+=len(valvulas_cfg)
            # Calcular tiempo y consumo por valvula
            for v in valvulas_cfg:
                ak=f"{finca_id}_s{sid}_v{v['id']}"
                if ak not in actuadores_valvulas: actuadores_valvulas[ak]={"valvula":0,"start_time":None,"litros_flow":0,"litros_estimado":0,"tiempo_acum":0}
                act=actuadores_valvulas[ak]
                total_flow+=act["litros_flow"]; total_est+=act["litros_estimado"]
            if not hums: estado_suelo="Sin datos sensor"
            elif hum_prom>=80: estado_suelo="SATURADO"
            elif hum_prom>=60: estado_suelo="ÓPTIMO"
            elif hum_prom>=40: estado_suelo="ESTRÉS"
            else: estado_suelo="SECO"
            sectores_info[sid]={
                "planta":scfg.get('planta','tomate'),"planta_nombre":planta["nombre"],"emoji":planta["emoji"],"color":planta["color"],
                "hum":planta["hum"],"hum_amb_ideal":planta["hum_amb"],"ph_ideal":planta["ph"],"temp_ideal":planta["temp"],"n_ideal":planta["n"],"p_ideal":planta["p"],"k_ideal":planta["k"],"nota":planta["nota"],"ec_ideal":"400-800",
                "hum_ideal":planta["hum"],"cant_sensores":scfg.get('cant_sensores',1),"cant_valvulas":len(valvulas_cfg),"valvulas":valvulas_cfg,
                "humedad_prom":hum_prom,"temp":temp,"ph":ph,"ec":ec,"n":n,"p":p,"k":k,
                "umbral_on":planta["on"],"umbral_off":planta["off"],"sensores_activos":len(sensores_sector),
                "ultimo_hace":f"{int(time.time()-sensores_sorted[-1]['ts'])}s" if sensores_sorted else "nunca","estado_suelo":estado_suelo,
                "id_ejemplo":f"{finca_id}_s{sid}_v1"
            }
            reporte+=f"● Sector {sid} {planta['emoji']} {planta['nombre']} ({scfg.get('cant_sensores')} sensores, {len(valvulas_cfg)} válvulas): Hum {hum_prom:.1f}% {estado_suelo} ON<{planta['on']}% OFF>={planta['off']}% Ideal: {planta['hum']} pH {planta['ph']} Temp {planta['temp']} N {planta['n']} P {planta['p']} K {planta['k']} Actual: T{temp} pH{ph} N{n} P{p} K{k} Nota: {planta['nota']}\n  Válvulas: {', '.join([f\"V{v['id']} {v['pulgadas']}\" + (' OPEN' if actuadores_valvulas.get(f'{finca_id}_s{sid}_v{v[\"id\"]}',{}).get('valvula') else ' CLOSED') for v in valvulas_cfg])}\n\n"
        # Bombas total flow
        for b in bombas_cfg:
            ak=f"{finca_id}_b{b['id']}"
            if ak not in actuadores_bombas: actuadores_bombas[ak]={"bomba":0,"start_time":None,"litros_flow":0,"litros_estimado":0,"tiempo_acum":0}
            total_flow+=actuadores_bombas[ak]["litros_flow"]; total_est+=actuadores_bombas[ak]["litros_estimado"]
        dif=abs(total_flow-total_est)/total_est*100 if total_est>0 else 0
        alerta="Sin riego" if total_est==0 and total_flow==0 else ("✅ OK" if dif<=20 else "⚠️ Fuga >20%")
        clima={"temp":31,"hum":28,"viento":14,"desc":"Soleado San Juan","riego_recomendado":"Riego normal OXITEM","flow_info":f"Bomba {finca_cfg.get('bomba_pulgadas','0.5')}\" {finca_cfg.get('bomba_lpm',25)}L/min","ubicacion":finca_cfg.get('ubicacion','Villa Krause')}
        hist_filtrado=[h for h in historico if h.get('finca')==finca_id]
        return jsonify({
            "finca_id":finca_id,"finca_sectores":len(sectores_cfg),"bombas_total":len(bombas_cfg),"valvulas_total":valvulas_total,"sensores_total":len(sensores_data),
            "sensores":sensores_data,"actuadores_valvulas":actuadores_valvulas,"actuadores_bombas":actuadores_bombas,"historico":hist_filtrado[-20:],
            "logs":logs[-20:],"sectores":sectores_info,"bombas":bombas_cfg,
            "consumo":{"total_litros_flow":total_flow,"total_litros_estimado":total_est,"diferencia":round(dif,1),"alerta":alerta},
            "reporte":reporte or "Sin sectores","ultimo_temp":ultimo_temp,"ultimo_ph":ultimo_ph,"ultimo_ec":ultimo_ec,"ultimo_n":ultimo_n,"ultimo_p":ultimo_p,"ultimo_k":ultimo_k,"clima":clima
        })
    except Exception as e:
        import traceback
        return jsonify({"error":str(e),"trace":traceback.format_exc(),"sectores":{},"bombas":[],"consumo":{"total_litros_flow":0,"total_litros_estimado":0,"diferencia":0,"alerta":f"Error {e}"},"historico":[],"logs":logs[-10:],"reporte":f"Error: {e}","clima":{"temp":0,"hum":0,"viento":0,"desc":f"Error {e}","riego_recomendado":"Error","flow_info":"Error","ubicacion":"Error"}}),500

@app.route('/api/comando', methods=['POST'])
def comando():
    try:
        d=request.get_json(force=True)
        finca=d.get('finca','default').strip()
        dev=d.get('device','')
        est=int(d.get('estado',0))
        sector=str(d.get('sector','')).strip()
        valvula_id=str(d.get('valvula_id','')).strip()
        bomba_id=str(d.get('bomba_id','')).strip()
        log(f"CMD {finca} dev={dev} sec={sector} valv={valvula_id} bomba={bomba_id} est={est}")
        finca_cfg=db["users"].get(finca,{}).get('finca',{})
        bomba_lpm=finca_cfg.get('bomba_lpm',25)
        if dev=='todas_bombas':
            for ak in actuadores_bombas:
                if ak.startswith(finca+"_b"):
                    if est==1 and actuadores_bombas[ak]["bomba"]==0:
                        actuadores_bombas[ak]["bomba"]=1; actuadores_bombas[ak]["start_time"]=time.time()
                    elif est==0:
                        if actuadores_bombas[ak]["start_time"]:
                            dur=time.time()-actuadores_bombas[ak]["start_time"]
                            actuadores_bombas[ak]["litros_estimado"]+=dur * bomba_lpm / 60.0
                            actuadores_bombas[ak]["tiempo_acum"]+=dur
                        actuadores_bombas[ak]["bomba"]=0; actuadores_bombas[ak]["start_time"]=None
        elif dev=='todas_valvulas':
            for ak in actuadores_valvulas:
                if ak.startswith(finca+"_s"):
                    if est==1 and actuadores_valvulas[ak]["valvula"]==0:
                        actuadores_valvulas[ak]["valvula"]=1; actuadores_valvulas[ak]["start_time"]=time.time()
                    elif est==0:
                        if actuadores_valvulas[ak]["start_time"]:
                            dur=time.time()-actuadores_valvulas[ak]["start_time"]
                            actuadores_valvulas[ak]["litros_estimado"]+=dur * bomba_lpm / 60.0
                            actuadores_valvulas[ak]["tiempo_acum"]+=dur
                        actuadores_valvulas[ak]["valvula"]=0; actuadores_valvulas[ak]["start_time"]=None
            # Si cierra todas valvulas, apaga todas bombas tambien
            if est==0:
                for ak in actuadores_bombas:
                    if ak.startswith(finca+"_b") and actuadores_bombas[ak]["bomba"]==1:
                        if actuadores_bombas[ak]["start_time"]:
                            dur=time.time()-actuadores_bombas[ak]["start_time"]
                            actuadores_bombas[ak]["litros_estimado"]+=dur * bomba_lpm / 60.0
                            actuadores_bombas[ak]["tiempo_acum"]+=dur
                        actuadores_bombas[ak]["bomba"]=0; actuadores_bombas[ak]["start_time"]=None
        elif dev=='valvula_id' and sector and valvula_id:
            ak=f"{finca}_s{sector}_v{valvula_id}"
            if ak not in actuadores_valvulas: actuadores_valvulas[ak]={"valvula":0,"start_time":None,"litros_flow":0,"litros_estimado":0,"tiempo_acum":0}
            if est==1 and actuadores_valvulas[ak]["valvula"]==0:
                actuadores_valvulas[ak]["valvula"]=1; actuadores_valvulas[ak]["start_time"]=time.time()
                log(f"VALV S{sector} V{valvula_id} OPEN - Prende bomba asignada")
                # Prende bombas asignadas a este sector
                for b in finca_cfg.get('bombas',[{"id":1,"sector_asignado":0}]):
                    if b["sector_asignado"]==0 or str(b["sector_asignado"])==sector:
                        bak=f"{finca}_b{b['id']}"
                        if bak not in actuadores_bombas: actuadores_bombas[bak]={"bomba":0,"start_time":None,"litros_flow":0,"litros_estimado":0,"tiempo_acum":0}
                        if actuadores_bombas[bak]["bomba"]==0:
                            actuadores_bombas[bak]["bomba"]=1; actuadores_bombas[bak]["start_time"]=time.time()
            elif est==0 and actuadores_valvulas[ak]["valvula"]==1:
                if actuadores_valvulas[ak]["start_time"]:
                    dur=time.time()-actuadores_valvulas[ak]["start_time"]
                    actuadores_valvulas[ak]["litros_estimado"]+=dur * bomba_lpm / 60.0
                    actuadores_valvulas[ak]["tiempo_acum"]+=dur
                actuadores_valvulas[ak]["valvula"]=0; actuadores_valvulas[ak]["start_time"]=None
                log(f"VALV S{sector} V{valvula_id} CLOSED")
                # Si no quedan valvulas abiertas en ese sector, apaga bombas asignadas
                otras_abiertas_sector=any(actuadores_valvulas.get(f"{finca}_s{sector}_v{v['id']}",{"valvula":0})["valvula"]==1 for v in finca_cfg.get('sectores_config',{}).get(sector,{}).get('valvulas',[]) if str(v['id'])!=valvula_id)
                if not otras_abiertas_sector:
                    for b in finca_cfg.get('bombas',[]):
                        if b["sector_asignado"]==0 or str(b["sector_asignado"])==sector:
                            # Solo apaga si no hay ningun otro sector con valvulas abiertas que use esa bomba
                            hay_otro=False
                            for sid, scfg in finca_cfg.get('sectores_config',{}).items():
                                if sid==sector: continue
                                if b["sector_asignado"]!=0 and str(b["sector_asignado"])!=sid: continue
                                for v in scfg.get('valvulas',[]):
                                    if actuadores_valvulas.get(f"{finca}_s{sid}_v{v['id']}",{"valvula":0})["valvula"]==1:
                                        hay_otro=True
                            if not hay_otro:
                                bak=f"{finca}_b{b['id']}"
                                if bak in actuadores_bombas and actuadores_bombas[bak]["bomba"]==1:
                                    if actuadores_bombas[bak]["start_time"]:
                                        dur=time.time()-actuadores_bombas[bak]["start_time"]
                                        actuadores_bombas[bak]["litros_estimado"]+=dur * bomba_lpm / 60.0
                                        actuadores_bombas[bak]["tiempo_acum"]+=dur
                                    actuadores_bombas[bak]["bomba"]=0; actuadores_bombas[bak]["start_time"]=None
        elif dev=='bomba_id' and bomba_id:
            ak=f"{finca}_b{bomba_id}"
            if ak not in actuadores_bombas: actuadores_bombas[ak]={"bomba":0,"start_time":None,"litros_flow":0,"litros_estimado":0,"tiempo_acum":0}
            if est==1 and actuadores_bombas[ak]["bomba"]==0:
                actuadores_bombas[ak]["bomba"]=1; actuadores_bombas[ak]["start_time"]=time.time()
            elif est==0 and actuadores_bombas[ak]["bomba"]==1:
                if actuadores_bombas[ak]["start_time"]:
                    dur=time.time()-actuadores_bombas[ak]["start_time"]
                    actuadores_bombas[ak]["litros_estimado"]+=dur * bomba_lpm / 60.0
                    actuadores_bombas[ak]["tiempo_acum"]+=dur
                actuadores_bombas[ak]["bomba"]=0; actuadores_bombas[ak]["start_time"]=None
        return {"ok":True}
    except Exception as e:
        import traceback
        return {"ok":False,"error":str(e),"trace":traceback.format_exc()},500

@app.route('/api/riego')
def riego():
    try:
        finca_id=request.args.get('finca','default').strip()
        sector_id=request.args.get('sector','1').strip()
        valvula_id=request.args.get('valvula_id', request.args.get('valvula','1')).strip()
        bomba_id=request.args.get('bomba_id', request.args.get('bomba','1')).strip()
        # Bomba por ID
        if sector_id=='0' or request.args.get('bomba_id'):
            # Si pide bomba_id especifico
            if bomba_id and bomba_id!='1':
                ak=f"{finca_id}_b{bomba_id}"
                act=actuadores_bombas.get(ak,{"bomba":0})
                return jsonify({"bomba": bool(act["bomba"]), "bomba_principal": act["bomba"], "bomba_id": int(bomba_id) if bomba_id.isdigit() else bomba_id, "finca":finca_id, "sector":0})
            # Si pide sector 0, devuelve si alguna bomba ON
            alguna_on=any(v["bomba"]==1 for k,v in actuadores_bombas.items() if k.startswith(finca_id+"_b"))
            # Tambien si alguna valvula ON, bomba debe estar ON
            alguna_valv_on=any(v["valvula"]==1 for k,v in actuadores_valvulas.items() if k.startswith(finca_id+"_s"))
            bomba_estado=alguna_on or alguna_valv_on
            return jsonify({"bomba": bomba_estado, "bomba_principal": int(bomba_estado), "valvula": False, "finca":finca_id, "sector":0, "bomba_id":1})
        # Valvula especifica por sector y valvula_id
        ak=f"{finca_id}_s{sector_id}_v{valvula_id}"
        act=actuadores_valvulas.get(ak,{"valvula":0})
        finca_cfg=db["users"].get(finca_id,{}).get('finca',{})
        sec_cfg=finca_cfg.get('sectores_config',{}).get(str(sector_id),{})
        planta=PLANTAS.get(sec_cfg.get('planta','tomate'), PLANTAS["tomate"])
        # Bomba asignada a este sector
        bomba_asignada=False
        for b in finca_cfg.get('bombas',[{"id":1,"sector_asignado":0}]):
            if b["sector_asignado"]==0 or str(b["sector_asignado"])==sector_id:
                bak=f"{finca_id}_b{b['id']}"
                if actuadores_bombas.get(bak,{"bomba":0})["bomba"]==1:
                    bomba_asignada=True
        return jsonify({"bomba": bomba_asignada, "valvula": bool(act["valvula"]), "bomba_principal": int(bomba_asignada), "valvula_sector": act["valvula"], "valvula_id": int(valvula_id) if valvula_id.isdigit() else valvula_id, "sector":int(sector_id) if sector_id.isdigit() else sector_id, "finca":finca_id, "umbral_on":planta["on"], "umbral_off":planta["off"], "planta":planta["nombre"]})
    except Exception as e:
        return jsonify({"bomba":False,"valvula":False,"error":str(e)}),500

@app.route('/api/debug')
def debug():
    return jsonify({"db_file":DB_FILE,"users":list(db["users"].keys()),"sensores_total":len(sensores_data),"actuadores_valvulas":actuadores_valvulas,"actuadores_bombas":actuadores_bombas,"logs":logs[-20:]})

if __name__=='__main__':
    app.run(host='0.0.0.0',port=5000)

