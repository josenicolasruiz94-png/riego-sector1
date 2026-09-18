"""
APP MAESTRO RENDER - VERSION LIVIANA - SIN CALCULOS PESADOS
Todo el Kalman ya viene hecho del ESP32
Render solo guarda, grafica y decide ON/OFF

Para Render:
pip install -r requirements.txt
gunicorn app:app
"""
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import time
from datetime import datetime

app = Flask(__name__)
CORS(app)

# DB en RAM - super liviana, no consume los 512MB gratis
sensores = {}  # {"sector1_sensor1": {humedad:28.5, ...}}
actuadores = {"bomba_principal":0, "sector1_valvula1":0}
historico = []
logs = []

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    logs.append(f"{ts} - {msg}")
    if len(logs) > 100: logs.pop(0)
    print(logs[-1])

HTML = """
<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Finca - Maestro Nube</title><script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>body{margin:0;font-family:system-ui;background:#f8fafc} .header{background:#0f172a;color:white;padding:18px 22px;display:flex;justify-content:space-between}
.card{background:white;border-radius:18px;padding:16px;margin:12px;box-shadow:0 4px 12px rgba(0,0,0,0.05)} .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;padding:12px}
.val{font-size:30px;font-weight:900} .badge{background:#22c55e;color:#000;padding:5px 10px;border-radius:20px;font-weight:800;font-size:11px}
.btn{padding:10px 16px;border-radius:10px;border:none;font-weight:800;cursor:pointer} .log{font-family:monospace;font-size:11px;background:#0f172a;color:#86efac;padding:12px;border-radius:12px;max-height:200px;overflow:auto}
</style></head><body>
<div class="header"><div><b>🌱 FINCA INTELIGENTE - MAESTRO RENDER (LIVIANO)</b><div style="opacity:0.7;font-size:12px">Kalman calculado en ESP32 - Render solo decide y grafica - Prototipo Sector 1</div></div><div class="badge">● RENDER FREE 512MB OK</div></div>
<div class="grid">
  <div class="card"><div style="font-size:10px;color:#64748b">ID SENSOR</div><div class="val" style="font-size:18px" id="idS">sector1_sensor1</div><div style="font-size:11px" id="hora">-</div></div>
  <div class="card" style="border-left:6px solid #22c55e"><div style="font-size:10px;color:#64748b">HUMEDAD (YA FILTRADA EN ESP32)</div><div class="val" id="hum">-- %</div><div style="font-size:11px">Umbral riego: 30%</div></div>
  <div class="card"><div style="font-size:10px">TEMP</div><div class="val" id="temp">-- °C</div></div>
  <div class="card"><div style="font-size:10px">pH</div><div class="val" id="ph">--</div></div>
  <div class="card"><div style="font-size:10px">EC / N-P-K</div><div class="val" style="font-size:16px" id="npk">--</div></div>
  <div class="card"><div style="font-size:10px">ACTUADORES</div><div>Bomba: <b id="bSt">OFF</b> | Valvula S1: <b id="vSt">CLOSED</b></div></div>
</div>
<div style="display:grid;grid-template-columns:2fr 1fr;gap:12px;padding:0 12px">
  <div class="card"><canvas id="cHum" height="110"></canvas></div>
  <div class="card"><b>Control</b><br><br><button class="btn" style="background:#0f172a;color:white" onclick="cmd('bomba_principal',1)">BOMBA ON</button> <button class="btn" onclick="cmd('bomba_principal',0)">OFF</button><br><br><button class="btn" style="background:#0f172a;color:white" onclick="cmd('sector1_valvula1',1)">VALVULA OPEN</button> <button class="btn" onclick="cmd('sector1_valvula1',0)">CLOSE</button><br><br><label><input type="checkbox" id="auto" checked> Auto ON</label></div>
</div>
<div class="card" style="background:linear-gradient(135deg,#22c55e,#16a34a);color:white"><b>📋 Reporte Finca Sector 1 (Datos ya filtrados por ESP32)</b><div id="rep" style="margin-top:6px;font-size:13px">Esperando datos...</div></div>
<div class="card"><canvas id="cOtros" height="70"></canvas></div>
<div class="log" id="log"></div>
<script>
let ch,ch2;
function init(){
 ch=new Chart(document.getElementById('cHum'),{type:'line',data:{labels:[],datasets:[{label:'Humedad KF (calculada en ESP32)',data:[],borderColor:'#22c55e',fill:false}]},options:{scales:{y:{min:0,max:100}}}});
 ch2=new Chart(document.getElementById('cOtros'),{type:'bar',data:{labels:['Temp','pH*10','EC/10','N','P','K/10'],datasets:[{data:[],backgroundColor:'#0f172a'}]},options:{plugins:{legend:{display:false}}}});
}
async function load(){
 const r=await fetch('/api/estado'); const j=await r.json();
 const s=j.sensores['sector1_sensor1']; if(!s) return;
 document.getElementById('idS').innerText=s.id; document.getElementById('hora').innerText=new Date(s.ts*1000).toLocaleTimeString();
 document.getElementById('hum').innerText=s.humedad.toFixed(1)+' %'; document.getElementById('temp').innerText=s.temperatura.toFixed(1)+' °C';
 document.getElementById('ph').innerText=s.ph.toFixed(2); document.getElementById('npk').innerText=`EC ${s.ec} | ${s.n}/${s.p}/${s.k}`;
 document.getElementById('bSt').innerText=j.actuadores['bomba_principal']?'ON':'OFF'; document.getElementById('vSt').innerText=j.actuadores['sector1_valvula1']?'OPEN':'CLOSED';
 ch.data.labels=j.historico.map(h=>new Date(h.ts*1000).toLocaleTimeString()); ch.data.datasets[0].data=j.historico.map(h=>h.humedad); ch.update();
 ch2.data.datasets[0].data=[s.temperatura,s.ph*10,s.ec/10,s.n,s.p,s.k/10]; ch2.update();
 let txt=''; const hum=s.humedad;
 if(hum<25) txt=`⚠️ SECO ${hum.toFixed(1)}% - Riego activo en Sector 1. Datos filtrados por Kalman en ESP32 (ahorra RAM Render).`;
 else if(hum<30) txt=`🌱 SECO ${hum.toFixed(1)}% - Iniciando riego. pH ${s.ph} óptimo.`;
 else if(hum<50) txt=`✅ ÓPTIMO ${hum.toFixed(1)}% - Sector 1 hidratado. No riega.`;
 else txt=`💧 EXCESO ${hum.toFixed(1)}% - Detenido.`;
 document.getElementById('rep').innerText=txt;
 document.getElementById('log').innerHTML=j.logs.slice(-15).reverse().map(l=>`<div>${l}</div>`).join('');
}
async function cmd(d,e){ await fetch('/api/comando',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({device:d,estado:e})}); load(); }
init(); setInterval(load,3000); load();
</script></body></html>
"""

@app.route('/')
def dash():
    return render_template_string(HTML)

@app.route('/api/datos', methods=['POST'])
def datos():
    # Render recibe dato YA FILTRADO por ESP32 - no calcula Kalman aqui
    j = request.get_json()
    if not j: return {"error":"no json"}, 400
    id_s = j.get('id','sector1_sensor1')
    j['ts'] = time.time()
    sensores[id_s] = j
    historico.append({"ts":j['ts'],"humedad":j.get('humedad'),"id":id_s})
    if len(historico)>100: historico.pop(0)
    log(f"RX {id_s} KF desde ESP32: Hum {j.get('humedad')}%")
    # Decision super liviana - no consume RAM
    hum = j.get('humedad',100)
    if j.get('sector',1)==1:
        if hum < 30:
            actuadores['bomba_principal']=1
            actuadores['sector1_valvula1']=1
            log(f"AUTO Sector1 hum {hum}% <30 -> BOMBA ON + VALVULA OPEN")
        elif hum > 50:
            actuadores['bomba_principal']=0
            actuadores['sector1_valvula1']=0
            log(f"AUTO hum {hum}% alta -> OFF")
    return {"ok":True}

@app.route('/api/estado')
def estado():
    return {"sensores":sensores,"actuadores":actuadores,"historico":historico[-20:],"logs":logs[-20:]}

@app.route('/api/comando', methods=['GET','POST'])
def comando():
    if request.method=='POST':
        d=request.get_json()
        dev=d.get('device'); est=d.get('estado',0)
        if dev in actuadores:
            actuadores[dev]=est
            log(f"MANUAL {dev} -> {est}")
        return {"ok":True}
    else:
        dev=request.args.get('device','bomba')
        key=dev
        if dev=='bomba': key='bomba_principal'
        if dev=='valvula': key='sector1_valvula1'
        return {"device":key,"estado":actuadores.get(key,0)}

if __name__=='__main__':
    app.run(host='0.0.0.0',port=5000)



