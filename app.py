"""
 OXITEM V13 - Backend Flask (Render)  ->  guardar como app.py
 Start Command en Render:  gunicorn app:app --workers 1 --threads 4 --timeout 60
 (IMPORTANTE: 1 solo worker, el estado de riego vive en memoria)

 Variables de entorno recomendadas en Render:
   SECRET_KEY    	clave larga aleatoria (si no, las sesiones se pierden al reiniciar)
   ADMIN_USER / ADMIN_PASS   credenciales admin (default admin / OXITEM -> CAMBIAR)
   DB_FILE       	ej: /var/data/fincas_db_v13.json  (con Render Disk, si no se pierde al redeploy)
   REQUIRE_DEVICE_KEY  1 (default) exige API_KEY en los ESP32. 0 solo para pruebas
   ALLOW_REGISTER	1/0 permite crear fincas nuevas desde /register
   COOKIE_SECURE 	1 (default, https). Poner 0 solo si pruebas local por http
   OPENWEATHER_KEY / WEATHER_QUERY   clima real (opcional), ej "San Juan,AR"
   TZ_OFFSET     	horas respecto a UTC para los logs (default -3)

 Cambios principales V13 (ver resumen en la respuesta):
   - Logica de riego centralizada en tick(): promedio de sensores frescos, histeresis, modos AUTO/ON/OFF
   - Bomba se calcula sola segun valvulas abiertas de SUS sectores (ya no prende B2 cuando pide B1)
   - Valvula abre primero y bomba despues; al cerrar, bomba para primero (LEAD_S)
   - Protecciones: sin datos frescos -> cierra, tiempo maximo de riego, alarmas sin caudal
   - Litros estimados repartidos entre valvulas abiertas (antes se triplicaban)
   - Seguridad: passwords hasheadas, API_KEY por finca, endpoints con sesion, XSS escapado
   - 36 plantas (ficha Villa Krause + uva + olivo), alertas pH/NPK/temp segun la planta
 """
 import os, re, json, time, hmac, secrets, threading, urllib.request, urllib.parse
 from collections import deque
 from datetime import datetime, timezone, timedelta
 from flask import Flask, request, jsonify, render_template_string, session, redirect
 from werkzeug.security import generate_password_hash, check_password_hash

 app = Flask(__name__)
 app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
 app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                   SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "1") == "1")

 ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
 ADMIN_PASS = os.environ.get("ADMIN_PASS", "OXITEM")
 REQUIRE_KEY = os.environ.get("REQUIRE_DEVICE_KEY", "1") == "1"
 ALLOW_REGISTER = os.environ.get("ALLOW_REGISTER", "1") == "1"
 DB_FILE = os.environ.get("DB_FILE", "fincas_db_v13.json")
 TZ = timezone(timedelta(hours=float(os.environ.get("TZ_OFFSET", "-3"))))

 STALE_S = 180      	# un sensor sin reportar hace mas de esto se considera sin dato
 LEAD_S = 6         	# segundos entre abrir valvula y prender bomba (y bomba apagada antes de cerrar valvula)
 MAX_RIEGO_S = 45 * 60  # tiempo maximo continuo de riego AUTO por valvula
 BLOQUEO_S = 30 * 60	# bloqueo del sector tras superar MAX_RIEGO_S
 MAX_MANUAL_S = 2 * 3600  # una valvula en modo ON manual vuelve a AUTO despues de esto
 PEDIDO_VALIDO_S = 30

 LOCK = threading.RLock()
 DBLOCK = threading.Lock()

 BOMBA_CAUDAL = {"0.5": 25, "0.75": 45, "1": 80, "1.25": 120, "1.5": 180}
 BOMBA_TXT = {"0.5": '1/2" 25 L/min', "0.75": '3/4" 45 L/min', "1": '1" 80 L/min', "1.25": '1 1/4" 120 L/min'}
 VALV_PULG = ["0.5", "0.75", "1"]
 FLOW_SPECS = {"no": {"modelo": "Sin flow (estimado)"},
           	"yf_s201": {"modelo": 'YF-S201 1/2" 450 p/L'},
           	"fs400a": {"modelo": 'FS400A 1" 360 p/L'}}
 FLOW_LEGACY = {"no": "no", "0.5": "yf_s201", "1_fs400": "fs400a"}

 # ============================== PLANTAS ==============================
 PLANTAS = {}
 COLOR_GRUPO = {"Huerta y aromáticas": "#22c55e", "Ornamentales de flor": "#f472b6",
            	"Suculentas e interior": "#38bdf8", "Frutal SJ": "#a78bfa"}

 def _rng(s):
 	n = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", str(s))]
 	return (n[0], n[-1]) if n else (None, None)

 def _p(k, nombre, emoji, grupo, hum, ph, temp, n, p, kk, nota="", on=None):
 	lo, hi = _rng(hum)
 	PLANTAS[k] = {"nombre": nombre, "emoji": emoji, "grupo": grupo,
               	"on": on if on is not None else lo, "off": hi, "color": COLOR_GRUPO[grupo],
               	"hum": hum + "%", "ph": ph, "temp": temp + "°C", "n": n, "p": p, "k": kk, "nota": nota}

 G1, G2, G3, G4 = "Huerta y aromáticas", "Ornamentales de flor", "Suculentas e interior", "Frutal SJ"
 # hum = rango ideal de sustrato (VWC relativo a capacidad de campo). ON = limite inferior, OFF = limite superior
 # (tomate: ON=60 segun recomendacion de la ficha)
 _p("tomate", "Tomate", "🍅", G1, "70-80", "5.5-6.8", "18-27", "150-200", "50-80", "250-350", "Muy demandante de K en floración", on=60)
 _p("lechuga", "Lechuga", "🥬", G1, "60-75", "6.0-7.0", "15-22", "120-150", "30-50", "150-200", "Media sombra obligatoria en verano SJ")
 _p("menta", "Menta", "🌿", G1, "75-85", "6.0-7.0", "15-25", "150", "50", "150", "Invasiva, maceta aparte")
 _p("ruda", "Ruda", "🌱", G1, "40-55", "6.0-8.0", "18-28", "50-80", "20-30", "80-120", "Autóctona, odia el encharque")
 _p("oregano", "Orégano", "🌿", G1, "45-60", "6.0-8.0", "18-30", "80", "30", "120")
 _p("romero", "Romero", "🌿", G1, "30-50", "5.5-7.0", "15-28", "50", "20", "100", "Si se riega mucho se muere")
 _p("papa", "Papa", "🥔", G1, "65-80", "5.0-6.0", "15-22", "100-150", "80-100", "300-400")
 _p("zanahoria", "Zanahoria", "🥕", G1, "60-70", "6.0-6.8", "16-24", "100", "60", "200")
 _p("habas", "Habas (Avas)", "🫘", G1, "60-75", "6.0-7.5", "10-22", "30-50", "60", "150", "Fija nitrógeno")
 _p("ajo", "Ajo", "🧄", G1, "50-65", "6.0-7.0", "12-22", "120", "50", "180")
 _p("cebolla", "Cebolla", "🧅", G1, "60-70", "6.0-7.0", "13-24", "110", "70", "180")
 _p("zapallo_ancho", "Zapallo Ancho", "🎃", G1, "70-80", "6.0-7.5", "20-30", "150", "50", "250")
 _p("zapallo_ingles", "Zapallo Inglés", "🎃", G1, "70-80", "6.0-7.0", "20-28", "150", "50", "250")
 _p("frutilla", "Frutilla", "🍓", G1, "65-75", "5.5-6.5", "15-24", "100", "70", "200", "pH ácido fundamental")
 _p("frambuesa", "Frambuesa", "🍇", G1, "65-80", "5.5-6.5", "12-22", "100", "50", "150")
 _p("pepino", "Pepino", "🥒", G1, "75-85", "5.5-6.8", "20-30", "150", "50", "250")
 _p("marimona", "Marimoña (Ranunculus)", "🌺", G2, "60-70", "6.0-7.0", "10-20", "100", "50", "150")
 _p("copete", "Copete (Tagetes)", "🌼", G2, "50-65", "6.0-7.0", "18-28", "80", "30", "120", "Repelente de plagas, ideal asociar con tomate")
 _p("conejito", "Conejito (Antirrhinum)", "🌸", G2, "60-70", "6.0-7.0", "12-22", "100", "40", "140")
 _p("clavel", "Clavel", "🌸", G2, "50-60", "6.0-7.5", "15-24", "120", "50", "180")
 _p("clavel_enano", "Clavel Enano", "🌸", G2, "50-60", "6.0-7.0", "15-22", "100", "40", "150")
 _p("petunia", "Petunia", "🌸", G2, "60-70", "5.5-6.5", "16-26", "120", "50", "150")
 _p("girasol", "Girasol", "🌻", G2, "60-75", "6.0-7.5", "20-30", "150", "60", "200")
 _p("pensamiento", "Pensamiento (Viola)", "🌼", G2, "65-75", "5.5-6.5", "10-18", "100", "40", "120", "Flor de invierno")
 _p("malvon", "Malvón (Pelargonium)", "🌺", G2, "45-60", "6.0-7.5", "16-26", "80", "30", "120")
 _p("rosa", "Rosa", "🌹", G2, "60-70", "6.0-6.8", "15-25", "150", "60", "200")
 _p("alegria", "Alegría del Hogar (Impatiens)", "🌸", G2, "70-80", "6.0-6.5", "18-24", "100", "40", "140", "No tolera sol directo sanjuanino")
 _p("flor_azucar", "Flor de Azúcar (Begonia)", "🌸", G2, "60-70", "5.5-6.5", "18-24", "100", "40", "120")
 _p("orquidea", "Orquídeas (Phalaenopsis)", "🪷", G2, "50-60", "5.5-6.5", "18-28", "50", "20", "50", "Sustrato de corteza y carbón: el sensor de suelo NO es confiable en corteza")
 _p("paleta", "Paleta de Pintor (Hypoestes)", "🎨", G3, "60-75", "5.5-6.5", "18-26", "80", "30", "100")
 _p("calanchoe", "Calanchoe (Kalanchoe)", "🪴", G3, "30-45", "6.0-7.0", "15-25", "50", "20", "80")
 _p("lazo_amor", "Lazo de Amor (Chlorophytum)", "🪴", G3, "50-65", "6.0-7.0", "15-26", "80", "30", "100")
 _p("dolar_negro", "Dólar Negro", "🪴", G3, "55-70", "6.0-7.0", "16-26", "100", "30", "120")
 _p("garrita_oso", "Garrita de Oso (Cotyledon)", "🪴", G3, "20-35", "6.0-7.5", "15-28", "30", "10", "50", "Suculenta extrema")
 _p("uva", "Uva Vid SJ", "🍇", G4, "40-60", "6.0-7.5", "15-30", "80-120", "40-60", "150-250", "Emblemático SJ")
 _p("olivo", "Olivo", "🫒", G4, "30-50", "6.0-8.0", "15-30", "60-100", "20-40", "100-200", "Tolerante a sequía")

 # ============================== UTILIDADES ==============================
 def eq(a, b):
 	return hmac.compare_digest(str(a).encode(), str(b).encode())

 def num(x, d=0.0):
 	try:
     	v = float(x)
     	return v if v == v and abs(v) < 1e9 else d
 	except (TypeError, ValueError):
     	return d

 def ent(x, lo, hi, d):
 	"""entero estricto: si esta fuera de rango devuelve d"""
 	try:
     	v = int(float(x))
 	except (TypeError, ValueError):
     	return d
 	return v if lo <= v <= hi else d

 def clamp(x, lo, hi, d):
 	try:
     	v = int(float(x))
 	except (TypeError, ValueError):
     	return d
 	return max(lo, min(hi, v))

 def limpiar(bombas_in, sect_in, n_b=None, n_s=None):
 	"""Valida y normaliza la config de bombas y sectores (usada al migrar, registrar y guardar)."""
 	bombas_in = bombas_in if isinstance(bombas_in, list) else []
 	sect_in = sect_in if isinstance(sect_in, dict) else {}
 	n_b = clamp(n_b if n_b else (len(bombas_in) or 1), 1, 10, 1)
 	n_s = clamp(n_s if n_s else (len(sect_in) or 1), 1, 20, 1)
 	bombas = []
 	for i in range(1, n_b + 1):
     	b = next((x for x in bombas_in if isinstance(x, dict) and str(x.get("id")) == str(i)), {})
     	pulg = str(b.get("pulgadas", "0.5"))
     	if pulg not in BOMBA_CAUDAL:
         	pulg = "0.5"
     	fl = b.get("flow") or FLOW_LEGACY.get(str(b.get("flow_pulgadas", "no")), "no")
     	if fl not in FLOW_SPECS:
         	fl = "no"
     	bombas.append({"id": i, "pulgadas": pulg, "flow": fl})
 	sect = {}
 	for i in range(1, n_s + 1):
     	s = sect_in.get(str(i)) or sect_in.get(i) or {}
     	planta = s.get("planta") if s.get("planta") in PLANTAS else "tomate"
     	cv = clamp(s.get("cant_valvulas", len(s.get("valvulas", [])) or 1), 1, 10, 1)
     	vin = s.get("valvulas") if isinstance(s.get("valvulas"), list) else []
     	vals = []
     	for v in range(1, cv + 1):
         	x = next((y for y in vin if isinstance(y, dict) and str(y.get("id")) == str(v)), {})
         	pg = str(x.get("pulgadas", "1"))
         	vals.append({"id": v, "pulgadas": pg if pg in VALV_PULG else "1",
                          "flow_present": x.get("flow_present") in (True, "true", 1)})
     	sect[str(i)] = {"planta": planta, "cant_sensores": clamp(s.get("cant_sensores", 1), 1, 20, 1),
                         "cant_valvulas": cv, "valvulas": vals,
                         "bomba_asignada": clamp(s.get("bomba_asignada", 1), 1, n_b, 1)}
 	return bombas, sect

 # ============================== BASE DE DATOS ==============================
 def guardar_db():
 	with DBLOCK:
     	try:
         	tmp = DB_FILE + ".tmp"
         	with open(tmp, "w") as fp:
             	json.dump(db, fp, indent=1)
         	os.replace(tmp, DB_FILE)
     	except Exception as e:
         	print("Error guardando DB:", e, flush=True)

 def cargar_db():
 	for fn in (DB_FILE, "fincas_db_v12.json", "fincas_db_v11.json", "fincas_db_v10.json"):
     	if os.path.exists(fn):
         	try:
             	with open(fn) as fp:
                 	d = json.load(fp)
                 d.setdefault("users", {})
             	return d
         	except Exception as e:
             	print("Error leyendo", fn, e, flush=True)
 	return {"users": {}}

 db = cargar_db()

 def migrar():
 	for name, u in db["users"].items():
     	if "password" in u:  # V12 guardaba la clave en texto plano
         	u["password_hash"] = generate_password_hash(u.pop("password"))
     	f = u.setdefault("finca", {})
     	f["ubicacion"] = f.get("ubicacion") or "Villa Krause, Rawson, San Juan"
     	f["largo"] = clamp(f.get("largo", 10), 1, 100000, 10)
     	f["ancho"] = clamp(f.get("ancho", 10), 1, 100000, 10)
     	f["m2"] = f["largo"] * f["ancho"]
     	f["api_key"] = f.get("api_key") or secrets.token_urlsafe(16)
     	f["bombas"], f["sectores_config"] = limpiar(f.get("bombas"), f.get("sectores_config"),
                                                     f.get("bombas_totales"), f.get("sectores"))
     	f["bombas_totales"] = len(f["bombas"])
     	f["sectores"] = len(f["sectores_config"])
     	for k in ("bomba_lpm", "bomba_pulgadas", "valvula_ppal_pulgadas"):
         	f.pop(k, None)
 	guardar_db()

 migrar()

 def cfg_de(f):
 	return db["users"].get(f, {}).get("finca")

 # ============================== AUTENTICACION ==============================
 def es_admin():
 	return session.get("user") == ADMIN_USER

 def puede(f):
 	u = session.get("user")
 	return bool(u) and f in db["users"] and (u == ADMIN_USER or u == f)

 def dev_ok(f):
 	cfg = cfg_de(f)
 	if not cfg:
     	return False
 	if not REQUIRE_KEY:
     	return True
 	key = request.headers.get("X-API-Key") or request.args.get("key") or ""
 	return eq(key, cfg["api_key"])

 # ============================== ESTADO EN MEMORIA ==============================
 RT = {}

 def rt(f):
 	R = RT.get(f)
 	if R is None:
     	R = RT[f] = {"sensores": {}, "valvulas": {}, "bombas": {}, "pedidos": {}, "sectores": {},
                      "historico": deque(maxlen=600), "logs": deque(maxlen=200), "alertas": {},
                      "last_tick": time.time()}
 	return R

 def log(f, msg):
     rt(f)["logs"].append(datetime.now(TZ).strftime("%d/%m %H:%M:%S") + " - " + msg)

 def nuevo_v():
 	return {"estado": 0, "modo": "auto", "abierta_desde": None, "cerrando_hasta": None,
         	"litros_flow": 0.0, "litros_est": 0.0, "tiempo_acum": 0.0, "flow_ts": 0}

 def nuevo_b():
 	return {"estado": 0, "modo": "auto", "encendida_desde": None,
         	"litros_flow": 0.0, "litros_est": 0.0, "tiempo_acum": 0.0, "flow_ts": 0}

 def get_v(f, sid, vid):
 	return rt(f)["valvulas"].setdefault(f"{sid}_{vid}", nuevo_v())

 def get_b(f, bid):
 	return rt(f)["bombas"].setdefault(str(bid), nuevo_b())

 def sensores_frescos(f, sid):
 	now = time.time()
 	return [s for k, s in rt(f)["sensores"].items() if k.startswith(f"{sid}_") and now - s["ts"] <= STALE_S]

 def promedio(lst, k):
 	v = [s[k] for s in lst]
 	return sum(v) / len(v) if v else None

 def abrir(vs, now):
 	vs["cerrando_hasta"] = None
 	if vs["estado"] == 0:
     	vs["estado"] = 1
     	vs["abierta_desde"] = now
     	return True
 	return False

 def cerrar(vs, now):
 	if vs["estado"] == 1 and not vs["cerrando_hasta"]:
     	vs["cerrando_hasta"] = now + LEAD_S
     	return True
 	return False

 def tick(f, force=False):
 	"""Cerebro del riego. Se llama en cada request. Decide valvulas, bombas, integra litros y genera alarmas."""
 	cfg = cfg_de(f)
 	if not cfg:
     	return
 	R = rt(f)
 	now = time.time()
 	sect, bombas = cfg["sectores_config"], cfg["bombas"]

 	# asegurar actuadores existentes y limpiar los que ya no estan en la config
 	# (antes del throttle, para que existan desde el primer request)
 	validos_v = {f"{sid}_{v['id']}" for sid, sc in sect.items() for v in sc["valvulas"]}
 	for k in [k for k in R["valvulas"] if k not in validos_v]:
     	del R["valvulas"][k]
 	for sid, sc in sect.items():
     	for v in sc["valvulas"]:
         	get_v(f, sid, v["id"])
 	for b in bombas:
     	get_b(f, b["id"])

 	dt = now - R["last_tick"]
 	if dt < 0.5 and not force:
     	return
 	R["last_tick"] = now
 	dt = max(0.0, min(dt, 10.0))

 	# 1) cierres pendientes
 	for vs in R["valvulas"].values():
     	if vs["cerrando_hasta"] and now >= vs["cerrando_hasta"]:
         	vs["estado"], vs["abierta_desde"], vs["cerrando_hasta"] = 0, None, None

 	# 2) logica por sector / valvula
 	alertas = {}
 	for sid, sc in sect.items():
     	pl = PLANTAS.get(sc["planta"], PLANTAS["tomate"])
     	S = R["sectores"].setdefault(sid, {"bloqueo_hasta": 0})
     	fr = sensores_frescos(f, sid)
     	prom = promedio(fr, "humedad")
     	if prom is None:
         	alertas["sec" + sid] = f"Sector {sid}: sin datos frescos de sensores (riego automático detenido)"
     	if S["bloqueo_hasta"] > now:
         	alertas["blq" + sid] = f"Sector {sid}: riego AUTO bloqueado por exceder {MAX_RIEGO_S // 60} min (revisar fuga, sensor o caudal)"
     	for v in sc["valvulas"]:
         	vs = get_v(f, sid, v["id"])
         	nom = f"S{sid}-V{v['id']}"
         	abierta = vs["estado"] == 1 and not vs["cerrando_hasta"]
         	if vs["modo"] == "on":
             	if abrir(vs, now):
                 	log(f, f"{nom} ABRE (manual)")
             	if vs["abierta_desde"] and now - vs["abierta_desde"] > MAX_MANUAL_S:
                 	vs["modo"] = "auto"
                 	cerrar(vs, now)
                 	log(f, f"{nom} vuelve a AUTO (máximo manual {MAX_MANUAL_S // 3600} h)")
         	elif vs["modo"] == "off":
             	if abierta and cerrar(vs, now):
                 	log(f, f"{nom} CIERRA (manual)")
         	else:
             	if abierta:
                 	if prom is None:
                     	cerrar(vs, now)
                     	log(f, f"{nom} CIERRA: sin datos frescos de sensores")
                 	elif prom >= pl["off"]:
                     	cerrar(vs, now)
                     	log(f, f"{nom} CIERRA (AUTO) prom {prom:.1f}% >= {pl['off']}%")
                 	elif vs["abierta_desde"] and now - vs["abierta_desde"] > MAX_RIEGO_S:
                     	cerrar(vs, now)
                         S["bloqueo_hasta"] = now + BLOQUEO_S
                     	log(f, f"{nom} CIERRA: superó {MAX_RIEGO_S // 60} min, sector bloqueado {BLOQUEO_S // 60} min")
             	elif vs["estado"] == 0 and prom is not None and prom < pl["on"] and now >= S["bloqueo_hasta"]:
                 	abrir(vs, now)
                 	log(f, f"{nom} ABRE (AUTO) {pl['nombre']} prom {prom:.1f}% < {pl['on']}%")

 	# 3) bombas: solo se enciende si hay valvula abierta (hace >= LEAD_S) en SUS sectores
 	for b in bombas:
     	bs = get_b(f, b["id"])
     	servidos = [sid for sid, sc in sect.items() if sc["bomba_asignada"] == b["id"]]
     	vs_list = [get_v(f, sid, v["id"]) for sid in servidos for v in sect[sid]["valvulas"]]
     	necesita = any(v["estado"] == 1 and not v["cerrando_hasta"] and v["abierta_desde"]
                    	and now - v["abierta_desde"] >= LEAD_S for v in vs_list)
     	quiere = bs["modo"] == "on" or (bs["modo"] == "auto" and necesita)
     	if quiere and not bs["estado"]:
         	bs["estado"], bs["encendida_desde"] = 1, now
         	log(f, f"B{b['id']} ENCIENDE ({'manual' if bs['modo'] == 'on' else 'AUTO'})")
     	elif not quiere and bs["estado"]:
         	bs["estado"], bs["encendida_desde"] = 0, None
         	log(f, f"B{b['id']} APAGA")
     	abiertas = [v for v in vs_list if v["estado"] == 1]
     	for v in abiertas:
         	v["tiempo_acum"] += dt
     	if bs["estado"]:
         	lit = dt * BOMBA_CAUDAL[b["pulgadas"]] / 60.0
         	bs["litros_est"] += lit
         	bs["tiempo_acum"] += dt
         	for v in abiertas:  # el caudal de la bomba se reparte entre las valvulas abiertas
             	v["litros_est"] += lit / len(abiertas)
         	if b["flow"] != "no" and bs["encendida_desde"] and now - bs["encendida_desde"] > 20 and now - bs["flow_ts"] > 30:
             	alertas["bf" + str(b["id"])] = f"B{b['id']} encendida sin caudal (cebado, filtro tapado o sin agua)"

 	# 4) valvulas con flowmeter abiertas y bomba encendida sin caudal
 	for sid, sc in sect.items():
     	bs = get_b(f, sc["bomba_asignada"])
     	for v in sc["valvulas"]:
         	vs = get_v(f, sid, v["id"])
         	if (v["flow_present"] and vs["estado"] == 1 and bs["estado"] and vs["abierta_desde"]
                 	and now - vs["abierta_desde"] > 25 and now - vs["flow_ts"] > 30):
                 alertas[f"vf{sid}_{v['id']}"] = f"S{sid}-V{v['id']} abierta con bomba ON pero sin caudal (válvula trabada u obstruida)"
 	R["alertas"] = alertas

 # ============================== ANALISIS AGRONOMICO ==============================
 def estado_suelo(h, pl):
 	if h is None:
     	return "SIN DATOS"
 	if h < min(20, pl["on"]):
     	return "CRÍTICO"
 	if h < pl["on"]:
     	return "SECO"
 	if h <= pl["off"] + 5:
     	return "ÓPTIMO"
 	return "SATURADO"

 def alertas_planta(pl, m):
 	out = []
 	if m["ph"] is not None and m["ph"] > 0:
     	lo, hi = _rng(pl["ph"])
     	if lo is not None and (m["ph"] < lo or m["ph"] > hi):
             out.append({"nivel": "rojo", "msg": f"pH {m['ph']:.1f} fuera de rango (ideal {pl['ph']})"})
 	if m["temp"]:
     	lo, hi = _rng(pl["temp"])
     	if lo is not None and (m["temp"] < lo - 3 or m["temp"] > hi + 3):
             out.append({"nivel": "amarillo", "msg": f"Temp. suelo {m['temp']:.1f}°C fuera de rango (ideal {pl['temp']})"})
 	for nombre, c in (("N", "n"), ("P", "p"), ("K", "k")):
     	lo, hi = _rng(pl[c])
     	v = m[c]
     	if lo is None or v is None:
         	continue
     	if v < 0.5 * lo:
             out.append({"nivel": "amarillo", "msg": f"{nombre} {v:.0f} ppm bajo (ideal {pl[c]}): falta fertilización"})
     	elif v > 2 * hi:
             out.append({"nivel": "amarillo", "msg": f"{nombre} {v:.0f} ppm en exceso (ideal {pl[c]})"})
 	return out

 _clima = {"ts": 0, "data": None}

 def clima_actual():
 	now = time.time()
 	if _clima["data"] and now - _clima["ts"] < 600:
     	return _clima["data"]
 	data = {"temp": None, "hum": None, "viento": None, "desc": "Clima no configurado (definir OPENWEATHER_KEY)", "fuente": "n/d"}
 	key = os.environ.get("OPENWEATHER_KEY")
 	if key:
     	try:
         	q = urllib.parse.urlencode({"q": os.environ.get("WEATHER_QUERY", "San Juan,AR"), "appid": key,
                                         "units": "metric", "lang": "es"})
      	   with urllib.request.urlopen("https://api.openweathermap.org/data/2.5/weather?" + q, timeout=4) as r:
             	j = json.loads(r.read().decode())
         	data = {"temp": round(j["main"]["temp"], 1), "hum": j["main"]["humidity"],
                 	"viento": round(j["wind"]["speed"] * 3.6), "desc": j["weather"][0]["description"], "fuente": "OpenWeather"}
     	except Exception as e:
         	data["desc"] = "Clima no disponible (" + e.__class__.__name__ + ")"
 	if data["temp"] is None:
         data["reco"] = "Sin dato de clima"
 	elif data["temp"] >= 32:
     	data["reco"] = "Calor extremo: regar temprano o al atardecer, evitar 12-16 h"
 	elif data["temp"] <= 3:
     	data["reco"] = "Riesgo de helada: evitar riego nocturno"
 	else:
     	data["reco"] = "Riego normal"
 	_clima.update(ts=now, data=data)
 	return data

 def vista_sector(f, sid, sc, now):
 	R = rt(f)
 	pl = PLANTAS.get(sc["planta"], PLANTAS["tomate"])
 	fr = sensores_frescos(f, sid)
 	m = {k: promedio(fr, k) for k in ("humedad", "temp", "ph", "ec", "n", "p", "k")}
 	sensores = []
 	for d in range(1, sc["cant_sensores"] + 1):
     	s = R["sensores"].get(f"{sid}_{d}")
     	if s:
             sensores.append({"id": d, "datos": True, "humedad": s["humedad"], "temp": s["temp"], "ph": s["ph"],
                              "ec": s["ec"], "n": s["n"], "p": s["p"], "k": s["k"],
                              "edad": int(now - s["ts"]), "fresco": now - s["ts"] <= STALE_S})
     	else:
         	sensores.append({"id": d, "datos": False})
 	valvulas = []
 	for v in sc["valvulas"]:
     	vs = get_v(f, sid, v["id"])
     	valvulas.append({"id": v["id"], "pulgadas": v["pulgadas"], "flow_present": v["flow_present"],
                          "estado": vs["estado"], "cerrando": bool(vs["cerrando_hasta"]), "modo": vs["modo"],
                          "litros_flow": round(vs["litros_flow"], 2), "litros_est": round(vs["litros_est"], 2),
                          "tiempo_acum": round(vs["tiempo_acum"])})
 	S = R["sectores"].get(sid, {"bloqueo_hasta": 0})
 	return {"planta": sc["planta"], "planta_nombre": pl["nombre"], "emoji": pl["emoji"], "color": pl["color"],
         	"hum_ideal": pl["hum"], "ph_ideal": pl["ph"], "temp_ideal": pl["temp"], "n_ideal": pl["n"],
         	"p_ideal": pl["p"], "k_ideal": pl["k"], "nota": pl["nota"], "umbral_on": pl["on"], "umbral_off": pl["off"],
         	"cant_sensores": sc["cant_sensores"], "cant_valvulas": sc["cant_valvulas"], "bomba_asignada": sc["bomba_asignada"],
   	      "humedad_prom": m["humedad"], "temp": m["temp"], "ph": m["ph"], "ec": m["ec"], "n": m["n"], "p": m["p"], "k": m["k"],
         	"estado_suelo": estado_suelo(m["humedad"], pl), "bloqueado": S["bloqueo_hasta"] > now,
         	"sensores": sensores, "valvulas": valvulas, "alertas": alertas_planta(pl, m) if fr else []}

 def fmt(x, d=1):
 	return "-" if x is None else f"{x:.{d}f}"

 # ============================== HTML ==============================
 LOGIN_HTML = r"""
 <!DOCTYPE html><html lang="es"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OXITEM V13 Login</title>
 <style>body{margin:0;background:#0a0f1c;color:white;font-family:system-ui;display:flex;align-items:center;justify-content:center;min-height:100vh}
 .card{background:#1e293b;border:1px solid #334155;padding:32px;border-radius:20px;width:min(400px,90vw)}
 .logo{font-size:32px;font-weight:900} .logo span{color:#22c55e}
 input{width:100%;padding:12px;margin:8px 0;background:#0f172a;border:1px solid #334155;border-radius:10px;color:white;box-sizing:border-box}
 .btn{width:100%;padding:12px;background:#22c55e;color:black;border:none;border-radius:10px;font-weight:800;cursor:pointer}</style></head><body>
 <div class="card"><div class="logo">OX<span>ITEM</span> V13</div><div style="color:#94a3b8;font-size:11px">RIEGO INTELIGENTE MULTI-FINCA</div>
 <form method="POST" action="/login" style="margin-top:16px"><input name="username" placeholder="Usuario / finca" required autocomplete="username"><input name="password" type="password" placeholder="Contraseña" required autocomplete="current-password"><button class="btn">INGRESAR →</button></form>
 {% if allow_register %}<a href="/register" style="color:#22c55e;display:block;text-align:center;margin-top:12px;font-size:13px;text-decoration:none">Crear finca nueva</a>{% endif %}
 {% if error %}<div style="color:#f87171;background:rgba(248,113,113,0.1);padding:8px;border-radius:8px;margin-top:10px;font-size:12px">{{error}}</div>{% endif %}
 </div></body></html>
 """

 REGISTER_HTML = r"""
 <!DOCTYPE html><html lang="es"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OXITEM V13 Registro</title>
 <style>body{margin:0;background:#0f172a;color:white;font-family:system-ui;padding:20px}
 .card{background:#1e293b;border:1px solid #334155;padding:24px;border-radius:18px;max-width:850px;margin:0 auto}
 input,select{width:100%;padding:12px;margin:6px 0;background:#0f172a;border:1px solid #334155;border-radius:10px;color:white;box-sizing:border-box}
 label{font-size:11px;color:#94a3b8}
 .grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
 .btn{width:100%;padding:14px;background:#22c55e;color:black;border:none;border-radius:12px;font-weight:800;cursor:pointer;margin-top:12px;font-size:14px}</style></head><body>
 <div class="card"><h2>OX<span style="color:#22c55e">ITEM</span> V13 - Nueva finca</h2>
 <p style="color:#94a3b8;font-size:12px">Paso 1: define terreno, cantidad de sectores y bombas. Paso 2: en Config Terreno defines planta, sensores, válvulas y bomba de cada sector.</p>
 <form method="POST" action="/register">
 <div class="grid"><div><label>Usuario (letras, números y _)</label><input name="username" placeholder="finca_demo" required pattern="[A-Za-z0-9_]{3,30}"></div><div><label>Contraseña (mín. 6)</label><input name="password" type="password" minlength="6" required></div></div>
 <label>Ubicación</label><input name="ubicacion" value="Villa Krause, Rawson, San Juan" required>
 <div class="grid"><div><label>Largo del terreno (m)</label><input name="largo" type="number" min="1" value="100" required></div><div><label>Ancho del terreno (m)</label><input name="ancho" type="number" min="1" value="100" required></div></div>
 <div class="grid"><div><label>Cantidad de sectores (1-20)</label><input name="sectores" type="number" min="1" max="20" value="3" required></div><div><label>Cantidad de bombas (1-10)</label><input name="bombas" type="number" min="1" max="10" value="2" required></div></div>
 <div class="grid"><div><label>Tipo de bomba</label><select name="bomba_pulgadas"><option value="0.5" selected>1/2" 25 L/min</option><option value="0.75">3/4" 45 L/min</option><option value="1">1" 80 L/min</option><option value="1.25">1 1/4" 120 L/min</option></select></div><div><label>Válvula por defecto</label><select name="valvula_ppal"><option value="0.5">1/2"</option><option value="0.75">3/4"</option><option value="1" selected>1"</option></select></div></div>
 <button class="btn">CREAR FINCA →</button>
 </form></div></body></html>
 """

 CONFIG_HTML = r"""
 <!DOCTYPE html><html lang="es"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OXITEM V13 Config</title>
 <style>
 body{margin:0;background:#080e1c;color:#e2e8f0;font-family:system-ui;padding:16px}
 .card{background:#162032;border:1px solid #2a3a52;border-radius:20px;padding:20px;margin:12px auto;max-width:1100px}
 input,select{padding:10px;margin:4px;background:#0f172a;border:1px solid #334155;border-radius:10px;color:white;max-width:100%}
 .btn{padding:10px 16px;background:#22c55e;color:black;border:none;border-radius:10px;font-weight:800;cursor:pointer}
 .sector-btn{width:100%;text-align:left;padding:14px;background:#1e293b;border:1px solid #334155;border-radius:12px;color:white;font-weight:700;cursor:pointer;margin:6px 0;display:flex;justify-content:space-between;gap:8px}
 .sector-btn:hover{background:#2a3a52}
 .sector-panel{display:none;background:#0f172a;border:1px solid #1e293b;border-radius:14px;padding:16px;margin:0 0 12px 0;border-left:4px solid #22c55e}
 .valv-box{background:#162032;border:1px dashed #334155;border-radius:10px;padding:10px;margin:8px 0}
 .mono{font-size:10px;color:#64748b;font-family:monospace;word-break:break-all}
 .g2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
 label{font-size:11px;color:#94a3b8}
 </style></head><body>
 <div class="card">
 <h2>OX<span style="color:#22c55e">ITEM</span> V13 Config - {{username}}</h2>
 <a href="/dashboard?finca={{username}}" style="color:#22c55e">← Volver al dashboard</a>
 <p style="color:#94a3b8;font-size:12px">Autentícate como admin para editar. Cada sector se despliega para elegir planta, bomba, sensores y válvulas. La bomba de cada sector se define SOLO acá (campo "bomba asignada").</p>
 <form id="adminAuth"><input id="adminUser" placeholder="admin" autocomplete="username"><input id="adminPass" type="password" placeholder="Clave admin" autocomplete="current-password"><button class="btn" type="submit">Autenticar</button></form>
 <div id="configArea" style="display:none">
 <div>Sectores: <input id="nSect" type="number" min="1" max="20" style="width:70px"> Bombas: <input id="nBomb" type="number" min="1" max="10" style="width:70px"> <button class="btn" type="button" onclick="aplicarTotales()">Aplicar</button></div>
 <h3 style="color:#22c55e">Bombas</h3><div id="bombasCfg"></div>
 <h3 style="color:#22c55e">Sectores</h3><div id="sectoresList"></div>
 <button class="btn" onclick="guardar()" style="margin-top:20px;padding:14px 28px;font-size:15px">💾 Guardar configuración</button><span id="msg" style="margin-left:12px"></span>
 </div></div>
 <script>const FINCA={{ username|tojson }}; const API_KEY={{ api_key|tojson }}; let F={{ finca|tojson }}; const PL={{ plantas|tojson }};</script>
 <script>
 {% raw %}
 const $=id=>document.getElementById(id);
 const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const BOMBA_OPC={"0.5":'1/2" 25 L/min',"0.75":'3/4" 45 L/min',"1":'1" 80 L/min',"1.25":'1 1/4" 120 L/min'};
 const FLOW_OPC={"no":"Sin flow (solo estimado)","yf_s201":'YF-S201 1/2" 450 p/L',"fs400a":'FS400A 1" 360 p/L'};
 let abiertos=new Set(); let listo=false;

 document.getElementById('adminAuth').addEventListener('submit',async e=>{
   e.preventDefault();
   const r=await fetch('/api/admin_auth',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user:$('adminUser').value,pass:$('adminPass').value})});
   const j=await r.json().catch(()=>({}));
   if(j.ok){ $('configArea').style.display='block'; listo=true; render(); } else alert('Admin incorrecto');
 });

 function optPlantas(sel){
   const g={}; Object.entries(PL).forEach(([k,p])=>{(g[p.grupo]=g[p.grupo]||[]).push([k,p]);});
   return Object.entries(g).map(([n,l])=>'<optgroup label="'+esc(n)+'">'+l.map(([k,p])=>
 	`<option value="${k}" ${k===sel?'selected':''}>${p.emoji} ${esc(p.nombre)} - Hum ${p.hum} (ON&lt;${p.on}% OFF&ge;${p.off}%) pH ${p.ph}</option>`).join('')+'</optgroup>').join('');
 }
 function opts(obj,sel){return Object.entries(obj).map(([k,t])=>`<option value="${k}" ${k===sel?'selected':''}>${esc(t)}</option>`).join('');}
 function sectoresDe(b){const l=Object.entries(F.sectores_config).filter(([i,s])=>s.bomba_asignada===b).map(([i])=>'S'+i);return l.length?l.join(', '):'ninguno';}

 function read(){
   if(!listo||!$('bombasCfg').children.length) return;
   const bombas=[];
   for(let b=1;b<=F.bombas_totales;b++){ const p=$('bp_'+b); if(!p) return; bombas.push({id:b,pulgadas:p.value,flow:$('bf_'+b).value}); }
   F.bombas=bombas;
   for(let i=1;i<=F.sectores;i++){
 	const pl=$('pl_'+i); if(!pl) continue;
 	const s=F.sectores_config[i]||(F.sectores_config[i]={});
 	s.planta=pl.value;
     s.bomba_asignada=Math.min(F.bombas_totales,Math.max(1,+$('ba_'+i).value||1));
     s.cant_sensores=Math.min(20,Math.max(1,+$('cs_'+i).value||1));
 	const cv=Math.min(10,Math.max(1,+$('cv_'+i).value||1)); s.cant_valvulas=cv;
 	const vs=[]; for(let v=1;v<=cv;v++){ const vp=$('vp_'+i+'_'+v); vs.push({id:v,pulgadas:vp?vp.value:'1',flow_present:vp?$('vf_'+i+'_'+v).value==='true':false}); }
 	s.valvulas=vs;
   }
 }
 function cambio(){ read(); render(); }
 function toggle(i){ abiertos.has(i)?abiertos.delete(i):abiertos.add(i); $('panel_'+i).style.display=abiertos.has(i)?'block':'none'; $('arr_'+i).textContent=abiertos.has(i)?'▲ Cerrar':'▼ Configurar'; }

 function aplicarTotales(){
   read();
   const ns=Math.min(20,Math.max(1,+$('nSect').value||1)), nb=Math.min(10,Math.max(1,+$('nBomb').value||1));
   while(F.bombas.length<nb) F.bombas.push({id:F.bombas.length+1,pulgadas:'0.5',flow:'no'});
   F.bombas.length=nb;
   for(let i=1;i<=ns;i++) if(!F.sectores_config[i]) F.sectores_config[i]={planta:'tomate',cant_sensores:1,cant_valvulas:1,valvulas:[{id:1,pulgadas:'1',flow_present:false}],bomba_asignada:1};
   Object.keys(F.sectores_config).forEach(k=>{ if(+k>ns) delete F.sectores_config[k]; else if(F.sectores_config[k].bomba_asignada>nb) F.sectores_config[k].bomba_asignada=nb; });
   F.sectores=ns; F.bombas_totales=nb; render();
 }

 function render(){
   $('nSect').value=F.sectores; $('nBomb').value=F.bombas_totales;
   $('bombasCfg').innerHTML=F.bombas.map(b=>`<div class="valv-box"><b>Bomba B${b.id} - BOMBA_ID=${b.id}</b><br>
 	Tipo: <select id="bp_${b.id}">${opts(BOMBA_OPC,b.pulgadas)}</select> Flowmeter: <select id="bf_${b.id}">${opts(FLOW_OPC,b.flow)}</select><br>
 	<span class="mono">Alimenta: ${sectoresDe(b.id)}</span><br>
 	<span class="mono">ESP: FINCA_ID="${esc(FINCA)}" API_KEY="${esc(API_KEY)}" BOMBA_ID=${b.id}</span></div>`).join('');
   let html='';
   for(let i=1;i<=F.sectores;i++){
 	const s=F.sectores_config[i]; const p=PL[s.planta]||PL.tomate;
 	let vh='';
 	for(let v=1;v<=s.cant_valvulas;v++){
   	const c=s.valvulas[v-1]||{pulgadas:'1',flow_present:false};
   	vh+=`<div class="valv-box"><b>Electroválvula S${i}-V${v} - VALVULA_ID=${v}</b><br>
     	Tipo: <select id="vp_${i}_${v}">${opts({"0.5":'1/2"',"0.75":'3/4"',"1":'1"'},c.pulgadas)}</select>
     	Flowmeter: <select id="vf_${i}_${v}"><option value="false" ${!c.flow_present?'selected':''}>NO (solo estimado)</option><option value="true" ${c.flow_present?'selected':''}>SÍ (YF-S201)</option></select><br>
     	<span class="mono">ESP: FINCA_ID="${esc(FINCA)}" API_KEY="${esc(API_KEY)}" SECTOR_ID=${i} VALVULA_ID=${v}</span></div>`;
 	}
 	let sh=''; for(let d=1;d<=s.cant_sensores;d++) sh+=`S${i}-D${d}: <span class="mono">FINCA_ID="${esc(FINCA)}" API_KEY="${esc(API_KEY)}" SECTOR_ID=${i} SENSOR_ID=${d}</span><br>`;
 	const ab=abiertos.has(i);
 	html+=`<button type="button" class="sector-btn" onclick="toggle(${i})"><span>📁 Sector ${i} • ${esc(p.nombre)} ${p.emoji} • ${s.cant_sensores} sensores • ${s.cant_valvulas} válvulas • B${s.bomba_asignada}</span><span id="arr_${i}">${ab?'▲ Cerrar':'▼ Configurar'}</span></button>
 	<div class="sector-panel" id="panel_${i}" style="display:${ab?'block':'none'}">
   	<div class="g2"><div><label>Planta</label><br><select id="pl_${i}" style="width:100%" onchange="cambio()">${optPlantas(s.planta)}</select></div>
   	<div><label>Bomba que alimenta este sector</label><br><select id="ba_${i}" style="width:100%" onchange="cambio()">${Array.from({length:F.bombas_totales},(_,b)=>b+1).map(b=>`<option value="${b}" ${b===s.bomba_asignada?'selected':''}>Bomba B${b}</option>`).join('')}</select></div></div>
   	<div class="g2"><div><label>Cantidad de sensores (1-20)</label><br><input id="cs_${i}" type="number" min="1" max="20" value="${s.cant_sensores}" style="width:100%" onchange="cambio()"></div>
   	<div><label>Cantidad de electroválvulas (1-10)</label><br><input id="cv_${i}" type="number" min="1" max="10" value="${s.cant_valvulas}" style="width:100%" onchange="cambio()"></div></div>
   	<div style="margin-top:12px"><b style="font-size:12px;color:#22c55e">Electroválvulas</b>${vh}</div>
   	<div class="valv-box"><b style="font-size:12px;color:#22c55e">Sensores 7en1</b><div style="margin-top:6px;font-size:11px">${sh}</div></div>
 	</div>`;
   }
   $('sectoresList').innerHTML=html;
 }
 async function guardar(){
   read();
   const r=await fetch('/api/config_terreno',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({finca:FINCA,bombas:F.bombas,sectores_config:F.sectores_config})});
   const j=await r.json().catch(()=>({}));
   $('msg').textContent=j.ok?'✅ Guardado':'Error: '+(j.error||r.status);
   if(j.ok){ F.bombas=j.bombas; F.sectores_config=j.sectores_config; F.sectores=j.sectores; F.bombas_totales=j.bombas_totales; render(); }
 }
 {% endraw %}
 </script></body></html>
 """

 DASHBOARD_HTML = r"""
 <!DOCTYPE html><html lang="es"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OXITEM V13 - {{username}}</title>
 <style>
 body{margin:0;background:#080e1c;color:#e2e8f0;font-family:system-ui}
 .header{background:#0f172a;border-bottom:1px solid #1e293b;padding:14px 20px;display:flex;justify-content:space-between;flex-wrap:wrap;gap:12px;position:sticky;top:0;z-index:10}
 .logo{font-weight:900;font-size:24px;color:white} .logo span{color:#22c55e}
 .card{background:#162032;border:1px solid #2a3a52;border-radius:20px;padding:20px;margin:14px;box-shadow:0 8px 24px rgba(0,0,0,0.3)}
 .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(420px,100%),1fr));gap:16px;padding:0 14px}
 .grid .card{margin:0}
 .val{font-size:34px;font-weight:900} .small{font-size:12px;color:#94a3b8;line-height:1.4}
 .btn{padding:8px 12px;border-radius:10px;border:none;font-weight:800;cursor:pointer;font-size:12px;margin:3px}
 .btn-dark{background:#0f172a;color:white;border:1px solid #334155} .btn-green{background:linear-gradient(135deg,#22c55e,#16a34a);color:black} .btn-red{background:linear-gradient(135deg,#ef4444,#dc2626);color:white}
 .badge{padding:5px 10px;border-radius:12px;font-size:11px;font-weight:800;white-space:nowrap}
 .row{display:flex;justify-content:space-between;flex-wrap:wrap;gap:6px;align-items:center}
 .log{background:#0f172a;border:1px solid #1e293b;color:#86efac;padding:12px;border-radius:12px;font-family:monospace;font-size:11px;max-height:260px;overflow:auto}
 .data-row{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:8px 0}
 .data-box{background:#0f172a;border:1px solid #1e293b;border-radius:12px;padding:10px;text-align:center}
 .data-box .label{font-size:10px;color:#64748b}
 .valv-card,.sens{background:#0f172a;border:1px solid #1e293b;border-radius:12px;padding:10px;margin:8px 0;border-left:4px solid #22c55e}
 .sens{border-left-width:1px;font-size:11px}
 .al-r{background:rgba(248,113,113,0.15);border:1px solid rgba(248,113,113,0.3);color:#f87171;padding:8px;border-radius:8px;font-size:11px;margin:4px 0}
 .al-y{background:rgba(251,191,36,0.15);border:1px solid rgba(251,191,36,0.3);color:#fbbf24;padding:8px;border-radius:8px;font-size:11px;margin:4px 0}
 #rep{font-size:11px;white-space:pre-wrap;max-height:400px;overflow:auto;background:#0f172a;padding:12px;border-radius:12px;margin-top:8px}
 </style></head><body>
 <div class="header">
 <div><div class="logo">OX<span>ITEM</span> V13</div><div class="small">{{finca.ubicacion}} • {{finca.largo}}x{{finca.ancho}} m ({{finca.m2}} m²) • {{finca.sectores}} sectores • {{finca.bombas_totales}} bombas <span id="conn"></span></div></div>
 <div><a href="/config_terreno?finca={{username}}" style="background:#22c55e;color:black;padding:10px 16px;border-radius:10px;text-decoration:none;font-weight:800;font-size:13px">⚙️ Config terreno</a> <a href="/logout" style="color:#94a3b8;margin-left:8px">Salir</a></div>
 </div>

 <div class="card" style="background:linear-gradient(135deg,rgba(34,197,94,0.12),rgba(6,182,212,0.08));border-color:rgba(34,197,94,0.3)">
 <div class="row"><div><b>💧 CONSUMO</b><div class="small">Flow real vs estimado (solo válvulas con flowmeter) y total estimado por bombas</div></div><div id="consumoResumen" style="font-size:13px;text-align:right">Cargando...</div></div>
 </div>
 <div id="alertasSis" style="margin:0 14px"></div>
 <div id="sectoresContainer" class="grid"></div>
 <div id="bombasContainer" class="grid" style="margin-top:16px"></div>

 <div class="grid" style="margin-top:16px">
 <div class="card"><b>📈 Historial de humedad (VWC %)</b><canvas id="cHum" width="600" height="220" style="width:100%"></canvas><div id="leyenda" class="small"></div></div>
 <div class="card"><b>Control global y clima</b>
 <div style="margin:10px 0"><button class="btn btn-dark" onclick="cmd({device:'todo_auto',modo:'auto'})">Todo en AUTO</button> <button class="btn btn-red" onclick="if(confirm('Cerrar todas las válvulas y apagar bombas (manual)?'))parar()">⛔ PARO TOTAL</button> <button class="btn btn-dark" onclick="pedirTodos()">🔄 Pedir dato a todos los sensores</button></div>
 <div id="clima" style="background:#0f172a;padding:12px;border-radius:12px;font-size:12px">Cargando clima...</div>
 <div style="margin-top:12px"><a href="https://www.google.com/maps/search/{{finca.ubicacion|urlencode}}" target="_blank" rel="noopener" style="color:#22c55e">📍 {{finca.ubicacion}} - Abrir Maps →</a></div>
 </div></div>

 <div class="card"><b>📋 Reporte agronómico por sector</b><div id="rep"></div></div>
 <div class="card"><b>LOGS</b><div id="log" class="log"></div></div>

 <script>const FINCA={{ username|tojson }};</script>
 <script>
 {% raw %}
 const $=id=>document.getElementById(id);
 const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const f1=(x,d=1)=>x==null?'–':(+x).toFixed(d);
 let last=null;
 async function post(url,body){const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});return r.json().catch(()=>({}));}
 async function cmd(b){await post('/api/comando',Object.assign({finca:FINCA},b));load();}
 async function parar(){await cmd({device:'todas_valvulas',modo:'off'});await cmd({device:'todas_bombas',modo:'off'});}
 async function pedirSensor(s,d){await post('/api/pedir_dato_sensor',{finca:FINCA,sector:s,sensor_id:d});}
 async function pedirTodos(){
   if(!last) return;
   for(const [sid,sec] of Object.entries(last.sectores)) for(let d=1;d<=sec.cant_sensores;d++){await pedirSensor(sid,d);await new Promise(r=>setTimeout(r,500));}
   $('conn').textContent=' • pedidos enviados, respuesta en 5-10 s';
 }
 function colorEstado(e){return e==='SECO'||e==='CRÍTICO'?'#f87171':e==='SATURADO'?'#38bdf8':e==='ÓPTIMO'?'#22c55e':'#94a3b8';}
 function box(l,ideal,act,d,u){return `<div class="data-box"><div class="label">${l} IDEAL</div><div style="font-size:14px;font-weight:800">${esc(ideal)}</div><div class="small">Actual ${act==null?'–':f1(act,d)+u}</div></div>`;}

 function cardSector(sid,s){
   const col=colorEstado(s.estado_suelo);
   const vh=s.valvulas.map(v=>`<div class="valv-card" style="border-left-color:${v.estado?'#22c55e':'#334155'}">
 	<div class="row"><b>S${sid}-V${v.id}</b><span class="small">VALVULA_ID=${v.id} • ${esc(v.pulgadas)}" • flow ${v.flow_present?'SÍ':'estimado'}</span>
 	<span class="badge" style="background:${v.estado?'#22c55e20':'#1e293b'};color:${v.estado?'#22c55e':'#64748b'}">${v.estado?(v.cerrando?'CERRANDO':'ABIERTA'):'CERRADA'} • ${v.modo.toUpperCase()}</span></div>
 	<div class="small">💧 ${f1(v.litros_flow)} L flow / ${f1(v.litros_est)} L est • ⏱ ${f1(v.tiempo_acum/60)} min</div>
 	<div><button class="btn btn-green" onclick="cmd({device:'valvula_id',sector:${sid},valvula_id:${v.id},modo:'on'})">Abrir</button><button class="btn btn-red" onclick="cmd({device:'valvula_id',sector:${sid},valvula_id:${v.id},modo:'off'})">Cerrar</button><button class="btn btn-dark" onclick="cmd({device:'valvula_id',sector:${sid},valvula_id:${v.id},modo:'auto'})">AUTO</button></div></div>`).join('');
   const sh=s.sensores.map(x=>`<div class="sens row"><span><b>S${sid}-D${x.id}</b> SENSOR_ID=${x.id}<br>${x.datos?`Humedad ${f1(x.humedad)}% VWC • T ${f1(x.temp)}°C • pH ${f1(x.ph,2)} • EC ${f1(x.ec,0)} • NPK ${f1(x.n,0)}/${f1(x.p,0)}/${f1(x.k,0)} • hace ${x.edad}s ${x.fresco?'':'⚠️ SIN DATO FRESCO'}`:'Sin datos'}</span><button class="btn btn-dark" onclick="pedirSensor(${sid},${x.id})">Pedir dato</button></div>`).join('');
   const al=s.alertas.map(a=>`<div class="${a.nivel==='rojo'?'al-r':'al-y'}">⚠️ ${esc(a.msg)}</div>`).join('');
   return `<div class="card" style="border-left:6px solid ${esc(s.color)}">
 	<div class="row"><b style="font-size:16px">SECTOR ${sid} • ${esc(s.planta_nombre.toUpperCase())} ${s.emoji} • B${s.bomba_asignada}</b><span class="badge" style="background:${col}20;color:${col}">${esc(s.estado_suelo)}${s.bloqueado?' • BLOQUEADO':''}</span></div>
 	<div class="val" style="color:${col}">Humedad: ${f1(s.humedad_prom)}<span style="font-size:14px">% VWC</span> <span class="small">ON&lt;${s.umbral_on}% OFF&ge;${s.umbral_off}%</span></div>
 	${al}
 	<div style="background:#0f172a;border-radius:12px;padding:10px;margin:10px 0"><b class="small" style="color:#22c55e">IDEALES PARA ${esc(s.planta_nombre.toUpperCase())}</b>
 	<div class="data-row">${box('HUM',s.hum_ideal,s.humedad_prom,1,'%')}${box('TEMP',s.temp_ideal,s.temp,1,'°C')}${box('pH',s.ph_ideal,s.ph,2,'')}</div>
 	<div class="data-row">${box('N',s.n_ideal,s.n,0,' ppm')}${box('P',s.p_ideal,s.p,0,' ppm')}${box('K',s.k_ideal,s.k,0,' ppm')}</div>
 	${s.nota?`<div class="small">Nota: ${esc(s.nota)}</div>`:''}</div>
 	<b class="small">SENSORES</b>${sh}<b class="small">VÁLVULAS (cada una con su ID)</b>${vh}</div>`;
 }
 function cardBomba(b){
   return `<div class="card" style="border-left:4px solid ${b.estado?'#22c55e':'#334155'}">
 	<div class="row"><b>Bomba B${b.id} - BOMBA_ID=${b.id}</b><span class="badge" style="background:${b.estado?'#22c55e20':'#1e293b'};color:${b.estado?'#22c55e':'#64748b'}">${b.estado?'ON':'OFF'} • ${b.modo.toUpperCase()}</span></div>
 	<div class="small">${esc(b.pulgadas)}" ${b.lpm} L/min • ${esc(b.flow_model)} • alimenta: ${b.sectores.length?b.sectores.map(x=>'S'+x).join(', '):'ninguno'}<br>💧 ${f1(b.litros_flow)} L flow / ${f1(b.litros_est)} L est • ⏱ ${f1(b.tiempo_acum/60)} min</div>
 	<div><button class="btn btn-green" onclick="cmd({device:'bomba_id',bomba_id:${b.id},modo:'on'})">Forzar ON</button><button class="btn btn-red" onclick="cmd({device:'bomba_id',bomba_id:${b.id},modo:'off'})">Forzar OFF</button><button class="btn btn-dark" onclick="cmd({device:'bomba_id',bomba_id:${b.id},modo:'auto'})">AUTO</button></div></div>`;
 }
 function chart(j){
   const c=$('cHum'),x=c.getContext('2d'); x.clearRect(0,0,c.width,c.height);
   x.strokeStyle='#1e293b'; x.fillStyle='#64748b'; x.font='10px system-ui';
   for(let p=0;p<=100;p+=25){const y=200-p*1.8;x.beginPath();x.moveTo(30,y);x.lineTo(590,y);x.stroke();x.fillText(p+'%',2,y+3);}
   const h=j.historico||[]; if(h.length<2){$('leyenda').textContent='Aún sin suficientes datos';return;}
   const t0=h[0].ts,t1=h[h.length-1].ts,span=Math.max(t1-t0,1),ser={};
   h.forEach(p=>{const k=p.sector+'-'+p.sensor;(ser[k]=ser[k]||[]).push(p);});
   let leg='';
   Object.entries(ser).forEach(([k,pts])=>{
 	const col=(j.sectores[pts[0].sector]||{}).color||'#22c55e'; x.strokeStyle=col; x.beginPath();
 	pts.forEach((p,i)=>{const px=30+(p.ts-t0)/span*560,py=200-Math.min(100,Math.max(0,p.humedad))*1.8;i?x.lineTo(px,py):x.moveTo(px,py);}); x.stroke();
 	leg+=`<span style="color:${esc(col)}">■ S${esc(k.replace('-','-D'))}</span> `;
   });
   $('leyenda').innerHTML=leg+' • últimos '+Math.round(span/60)+' min';
 }
 function render(j){
   const c=j.consumo;
   $('consumoResumen').innerHTML=`Flow ${f1(c.litros_flow)} L / Est. comparable ${f1(c.litros_est_comparable)} L • Dif ${c.diferencia}% ${esc(c.alerta)}<br><span class="small">Total estimado (bombas): ${f1(c.litros_est_total)} L</span>`;
   $('alertasSis').innerHTML=(j.alertas_sistema||[]).map(a=>`<div class="al-r">🚨 ${esc(a)}</div>`).join('');
   $('sectoresContainer').innerHTML=Object.entries(j.sectores).map(([sid,s])=>cardSector(sid,s)).join('');
   $('bombasContainer').innerHTML=j.bombas.map(cardBomba).join('');
   chart(j);
   const cl=j.clima; $('clima').innerHTML=`<b>🌤️ ${cl.temp==null?'–':cl.temp+'°C'}</b> • ${cl.hum==null?'–':cl.hum+'% hum'} • viento ${cl.viento==null?'–':cl.viento+' km/h'}<br>${esc(cl.desc)}<br><b style="color:#22c55e">${esc(cl.reco)}</b>`;
   $('rep').textContent=j.reporte;
   $('log').innerHTML=(j.logs||[]).slice(-25).reverse().map(l=>`<div>${esc(l)}</div>`).join('');
 }
 async function load(){
   try{
 	const r=await fetch('/api/estado?finca='+encodeURIComponent(FINCA));
 	if(r.status===401||r.status===403){location='/login';return;}
 	const j=await r.json(); last=j; render(j); $('conn').textContent='';
   }catch(e){ $('conn').textContent=' • ⚠️ sin conexión'; }
 }
 load(); setInterval(load,3000);
 {% endraw %}
 </script></body></html>
 """

 # ============================== RUTAS WEB ==============================
 @app.route('/')
 def idx():
 	return redirect('/dashboard' if 'user' in session else '/login')

 @app.route('/healthz')
 def healthz():
 	return "ok"

 @app.route('/login', methods=['GET', 'POST'])
 def login():
 	err = None
 	if request.method == 'POST':
     	u = request.form.get('username', '').strip()
     	p = request.form.get('password', '')
     	if eq(u, ADMIN_USER) and eq(p, ADMIN_PASS):
         	session.clear(); session['user'] = ADMIN_USER
         	return redirect('/dashboard')
     	for ku, vu in db["users"].items():
         	if ku.lower() == u.lower() and check_password_hash(vu.get("password_hash", ""), p):
             	session.clear(); session['user'] = ku
             	return redirect('/dashboard')
     	time.sleep(1)  # frena fuerza bruta basica
     	err = "Usuario o contraseña incorrectos"
 	return render_template_string(LOGIN_HTML, error=err, allow_register=ALLOW_REGISTER)

 @app.route('/register', methods=['GET', 'POST'])
 def register():
 	if not ALLOW_REGISTER and not es_admin():
     	return "Registro deshabilitado", 403
 	if request.method == 'POST':
     	u = request.form.get('username', '').strip()
     	p = request.form.get('password', '')
     	if not re.fullmatch(r"[A-Za-z0-9_]{3,30}", u):
         	return "Usuario: 3-30 caracteres (letras, números, _)", 400
     	if len(p) < 6:
         	return "Contraseña mínima: 6 caracteres", 400
     	with LOCK:
         	if u.lower() == ADMIN_USER.lower() or any(k.lower() == u.lower() for k in db["users"]):
             	return f"Usuario {u} ya existe", 400
         	largo = clamp(request.form.get('largo'), 1, 100000, 10)
         	ancho = clamp(request.form.get('ancho'), 1, 100000, 10)
         	ns = clamp(request.form.get('sectores'), 1, 20, 3)
         	nb = clamp(request.form.get('bombas'), 1, 10, 2)
         	bp = request.form.get('bomba_pulgadas', '0.5')
         	vp = request.form.get('valvula_ppal', '1')
         	bombas, sect = limpiar([{"id": i, "pulgadas": bp} for i in range(1, nb + 1)],
                                    {str(i): {"valvulas": [{"id": 1, "pulgadas": vp}]} for i in range(1, ns + 1)}, nb, ns)
         	db["users"][u] = {"password_hash": generate_password_hash(p), "finca": {
             	"ubicacion": request.form.get('ubicacion', 'Villa Krause, Rawson, San Juan')[:120],
             	"largo": largo, "ancho": ancho, "m2": largo * ancho, "sectores": ns, "bombas_totales": nb,
             	"bombas": bombas, "sectores_config": sect, "api_key": secrets.token_urlsafe(16)}}
         	guardar_db()
         	log(u, f"NUEVA FINCA {ns} sectores {nb} bombas")
     	if not es_admin():
         	session.clear(); session['user'] = u
 	    return redirect('/config_terreno?finca=' + u)
 	return render_template_string(REGISTER_HTML)

 @app.route('/logout')
 def logout():
 	session.clear()
 	return redirect('/login')

 @app.route('/dashboard')
 def dashboard():
 	if 'user' not in session:
     	return redirect('/login')
 	user = session['user']
 	if user == ADMIN_USER and not request.args.get('finca'):
     	filas = "".join(
         	"<div style='background:#1e293b;border:1px solid #334155;padding:12px;border-radius:12px;margin:8px'><b>%s</b> %s • %s sectores • %s bombas "
         	"<a href='/dashboard?finca=%s' style='color:#22c55e'>Ver</a> • <a href='/config_terreno?finca=%s' style='color:#22c55e'>Config</a></div>"
         	% (esc_html(k), esc_html(v['finca']['ubicacion']), v['finca']['sectores'], v['finca']['bombas_totales'], esc_html(k), esc_html(k))
         	for k, v in db["users"].items()) or "No hay fincas"
     	return ("<body style='background:#0a0f1c;color:white;font-family:system-ui;padding:20px'><h1>OXITEM V13 ADMIN - %d fincas</h1>%s<br>"
             	"<a href='/register' style='color:#22c55e'>+ Crear finca</a> • <a href='/logout' style='color:#94a3b8'>Salir</a></body>" % (len(db["users"]), filas))
 	fu = request.args.get('finca', user)
 	if not puede(fu):
     	return redirect('/login')
 	return render_template_string(DASHBOARD_HTML, username=fu, finca=cfg_de(fu))

 def esc_html(s):
 	return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;")

 @app.route('/config_terreno')
 def config_terreno():
 	if 'user' not in session:
     	return redirect('/login')
 	fu = request.args.get('finca', session['user'])
 	if not puede(fu):
     	return "No autorizado", 403
 	cfg = cfg_de(fu)
 	pub = {k: v for k, v in cfg.items() if k != "api_key"}
 	return render_template_string(CONFIG_HTML, username=fu, finca=pub, plantas=PLANTAS, api_key=cfg["api_key"])

 # ============================== API USUARIO (sesion) ==============================
 @app.route('/api/admin_auth', methods=['POST'])
 def admin_auth():
 	d = request.get_json(silent=True) or {}
 	if 'user' in session and eq(str(d.get('user', '')).strip(), ADMIN_USER) and eq(str(d.get('pass', '')), ADMIN_PASS):
     	session['cfg_ok'] = True
     	return jsonify({"ok": True})
 	time.sleep(1)
 	return jsonify({"ok": False}), 401

 @app.route('/api/config_terreno', methods=['POST'])
 def api_config():
 	d = request.get_json(silent=True) or {}
 	f = str(d.get('finca', '')).strip()
 	if not puede(f):
     	return jsonify({"ok": False, "error": "no autorizado"}), 403
 	if not session.get('cfg_ok'):
     	return jsonify({"ok": False, "error": "autenticá como admin primero"}), 403
 	with LOCK:
     	cfg = cfg_de(f)
     	bin_ = d.get('bombas', cfg["bombas"])
     	sin = d.get('sectores_config', cfg["sectores_config"])
     	cfg["bombas"], cfg["sectores_config"] = limpiar(bin_, sin, len(bin_) if isinstance(bin_, list) else None,
                                  	                   len(sin) if isinstance(sin, dict) else None)
     	cfg["bombas_totales"] = len(cfg["bombas"])
     	cfg["sectores"] = len(cfg["sectores_config"])
     	R = rt(f)
     	validos_s = {f"{sid}_{x}" for sid, sc in cfg["sectores_config"].items() for x in range(1, sc["cant_sensores"] + 1)}
     	R["sensores"] = {k: v for k, v in R["sensores"].items() if k in validos_s}
     	R["bombas"] = {k: v for k, v in R["bombas"].items() if int(k) <= cfg["bombas_totales"]}
     	R["sectores"] = {k: v for k, v in R["sectores"].items() if k in cfg["sectores_config"]}
     	guardar_db()
     	log(f, f"CONFIG guardada: {cfg['sectores']} sectores, {cfg['bombas_totales']} bombas")
     	tick(f, force=True)
 	return jsonify({"ok": True, "bombas": cfg["bombas"], "sectores_config": cfg["sectores_config"],
                 	"sectores": cfg["sectores"], "bombas_totales": cfg["bombas_totales"]})

 @app.route('/api/pedir_dato_sensor', methods=['POST'])
 def pedir_dato():
 	d = request.get_json(silent=True) or {}
 	f = str(d.get('finca', '')).strip()
 	if not puede(f):
     	return jsonify({"ok": False, "error": "no autorizado"}), 403
 	sid = str(ent(d.get('sector'), 1, 20, 0))
 	did = ent(d.get('sensor_id'), 1, 20, 0)
 	sc = cfg_de(f)["sectores_config"].get(sid)
 	if not sc or not (1 <= did <= sc["cant_sensores"]):
     	return jsonify({"ok": False, "error": "sensor no configurado"}), 404
 	with LOCK:
         rt(f)["pedidos"][f"{sid}_{did}"] = time.time()
 	return jsonify({"ok": True, "pedido": f"S{sid}-D{did}"})

 @app.route('/api/sensores_pendientes')
 def sensores_pendientes():
 	f = request.args.get('finca', '').strip()
 	if not puede(f):
     	return jsonify({"error": "no autorizado"}), 403
 	now = time.time()
 	with LOCK:
     	return jsonify({"pendientes": [k for k, t in rt(f)["pedidos"].items() if now - t <= PEDIDO_VALIDO_S]})

 @app.route('/api/comando', methods=['POST'])
 def comando():
 	d = request.get_json(silent=True) or {}
 	f = str(d.get('finca', '')).strip()
 	if not puede(f):
     	return jsonify({"ok": False, "error": "no autorizado"}), 403
 	modo = d.get('modo')
 	if modo not in ("on", "off", "auto"):
     	modo = {1: "on", 0: "off", "1": "on", "0": "off"}.get(d.get('estado'))
 	if modo is None:
     	return jsonify({"ok": False, "error": "modo invalido"}), 400
 	dev = d.get('device', '')
 	with LOCK:
     	R = rt(f)
     	tick(f, force=True)  # asegura que existan los actuadores
     	if dev == 'valvula_id':
         	sid = str(ent(d.get('sector'), 1, 20, 0))
         	vid = ent(d.get('valvula_id'), 1, 10, 0)
         	vs = R["valvulas"].get(f"{sid}_{vid}")
         	if not vs:
             	return jsonify({"ok": False, "error": "valvula no existe"}), 404
         	vs["modo"] = modo
         	log(f, f"CMD S{sid}-V{vid} -> {modo.upper()}")
     	elif dev == 'bomba_id':
         	bs = R["bombas"].get(str(ent(d.get('bomba_id'), 1, 10, 0)))
         	if not bs:
             	return jsonify({"ok": False, "error": "bomba no existe"}), 404
         	bs["modo"] = modo
         	log(f, f"CMD B{d.get('bomba_id')} -> {modo.upper()}")
     	elif dev in ('todas_valvulas', 'todo_auto'):
         	for v in R["valvulas"].values():
             	v["modo"] = modo
         	if dev == 'todo_auto':
             	for b in R["bombas"].values():
                 	b["modo"] = modo
             	for S in R["sectores"].values():
                     S["bloqueo_hasta"] = 0
         	log(f, f"CMD {dev} -> {modo.upper()}")
     	elif dev == 'todas_bombas':
         	for b in R["bombas"].values():
             	b["modo"] = modo
         	log(f, f"CMD todas_bombas -> {modo.upper()}")
     	else:
         	return jsonify({"ok": False, "error": "device invalido"}), 400
     	tick(f, force=True)
 	return jsonify({"ok": True})

 @app.route('/api/estado')
 def estado():
 	f = request.args.get('finca', '').strip()
 	if not puede(f):
     	return jsonify({"error": "no autorizado"}), 403
 	clima = clima_actual()  # fuera del lock (puede tardar hasta 4 s)
 	with LOCK:
     	cfg = cfg_de(f)
     	R = rt(f)
     	tick(f, force=True)
     	now = time.time()
     	sect = {sid: vista_sector(f, sid, sc, now) for sid, sc in cfg["sectores_config"].items()}
     	bombas = []
     	for b in cfg["bombas"]:
         	bs = get_b(f, b["id"])
             bombas.append({"id": b["id"], "pulgadas": b["pulgadas"], "lpm": BOMBA_CAUDAL[b["pulgadas"]],
                            "flow": b["flow"], "flow_model": FLOW_SPECS[b["flow"]]["modelo"],
                            "sectores": [int(sid) for sid, sc in cfg["sectores_config"].items() if sc["bomba_asignada"] == b["id"]],
                            "estado": bs["estado"], "modo": bs["modo"], "litros_flow": round(bs["litros_flow"], 2),
                            "litros_est": round(bs["litros_est"], 2), "tiempo_acum": round(bs["tiempo_acum"])})
     	# consumo: se compara flow real vs estimado SOLO en valvulas que tienen flowmeter
     	flow = est_cmp = 0.0
     	for sid, s in sect.items():
         	for v in s["valvulas"]:
             	if v["flow_present"]:
                 	flow += v["litros_flow"]
                 	est_cmp += v["litros_est"]
     	est_total = sum(b["litros_est"] for b in bombas)
     	dif = abs(flow - est_cmp) / est_cmp * 100 if est_cmp > 0 else 0
     	if est_total == 0 and flow == 0:
         	alerta = "Sin riego"
     	elif est_cmp == 0:
         	alerta = "Sin válvulas con flowmeter"
     	else:
         	alerta = "✅ OK" if dif <= 20 else "⚠️ Diferencia >20% (fuga, obstrucción o caudal mal calibrado)"
     	# reporte
     	lin = []
     	for sid, s in sect.items():
         	al = " | ".join("⚠️ " + a["msg"] for a in s["alertas"])
         	vt = ", ".join("V%d %s%s" % (v["id"], v["pulgadas"] + '"', " OPEN" if v["estado"] else " CLOSED") for v in s["valvulas"])
         	lin.append("● Sector %s %s %s (%d sensores, %d válvulas, B%d): Humedad %s%% VWC %s | ON<%d%% OFF>=%d%% | Ideal hum %s pH %s T %s N %s P %s K %s\n"
                    	"   Actual: T %s pH %s N %s P %s K %s\n   Válvulas: %s%s%s\n" %
                    	(sid, s["emoji"], s["planta_nombre"], s["cant_sensores"], s["cant_valvulas"], s["bomba_asignada"],
                         fmt(s["humedad_prom"]), s["estado_suelo"], s["umbral_on"], s["umbral_off"], s["hum_ideal"], s["ph_ideal"],
                         s["temp_ideal"], s["n_ideal"], s["p_ideal"], s["k_ideal"], fmt(s["temp"]), fmt(s["ph"], 2),
                         fmt(s["n"], 0), fmt(s["p"], 0), fmt(s["k"], 0), vt, ("\n   " + al) if al else "",
                     	("\n   Nota: " + s["nota"]) if s["nota"] else ""))
     	hist = [h for h in list(R["historico"])[-300:]]
     	return jsonify({"finca_id": f, "sectores": sect, "bombas": bombas,
                         "consumo": {"litros_flow": round(flow, 2), "litros_est_comparable": round(est_cmp, 2),
                                     "litros_est_total": round(est_total, 2), "diferencia": round(dif, 1), "alerta": alerta},
            	         "alertas_sistema": list(R["alertas"].values()), "historico": hist, "logs": list(R["logs"])[-30:],
                         "reporte": "\n".join(lin) or "Sin sectores", "clima": clima})

 # ============================== API DISPOSITIVOS (ESP32, X-API-Key) ==============================
 @app.route('/api/datos', methods=['POST'])
 def datos():
 	j = request.get_json(force=True, silent=True) or {}
 	f = str(j.get('finca_id') or j.get('finca') or '').strip()
 	if not dev_ok(f):
     	return jsonify({"ok": False, "error": "no autorizado"}), 401
 	tipo = j.get('tipo', 'sensor')
 	now = time.time()
 	with LOCK:
     	cfg = cfg_de(f)
     	R = rt(f)
     	if tipo == 'sensor':
         	sid = str(ent(j.get('sector_id'), 1, 20, 0))
         	did = ent(j.get('sensor_id', j.get('dispositivo_id')), 1, 20, 0)
         	sc = cfg["sectores_config"].get(sid)
         	if not sc or not (1 <= did <= sc["cant_sensores"]):
             	return jsonify({"ok": False, "error": "sensor no configurado"}), 404
         	h = num(j.get('humedad'), -1)
         	if not (0 <= h <= 100):
             	return jsonify({"ok": False, "error": "humedad invalida"}), 400
             R["sensores"][f"{sid}_{did}"] = {
             	"humedad": h, "temp": num(j.get('temperatura')), "ph": num(j.get('ph')), "ec": num(j.get('conductividad')),
             	"n": num(j.get('nitrogeno')), "p": num(j.get('fosforo')), "k": num(j.get('potasio')), "ts": now}
             R["historico"].append({"ts": now, "sector": sid, "sensor": did, "humedad": h})
             R["pedidos"].pop(f"{sid}_{did}", None)
     	elif tipo == 'valvula_flow':
         	sid = str(ent(j.get('sector_id'), 1, 20, 0))
         	vid = ent(j.get('valvula_id'), 1, 10, 0)
         	vs = R["valvulas"].get(f"{sid}_{vid}")
         	if vs is None:
             	return jsonify({"ok": False, "error": "valvula no configurada"}), 404
         	vs["litros_flow"] += max(0.0, num(j.get('litros_flow')))
         	vs["flow_ts"] = now
     	elif tipo == 'bomba_flow':
         	bs = R["bombas"].get(str(ent(j.get('bomba_id'), 1, 10, 0)))
         	if bs is None:
             	return jsonify({"ok": False, "error": "bomba no configurada"}), 404
         	bs["litros_flow"] += max(0.0, num(j.get('litros_flow')))
         	bs["flow_ts"] = now
     	else:
         	return jsonify({"ok": False, "error": "tipo invalido"}), 400
     	tick(f)
 	return jsonify({"ok": True})

 @app.route('/api/estado_sensor')
 def estado_sensor():
 	f = request.args.get('finca', '').strip()
 	if not dev_ok(f):
     	return jsonify({"pedir": False, "error": "no autorizado"}), 401
 	key = "%s_%s" % (ent(request.args.get('sector'), 1, 20, 0), ent(request.args.get('sensor_id'), 1, 20, 0))
 	with LOCK:
     	P = rt(f)["pedidos"]
     	ts = P.pop(key, None)  # se entrega una sola vez
     	return jsonify({"pedir": bool(ts and time.time() - ts <= PEDIDO_VALIDO_S)})

 @app.route('/api/riego')
 def riego():
 	"""Valvula: ?finca=&sector=&valvula_id=   Bomba: ?finca=&bomba_id=  (consultado por los ESP32)"""
 	f = request.args.get('finca', '').strip()
 	if not dev_ok(f):
     	return jsonify({"ok": False, "error": "no autorizado"}), 401
 	with LOCK:
     	cfg = cfg_de(f)
     	R = rt(f)
     	tick(f)
     	if request.args.get('bomba_id'):
         	bid = ent(request.args.get('bomba_id'), 1, 10, 0)
         	bs = R["bombas"].get(str(bid))
         	if bs is None:
             	return jsonify({"ok": False, "bomba": False, "error": "bomba no configurada"})
         	return jsonify({"ok": True, "bomba": bool(bs["estado"]), "bomba_id": bid, "modo": bs["modo"]})
     	sid = str(ent(request.args.get('sector'), 1, 20, 0))
     	vid = ent(request.args.get('valvula_id'), 1, 10, 0)
     	vs = R["valvulas"].get(f"{sid}_{vid}")
     	if vs is None:
         	return jsonify({"ok": False, "valvula": False, "error": "valvula no configurada"})
     	sc = cfg["sectores_config"][sid]
     	pl = PLANTAS[sc["planta"]]
     	return jsonify({"ok": True, "valvula": bool(vs["estado"]), "valvula_id": vid, "sector": int(sid),
                         "bomba_id": sc["bomba_asignada"], "modo": vs["modo"],
                         "umbral_on": pl["on"], "umbral_off": pl["off"], "planta": pl["nombre"]})

 @app.route('/api/debug')
 def debug():
 	if not es_admin():
     	return jsonify({"error": "solo admin"}), 403
 	with LOCK:
     	return jsonify({"db_file": DB_FILE, "fincas": list(db["users"].keys()), "require_key": REQUIRE_KEY,
                     	"rt": {f: {"valvulas": R["valvulas"], "bombas": R["bombas"], "sensores": R["sensores"],
                                    "pedidos": R["pedidos"], "alertas": R["alertas"]} for f, R in RT.items()}})

 if __name__ == '__main__':
 	port = int(os.environ.get("PORT", 10000))
 	print(f"OXITEM V13 iniciando en puerto {port}", flush=True)
 	app.run(host='0.0.0.0', port=port, debug=False)
  

