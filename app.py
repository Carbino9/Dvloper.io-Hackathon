from flask import Flask, jsonify, render_template_string
import pandas as pd
from datetime import datetime
import os

app = Flask(__name__)
CSV_PATH = "transactions.csv"

EXPECTED_COLS = [
    'transaction_id', 'ssn', 'cc_num', 'first_name', 'last_name', 'gender',
    'street', 'city', 'state', 'zip', 'home_lat', 'home_long', 'city_population',
    'job', 'dob', 'account_number', 'trans_num', 'trans_date', 'trans_time',
    'unix_time', 'category', 'amt', 'merchant', 'merch_lat', 'merch_long',
    'is_fraud', 'local_timestamp'
]

def safe_float(x):
    if x is None:
        return None
    try:
        s = str(x).strip().replace(',', '.')
        return float(s)
    except Exception:
        return None

def load_data():
    if not os.path.isfile(CSV_PATH):
        return pd.DataFrame()
    try:
        df = pd.read_csv(CSV_PATH, dtype=str, keep_default_na=False)
    except Exception:
        return pd.DataFrame()

    if 'local_timestamp' not in df.columns and len(df.columns) == len(EXPECTED_COLS):
        df.columns = EXPECTED_COLS

    if 'is_fraud' in df.columns:
        df['is_fraud'] = pd.to_numeric(df['is_fraud'].astype(str).str.extract(r'(\d+)')[0],
                                       errors='coerce').fillna(0).astype(int)
    else:
        df['is_fraud'] = 0

    df['local_timestamp'] = pd.to_datetime(df.get('local_timestamp'), errors='coerce')

    if 'dob' in df.columns:
        df['dob'] = pd.to_datetime(df['dob'], errors='coerce')
        df['age'] = (pd.Timestamp.now() - df['dob']).dt.days // 365
    else:
        df['age'] = None

    df['merch_lat_f'] = df['merch_lat'].apply(safe_float) if 'merch_lat' in df.columns else None
    df['merch_long_f'] = df['merch_long'].apply(safe_float) if 'merch_long' in df.columns else None
    return df

# ---------- METRICI ----------
def get_fraud_count(hours=2):
    df = load_data()
    if df.empty:
        return 0
    cutoff = pd.Timestamp.now() - pd.Timedelta(hours=hours)
    mask = (df['is_fraud'] == 1) & (df['local_timestamp'] >= cutoff)
    return int(mask.sum())

def get_fraud_ratio_5min():
    df = load_data()
    if df.empty:
        return 0.0
    cutoff = pd.Timestamp.now() - pd.Timedelta(minutes=5)
    recent = df[df['local_timestamp'] >= cutoff]
    if recent.empty:
        return 0.0
    total = len(recent)
    frauds = (recent['is_fraud'] == 1).sum()
    return round((frauds / total) * 100, 2)

def get_top_categories(n=5):
    df = load_data()
    if df.empty or 'category' not in df.columns:
        return []
    top = df[df['is_fraud'] == 1]['category'].value_counts().head(n)
    return [{"category": k, "count": int(v)} for k, v in top.items()]

def get_age_distribution():
    df = load_data()
    if df.empty or 'age' not in df.columns:
        return []
    df_fraud = df[df['is_fraud'] == 1].copy()
    if df_fraud.empty:
        return []
    bins = [0, 25, 35, 45, 55, 120]
    labels = ["<25", "25-34", "35-44", "45-54", "55+"]
    df_fraud['age_group'] = pd.cut(df_fraud['age'], bins=bins, labels=labels, right=False)
    counts = df_fraud['age_group'].value_counts().reindex(labels, fill_value=0)
    return [{"age_group": g, "count": int(c)} for g, c in counts.items()]

def get_top_merchant_locations(n=5):
    df = load_data()
    if df.empty:
        return []
    df_fraud = df[df['is_fraud'] == 1]
    if df_fraud.empty:
        return []
    df_coords = df_fraud[(df_fraud['merch_lat_f'].notna()) & (df_fraud['merch_long_f'].notna())]
    if df_coords.empty:
        return []
    grouped = df_coords.groupby(['merchant', 'merch_lat_f', 'merch_long_f']).size().reset_index(name='count')
    top = grouped.sort_values(by='count', ascending=False).head(n)
    return [
        {"merchant": r['merchant'], "count": int(r['count']),
         "merch_lat": float(r['merch_lat_f']), "merch_long": float(r['merch_long_f'])}
        for _, r in top.iterrows()
    ]

def get_top_states(n=5):
    df = load_data()
    if df.empty or 'state' not in df.columns:
        return []
    df_fraud = df[df['is_fraud'] == 1]
    top = df_fraud['state'].value_counts().head(n)
    return [{"state": s, "count": int(c)} for s, c in top.items()]

# ---------- ENDPOINTURI ----------
@app.route("/alerts_count")
def alerts_count():
    count = get_fraud_count(hours=2)
    ratio = get_fraud_ratio_5min()
    return jsonify({
        "fraud_count": count,
        "fraud_ratio_5min": ratio,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

@app.route("/stats")
def stats():
    return jsonify({
        "top_categories": get_top_categories(),
        "age_distribution": get_age_distribution(),
        "top_merchant_locations": get_top_merchant_locations(),
        "top_states": get_top_states(),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

# ---------- PAGINA ----------
PAGE_HTML = """
<!doctype html>
<html lang="ro">
<head>
<meta charset="utf-8">
<title>Dashboard fraude</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
body{font-family:Arial;background:#fafafa;margin:0;padding:0;text-align:center;transition:background-color 0.3s ease}
.flash-red{background-color:#ff0000 !important;}
header{padding:20px}
h1{font-size:30px;margin:0}
#count{font-size:72px;color:#e53935}
#ratio{font-size:32px;color:#3949ab;margin-top:10px}
.layout{display:flex;flex-wrap:wrap;gap:24px;justify-content:center;padding:20px}
.panel{background:#fff;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,0.1);padding:16px}
#map{width:700px;height:420px;border-radius:8px}
canvas{border-radius:8px}
</style>
</head>
<body>
<header>
<h1>Alerte de fraudă în ultimele 2 ore</h1>
<div id="count">0</div>
<div id="ratio">0% fraude în ultimele 5 minute</div>
<div id="timestamp" style="color:#666;margin-top:6px">Actualizare...</div>
</header>

<div class="layout">
  <div class="panel">
    <h3>Top 5 categorii fraude</h3>
    <canvas id="catChart" width="420" height="300"></canvas>
  </div>
  <div class="panel">
    <h3>Distribuția pe grupe de vârstă</h3>
    <canvas id="ageChart" width="320" height="300"></canvas>
  </div>
  <div class="panel">
    <h3>Top 5 state cu cele mai multe fraude</h3>
    <canvas id="stateChart" width="420" height="300"></canvas>
  </div>
  <div class="panel" style="min-width:720px">
    <h3>Top 5 locații POS (merchant) după număr de fraude</h3>
    <div id="map"></div>
  </div>
</div>

<script>
const POLL_MS = 2000;
let catChart, ageChart, stateChart, map, markersLayer;

async function initMap(){
  map = L.map('map');
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{
    attribution:'&copy; OpenStreetMap'
  }).addTo(map);
  markersLayer = L.layerGroup().addTo(map);
  map.setView([20,0],2);
}

function updateMap(data){
  markersLayer.clearLayers();
  const pts=[];
  for(const d of data){
    if(!d.merch_lat||!d.merch_long) continue;
    const lat=parseFloat(d.merch_lat),lon=parseFloat(d.merch_long);
    if(isNaN(lat)||isNaN(lon)) continue;
    const m=L.marker([lat,lon]).bindPopup(`<b>${d.merchant}</b><br>Fraude: ${d.count}`);
    markersLayer.addLayer(m);pts.push([lat,lon]);
  }
  if(pts.length>0) map.fitBounds(L.latLngBounds(pts).pad(0.2));
  else map.setView([20,0],2);
}

// ---------- ÎNCEPUT MODIFICĂRI ----------

function initCharts() {
    // Inițializează graficele o singură dată, cu date goale
    const emptyData = { labels: [], datasets: [{ data: [] }] };
    const options = {
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true } }
    };

    catChart = new Chart(document.getElementById('catChart'), {
        type: 'bar',
        data: emptyData,
        options: options
    });

    ageChart = new Chart(document.getElementById('ageChart'), {
        type: 'bar',
        data: emptyData,
        options: options
    });

    stateChart = new Chart(document.getElementById('stateChart'), {
        type: 'bar',
        data: emptyData,
        options: options
    });
}

let lastFraudCount = 0;

async function refresh(){
  const c=await fetch('/alerts_count').then(r=>r.json());
  const currentCount = c.fraud_count;
  document.getElementById('count').textContent=c.fraud_count;
  document.getElementById('ratio').textContent=c.fraud_ratio_5min+'% fraude în ultimele 5 minute';
  document.getElementById('timestamp').textContent='Actualizat: '+new Date(c.timestamp).toLocaleTimeString();

  // 💥 Efect vizual când numărul crește
  if (currentCount > lastFraudCount) {
    document.body.classList.add('flash-red');
    setTimeout(() => document.body.classList.remove('flash-red'), 150);
  }
  lastFraudCount = currentCount;

  const s=await fetch('/stats').then(r=>r.json());
  const catL=s.top_categories.map(x=>x.category),catV=s.top_categories.map(x=>x.count);
  const ageL=s.age_distribution.map(x=>x.age_group),ageV=s.age_distribution.map(x=>x.count);
  const stateL=s.top_states.map(x=>x.state),stateV=s.top_states.map(x=>x.count);
  
  // În loc să distrugem graficele, le actualizăm datele
  catChart.data.labels = catL;
  catChart.data.datasets[0].data = catV;
  catChart.data.datasets[0].backgroundColor = '#42a5f5';
  catChart.update();

  ageChart.data.labels = ageL;
  ageChart.data.datasets[0].data = ageV;
  ageChart.data.datasets[0].backgroundColor = '#66bb6a';
  ageChart.update();

  stateChart.data.labels = stateL;
  stateChart.data.datasets[0].data = stateV;
  stateChart.data.datasets[0].backgroundColor = '#ef5350';
  stateChart.update();
  
  updateMap(s.top_merchant_locations||[]);
}

window.addEventListener('load',async()=>{
  await initMap();
  initCharts(); // Apelăm funcția de inițializare a graficelor
  await refresh(); // Așteptăm prima actualizare a datelor
  setInterval(refresh,POLL_MS); // Pornim intervalul
});

// ---------- SFÂRȘIT MODIFICĂRI ----------
</script>
</body></html>
"""

@app.route("/")
def index():
    return render_template_string(PAGE_HTML)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)