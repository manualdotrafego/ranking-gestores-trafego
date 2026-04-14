#!/usr/bin/env /Library/Frameworks/Python.framework/Versions/3.14/bin/python3
"""
gerar_relatorios_igor.py
Gera relatórios HTML + screenshots para todas as clínicas do Gestor Igor Teixeira
com Status=ON no Notion, para os últimos 30 dias (padrão na tela: 15 dias).
"""

import os, re, sys, json, time, base64, subprocess, unicodedata
import http.server, threading, requests
from datetime import date, timedelta
from pathlib import Path
from dotenv import load_dotenv

# ─── CONFIG ───────────────────────────────────────────────────────────────────
BASE_DIR  = Path("/Users/alexrangelalves/Downloads/Conexão mtds")
LOGO_PATH = Path("/Users/alexrangelalves/Downloads/logo sem fundo dbout.png")

load_dotenv(dotenv_path=BASE_DIR / ".env")

META_TOKEN    = os.getenv("META_ACCESS_TOKEN")
META_BASE     = "https://graph.facebook.com/v21.0"
NOTION_TOKEN  = os.getenv("NOTION_TOKEN", "")
NOTION_DB_ID  = "115e97e8e1368028b3c1fe0a465f8b07"
NOTION_BASE   = "https://api.notion.com/v1"
GH_PAGES_BASE = "https://manualdotrafego.github.io/ranking-gestores-trafego"
LOCAL_PORT    = 8769

# ─── CONTAS IGOR ──────────────────────────────────────────────────────────────
IGOR_VALID = {
    "5648874101844136",  # CT03 - Guaramirim
    "449000287288780",   # CT02 - Unaí
    "1181454115989018",  # CT03 - Fhilipe
    "1191525622298805",  # CT05 - DBOUT 02
    "412153471621510",   # CT02 - MJOLNIR
    "391009870578696",   # AQC 00
    "1583196522529565",  # CT01 - DRACO
    "1329276834986407",  # Orthodontic Aparecida de Goiânia
    "566170923166415",   # Ortomais 1.1
    "1132321672289497",  # Brasil Odontologia Rio do Sul
}

# IDs com dígito faltando no Notion → ID real correto
IGOR_ID_FIX = {
    "41215347621510":  "412153471621510",   # MJOLNIR
    "11915262298805":  "1191525622298805",  # DBOUT 02
}

# ─── HELPERS ──────────────────────────────────────────────────────────────────
def norm(t):
    t = unicodedata.normalize("NFKD", t)
    return "".join(c for c in t if not unicodedata.combining(c)).lower()

def slugify(t):
    t = norm(t)
    t = re.sub(r"[^\w\s-]", "", t)
    return re.sub(r"[\s\-]+", "_", t).strip("_")

def meta_get(path, params=None):
    p = {"access_token": META_TOKEN, "limit": 500}
    if params: p.update(params)
    r = requests.get(f"{META_BASE}{path}", params=p, timeout=30)
    r.raise_for_status()
    return r.json()

def notion_headers():
    return {"Authorization": f"Bearer {NOTION_TOKEN}",
            "Notion-Version": "2022-06-28", "Content-Type": "application/json"}

# ─── EXTRACT ACCOUNT ID ───────────────────────────────────────────────────────
def extract_igor_account(ca_value: str) -> str | None:
    if not ca_value:
        return None

    # 1) Primeiro verifica se tem algum ID corrigível (14 dígitos conhecidos)
    for bad, good in IGOR_ID_FIX.items():
        if bad in ca_value:
            return good

    # 2) Extrai todas as sequências de dígitos
    for seq in re.findall(r"\d+", ca_value):
        if seq in IGOR_VALID:
            return seq
        # Busca substring: seq dentro de algum ID válido
        for vid in IGOR_VALID:
            if seq in vid and len(seq) >= 12:
                return vid

    return None

# ─── NOTION ───────────────────────────────────────────────────────────────────
def notion_get_igor_pages():
    pages = []
    has_more, start_cursor = True, None
    while has_more:
        body = {
            "page_size": 100,
            "filter": {
                "and": [
                    {"property": "Gestor de Tráfego", "select": {"equals": "Igor Teixeira"}},
                    {"property": "Status", "status": {"equals": "ON"}},
                ]
            },
        }
        if start_cursor:
            body["start_cursor"] = start_cursor
        r = requests.post(f"{NOTION_BASE}/databases/{NOTION_DB_ID}/query",
                          headers=notion_headers(), json=body, timeout=30)
        r.raise_for_status()
        data = r.json()
        pages.extend(data.get("results", []))
        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")
    return pages

def parse_page(page):
    props = page.get("properties", {})
    def rt(k): return "".join(t.get("plain_text","") for t in props.get(k,{}).get("rich_text",[])).strip()

    clinic = ""
    for k, v in props.items():
        if v.get("type") == "title":
            clinic = "".join(t.get("plain_text","") for t in v.get("title",[])).strip()
            if clinic: break

    ca = rt("C.A") or rt("CA") or rt("Conta de Anúncio")
    return {
        "page_id":    page["id"],
        "clinic_name": clinic,
        "ca_field":   ca,
        "account_id": extract_igor_account(ca),
    }

# ─── META API ─────────────────────────────────────────────────────────────────
def fetch_campaigns(acct_id):
    camps = []
    for status in (["ACTIVE"], ["PAUSED","CAMPAIGN_PAUSED"]):
        try:
            r = meta_get(f"/act_{acct_id}/campaigns", {
                "fields": "id,name,effective_status",
                "effective_status": json.dumps(status), "limit": 500
            })
            camps.extend(r.get("data", []))
            time.sleep(0.3)
        except Exception as e:
            print(f"  [WARN] camps {acct_id}: {e}")
    return camps

def find_campaign(campaigns, clinic_name, hint=""):
    if not campaigns: return None
    active = [c for c in campaigns if c.get("effective_status") == "ACTIVE"]
    pool   = active if active else campaigns

    if hint:
        hn = norm(hint)
        for c in pool:
            if hn in norm(c["name"]): return c

    num_m = re.match(r"^(\d+)", clinic_name.strip())
    if num_m:
        num = num_m.group(1)
        for c in pool:
            if num in c["name"]: return c

    words = [w for w in re.split(r"[\s\-_/]+", clinic_name) if len(w) > 3 and not w.isdigit()]
    for w in words:
        wn = norm(w)
        for c in pool:
            if wn in norm(c["name"]): return c

    return pool[0] if pool else None

def fetch_daily_insights(camp_id, since, until):
    try:
        r = meta_get(f"/{camp_id}/insights", {
            "fields": "date_start,spend,actions,cost_per_action_type,impressions,cpm,ctr",
            "time_range": json.dumps({"since": since, "until": until}),
            "time_increment": "1", "limit": 50,
        })
        time.sleep(0.3)
        daily = []
        for row in r.get("data", []):
            msgs = 0
            for a in row.get("actions", []):
                if a.get("action_type") in (
                    "onsite_conversion.messaging_first_reply",
                    "onsite_conversion.total_messaging_connection",
                    "onsite_conversion.messaging_conversation_started_7d",
                ):
                    try: msgs += int(float(a["value"]))
                    except: pass
            spend = float(row.get("spend", 0))
            impr  = int(row.get("impressions", 0))
            cpm   = float(row.get("cpm", 0))
            ctr   = float(row.get("ctr", 0))
            daily.append({
                "date": row["date_start"],
                "spend": round(spend, 2),
                "msgs": msgs,
                "cost_msg": round(spend/msgs, 2) if msgs > 0 else 0.0,
                "impr": impr, "cpm": round(cpm, 2), "ctr": round(ctr, 2),
            })
        daily.sort(key=lambda x: x["date"], reverse=True)
        return daily
    except Exception as e:
        print(f"  [ERROR] insights {camp_id}: {e}")
        return []

# ─── HTML ─────────────────────────────────────────────────────────────────────
def load_logo():
    try: return base64.b64encode(open(LOGO_PATH,"rb").read()).decode()
    except Exception as e: print(f"[WARN] logo: {e}"); return ""

LOGO_B64 = load_logo()

def generate_html(clinic_name, campaign, account_id, daily):
    camp_name    = campaign.get("name","—")
    camp_status  = campaign.get("effective_status","UNKNOWN")
    status_color = "#42b72a" if camp_status == "ACTIVE" else "#e2a01d"
    status_label = "Ativa" if camp_status == "ACTIVE" else "Pausada"
    gen_date     = date.today().strftime("%d/%m/%Y")
    daily_json   = json.dumps(daily, ensure_ascii=False)
    logo_html    = f'<img class="dbout-logo" src="data:image/png;base64,{LOGO_B64}" alt="Dbout"/>' if LOGO_B64 else ""

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Relatório · {clinic_name} · Meta Ads</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css">
<script src="https://cdn.jsdelivr.net/npm/flatpickr"></script>
<script src="https://cdn.jsdelivr.net/npm/flatpickr/dist/l10n/pt.js"></script>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Inter',sans-serif;background:#f0f2f5;color:#1c1e21;font-size:14px}}
.page{{max-width:920px;margin:0 auto;padding:24px 16px 48px}}
.header{{background:#fff;border-radius:8px;padding:14px 22px;margin-bottom:18px;
        display:flex;align-items:center;justify-content:space-between;
        box-shadow:0 1px 3px rgba(0,0,0,.12)}}
.fb-wordmark{{font-size:22px;font-weight:800;color:#1877f2;line-height:1}}
.fb-sub{{font-size:11px;color:#606770;font-weight:500}}
.dbout-logo{{height:44px;width:auto;object-fit:contain}}
.camp-info{{background:#fff;border-radius:8px;padding:13px 20px;margin-bottom:16px;
           box-shadow:0 1px 3px rgba(0,0,0,.1);display:flex;align-items:center;gap:12px}}
.camp-dot{{width:10px;height:10px;border-radius:50%;background:{status_color};flex-shrink:0}}
.camp-name{{font-size:13px;font-weight:600;color:#1c1e21}}
.camp-status{{font-size:11px;color:{status_color};font-weight:700}}
.camp-account{{font-size:11px;color:#8a8d91;margin-left:auto;white-space:nowrap}}
.date-range-wrap{{display:flex;justify-content:center;margin-bottom:18px;gap:8px;flex-wrap:wrap}}
.date-input-wrap{{position:relative}}
.date-icon{{position:absolute;left:12px;top:50%;transform:translateY(-50%);pointer-events:none;color:#606770}}
#dateRangeInput{{background:#fff;border:1.5px solid #dddfe2;border-radius:8px;
  padding:9px 16px 9px 36px;font-size:13px;font-weight:600;color:#1c1e21;
  font-family:'Inter',sans-serif;cursor:pointer;min-width:280px;text-align:center;
  box-shadow:0 1px 3px rgba(0,0,0,.08);transition:border-color .15s;outline:none}}
#dateRangeInput:hover,#dateRangeInput:focus{{border-color:#1877f2}}
.period-shortcuts{{display:flex;gap:6px;flex-wrap:wrap;justify-content:center}}
.ps-btn{{padding:6px 14px;border-radius:20px;font-size:11px;font-weight:600;cursor:pointer;
        border:1.5px solid #dddfe2;background:#fff;color:#606770;
        font-family:'Inter',sans-serif;transition:all .15s}}
.ps-btn:hover{{border-color:#1877f2;color:#1877f2}}
.ps-btn.active{{background:#1877f2;color:#fff;border-color:#1877f2}}
.kpi-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:18px}}
.kpi-card{{background:#fff;border-radius:8px;padding:18px 22px;
          box-shadow:0 1px 3px rgba(0,0,0,.12);border-top:3px solid #1877f2}}
.kpi-label{{font-size:10px;font-weight:700;color:#1877f2;text-transform:uppercase;
           letter-spacing:.6px;margin-bottom:6px}}
.kpi-value{{font-size:26px;font-weight:800;color:#1c1e21;line-height:1}}
.kpi-sub{{font-size:11px;color:#8a8d91;margin-top:5px}}
.section-card{{background:#fff;border-radius:8px;padding:20px 24px;margin-bottom:18px;
              box-shadow:0 1px 3px rgba(0,0,0,.12)}}
.section-title{{font-size:15px;font-weight:700;color:#1c1e21;margin-bottom:2px}}
.section-sub{{font-size:12px;color:#8a8d91;margin-bottom:16px}}
.chart-wrap{{height:280px;position:relative}}
.table-wrap{{overflow-x:auto}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
thead th{{padding:10px 14px;text-align:right;font-weight:700;color:#606770;
         border-bottom:2px solid #dddfe2;font-size:11px;text-transform:uppercase;
         letter-spacing:.4px;white-space:nowrap}}
thead th:first-child{{text-align:left}}
tbody tr{{border-bottom:1px solid #f0f2f5;transition:background .1s}}
tbody tr:hover{{background:#f7f8fa}}
tbody tr.out-range{{opacity:.4}}
tbody td{{padding:9px 14px;text-align:right;color:#1c1e21;white-space:nowrap}}
tbody td:first-child{{text-align:left;color:#606770;font-weight:600}}
.td-spend{{font-weight:600}}
.td-msgs{{color:#1877f2;font-weight:700}}
.td-good{{color:#42b72a;font-weight:600}}
.td-warn{{color:#e2a01d;font-weight:600}}
.td-bad{{color:#fa383e;font-weight:600}}
.today-row td{{background:#f0f7ff}}
.today-badge,.range-badge{{display:inline-block;font-size:9px;font-weight:700;
             padding:1px 5px;border-radius:3px;margin-left:5px;vertical-align:middle}}
.today-badge{{background:#e7f3ff;color:#1877f2}}
.range-badge{{background:#e6f4ea;color:#2d9e43}}
.flatpickr-calendar{{font-family:'Inter',sans-serif!important;border-radius:10px;
                    box-shadow:0 8px 24px rgba(0,0,0,.15)!important}}
.flatpickr-day.selected,.flatpickr-day.startRange,.flatpickr-day.endRange{{
  background:#1877f2!important;border-color:#1877f2!important}}
.flatpickr-day.inRange{{background:#e7f3ff!important;border-color:#e7f3ff!important;color:#1c1e21}}
.footer{{text-align:center;font-size:11px;color:#8a8d91;margin-top:24px}}
@media(max-width:620px){{.kpi-grid{{grid-template-columns:1fr}}#dateRangeInput{{min-width:220px}}}}
</style>
</head>
<body>
<div class="page">
<div class="header">
  <div><div class="fb-wordmark">facebook</div><div class="fb-sub">Ads</div></div>
  {logo_html}
</div>
<div class="camp-info">
  <div class="camp-dot"></div>
  <div><div class="camp-name">{camp_name}</div><div class="camp-status">{status_label}</div></div>
  <div class="camp-account">Conta: {account_id}</div>
</div>
<div class="date-range-wrap">
  <div class="date-input-wrap">
    <span class="date-icon">📅</span>
    <input id="dateRangeInput" type="text" readonly placeholder="Selecione o período"/>
  </div>
  <div class="period-shortcuts">
    <button class="ps-btn" onclick="applyShortcut(0)">Hoje</button>
    <button class="ps-btn" onclick="applyShortcut(1)">Ontem</button>
    <button class="ps-btn" onclick="applyShortcut(7)">Últimos 7 dias</button>
    <button class="ps-btn" onclick="applyShortcut(15)">Últimos 15 dias</button>
    <button class="ps-btn" onclick="applyShortcut(30)">Últimos 30 dias</button>
  </div>
</div>
<div class="kpi-grid">
  <div class="kpi-card">
    <div class="kpi-label">Valor Investido</div>
    <div class="kpi-value" id="kpi-spend">—</div>
    <div class="kpi-sub" id="kpi-spend-sub"></div>
  </div>
  <div class="kpi-card" style="border-top-color:#42b72a">
    <div class="kpi-label" style="color:#42b72a">Mensagens Iniciadas</div>
    <div class="kpi-value" id="kpi-msgs">—</div>
    <div class="kpi-sub" id="kpi-msgs-sub"></div>
  </div>
  <div class="kpi-card" style="border-top-color:#e2a01d">
    <div class="kpi-label" style="color:#e2a01d">Custo por Mensagem</div>
    <div class="kpi-value" id="kpi-cpmsg">—</div>
    <div class="kpi-sub" id="kpi-cpmsg-sub"></div>
  </div>
</div>
<div class="section-card">
  <div class="section-title">Visão Geral</div>
  <div class="section-sub" id="chartSub">Período selecionado</div>
  <div class="chart-wrap"><canvas id="mainChart"></canvas></div>
</div>
<div class="section-card">
  <div class="section-title">Detalhamento</div>
  <div class="section-sub">Diário · Últimos 30 dias</div>
  <div class="table-wrap">
    <table>
      <thead><tr>
        <th style="text-align:left">Dia</th>
        <th>Valor Investido</th><th>Mensagens</th><th>Custo/Msg</th>
        <th>Impressões</th><th>CPM</th><th>CTR</th>
      </tr></thead>
      <tbody id="tableBody"></tbody>
    </table>
  </div>
</div>
<div class="footer">Gerado em {gen_date} · {clinic_name} · Gestor Igor Teixeira · Meta API v21.0</div>
</div>
<script>
const DAILY={daily_json};
const PT_M=['jan','fev','mar','abr','mai','jun','jul','ago','set','out','nov','dez'];
const PT_MF=['janeiro','fevereiro','março','abril','maio','junho','julho','agosto','setembro','outubro','novembro','dezembro'];
let chart=null,activeSince=null,activeUntil=null;
function fmtBRL(v){{return 'R$ '+Number(v).toLocaleString('pt-BR',{{minimumFractionDigits:2,maximumFractionDigits:2}})}}
function fmtNum(v){{return Number(v).toLocaleString('pt-BR')}}
function fmtShort(iso){{const[y,m,d]=iso.split('-');return `${{+d}} de ${{PT_M[+m-1]}}.`}}
function fmtFull(iso){{const[y,m,d]=iso.split('-');return `${{+d}} de ${{PT_MF[+m-1]}} de ${{y}}`}}
function addDays(iso,n){{const d=new Date(iso+'T12:00:00');d.setDate(d.getDate()+n);return d.toISOString().slice(0,10)}}
function today(){{return DAILY.length>0?DAILY[0].date:new Date().toISOString().slice(0,10)}}
const fp=flatpickr('#dateRangeInput',{{mode:'range',locale:'pt',dateFormat:'d \\de M. \\de Y',
  minDate:DAILY.length>0?DAILY[DAILY.length-1].date:undefined,
  maxDate:DAILY.length>0?DAILY[0].date:undefined,showMonths:1,
  onChange(sel){{if(sel.length===2){{clearShortcuts();applyRange(sel[0].toISOString().slice(0,10),sel[1].toISOString().slice(0,10));}}}}
}});
function applyShortcut(days){{
  clearShortcuts();
  const btns=document.querySelectorAll('.ps-btn');
  const idx=[0,1,7,15,30].indexOf(days);
  if(idx>=0)btns[idx].classList.add('active');
  const until=today();
  const since=days===0?until:days===1?addDays(until,-1):addDays(until,-(days-1));
  const sinceEnd=days===1?addDays(until,-1):until;
  fp.setDate([since,sinceEnd],false);
  applyRange(since,sinceEnd);
}}
function clearShortcuts(){{document.querySelectorAll('.ps-btn').forEach(b=>b.classList.remove('active'));}}
function applyRange(since,until){{
  activeSince=since;activeUntil=until;
  const inRange=DAILY.filter(d=>d.date>=since&&d.date<=until).sort((a,b)=>a.date.localeCompare(b.date));
  const totalSpend=inRange.reduce((s,d)=>s+d.spend,0);
  const totalMsgs=inRange.reduce((s,d)=>s+d.msgs,0);
  const cpMsg=totalMsgs>0?totalSpend/totalMsgs:0;
  const totalImpr=inRange.reduce((s,d)=>s+d.impr,0);
  document.getElementById('kpi-spend').textContent=fmtBRL(totalSpend);
  document.getElementById('kpi-spend-sub').textContent=`${{inRange.length}} dias · Impressões: ${{fmtNum(totalImpr)}}`;
  document.getElementById('kpi-msgs').textContent=fmtNum(totalMsgs);
  document.getElementById('kpi-msgs-sub').textContent=`Média diária: ${{inRange.length>0?(totalMsgs/inRange.length).toFixed(1):0}} msgs`;
  document.getElementById('kpi-cpmsg').textContent=fmtBRL(cpMsg);
  document.getElementById('kpi-cpmsg-sub').textContent=cpMsg>0&&cpMsg<=12?'✓ Dentro da meta (≤R$12)':cpMsg>12?'⚠ Acima da meta':'—';
  document.getElementById('kpi-cpmsg').style.color=cpMsg>15?'#fa383e':cpMsg>12?'#e2a01d':'#1c1e21';
  document.getElementById('chartSub').textContent=fmtFull(since)+' – '+fmtFull(until);
  renderChart(inRange);renderTable(since,until);
}}
function renderChart(days){{
  if(chart){{chart.destroy();chart=null}}
  chart=new Chart(document.getElementById('mainChart'),{{
    data:{{
      labels:days.map(d=>fmtShort(d.date)),
      datasets:[
        {{type:'bar',label:'Mensagens Iniciadas',data:days.map(d=>d.msgs),
          backgroundColor:'rgba(24,119,242,0.65)',borderColor:'rgba(24,119,242,1)',
          borderWidth:1,borderRadius:4,yAxisID:'yL',order:2}},
        {{type:'line',label:'Valor Investido',data:days.map(d=>d.spend),
          borderColor:'#7b1fa2',backgroundColor:'transparent',
          borderWidth:2.5,pointRadius:4,pointBackgroundColor:'#7b1fa2',
          tension:0.3,yAxisID:'yR',order:1}}
      ]
    }},
    options:{{responsive:true,maintainAspectRatio:false,interaction:{{mode:'index',intersect:false}},
      plugins:{{legend:{{display:true,position:'top',align:'start',
        labels:{{font:{{size:11,family:'Inter'}},color:'#606770',boxWidth:14,padding:14,usePointStyle:true}}}},
        tooltip:{{backgroundColor:'#fff',titleColor:'#1c1e21',bodyColor:'#606770',
          borderColor:'#dddfe2',borderWidth:1,padding:10,
          callbacks:{{label(c){{return c.dataset.label==='Valor Investido'?' '+fmtBRL(c.raw):' '+fmtNum(c.raw)+' msgs'}}}}}}}},
      scales:{{
        yL:{{type:'linear',position:'left',beginAtZero:true,
            title:{{display:true,text:'Mensagens',color:'#606770',font:{{size:10}}}},
            ticks:{{color:'#606770',font:{{size:10}}}},grid:{{color:'rgba(0,0,0,.05)'}}}},
        yR:{{type:'linear',position:'right',beginAtZero:true,
            title:{{display:true,text:'Investido',color:'#606770',font:{{size:10}}}},
            ticks:{{color:'#606770',font:{{size:10}},callback:v=>'R$'+v.toFixed(0)}},grid:{{display:false}}}},
        x:{{ticks:{{color:'#606770',font:{{size:10}},maxRotation:45}},grid:{{display:false}}}}
      }}
    }}
  }});
}}
function renderTable(since,until){{
  const tbody=document.getElementById('tableBody');
  const todayStr=DAILY.length>0?DAILY[0].date:'';
  tbody.innerHTML='';
  DAILY.forEach(d=>{{
    const inSel=d.date>=since&&d.date<=until;
    const isToday=d.date===todayStr;
    const[y,m,day]=d.date.split('-');
    const cpClass=d.cost_msg<=10?'td-good':d.cost_msg<=15?'td-warn':'td-bad';
    const tr=document.createElement('tr');
    if(isToday)tr.className='today-row';else if(!inSel)tr.className='out-range';
    tr.innerHTML=`<td>${{+day}} de ${{PT_M[+m-1]}}.${{isToday?'<span class="today-badge">HOJE</span>':''}}${{inSel&&!isToday?'<span class="range-badge">✓</span>':''}}</td>
      <td class="td-spend">${{fmtBRL(d.spend)}}</td><td class="td-msgs">${{fmtNum(d.msgs)}}</td>
      <td class="${{cpClass}}">${{fmtBRL(d.cost_msg)}}</td><td>${{fmtNum(d.impr)}}</td>
      <td>${{fmtBRL(d.cpm)}}</td><td>${{d.ctr.toFixed(2)}}%</td>`;
    tbody.appendChild(tr);
  }});
}}
applyShortcut(15);
</script>
</body>
</html>"""

# ─── NOTION UPDATE ────────────────────────────────────────────────────────────
def notion_update_url(page_id, url):
    try:
        r = requests.patch(f"{NOTION_BASE}/pages/{page_id}",
                           headers=notion_headers(),
                           json={"properties": {"Relatório Novo": {"url": url}}}, timeout=30)
        r.raise_for_status(); return True
    except Exception as e:
        print(f"  [ERROR] URL {page_id}: {e}"); return False

def notion_add_blocks(page_id, png_url):
    try:
        r = requests.get(f"{NOTION_BASE}/blocks/{page_id}/children",
                         headers=notion_headers(), params={"page_size": 100}, timeout=30)
        r.raise_for_status()
        for b in r.json().get("results", []):
            if b.get("type") == "heading_3":
                if any("Preview" in t.get("plain_text","")
                       for t in b.get("heading_3",{}).get("rich_text",[])):
                    print(f"  [SKIP] blocos já existem"); return True
    except: pass
    try:
        payload = {"children": [
            {"object":"block","type":"heading_3",
             "heading_3":{"rich_text":[{"type":"text","text":{"content":"📊 Preview do Relatório"}}]}},
            {"object":"block","type":"image",
             "image":{"type":"external","external":{"url": png_url}}}
        ]}
        r = requests.patch(f"{NOTION_BASE}/blocks/{page_id}/children",
                           headers=notion_headers(), json=payload, timeout=30)
        r.raise_for_status(); return True
    except Exception as e:
        print(f"  [ERROR] blocos {page_id}: {e}"); return False

# ─── LOCAL SERVER ─────────────────────────────────────────────────────────────
class QH(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass

def start_server(directory, port):
    os.chdir(directory)
    t = threading.Thread(target=http.server.HTTPServer(("",port),QH).serve_forever, daemon=True)
    t.start()

# ─── SCREENSHOTS ─────────────────────────────────────────────────────────────
async def screenshots_async(items):
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width":920,"height":800})
        pg  = await ctx.new_page()
        for item in items:
            url = f"http://localhost:{LOCAL_PORT}/{item['html_filename']}"
            try:
                print(f"  📸 {item['slug']}")
                await pg.goto(url, wait_until="networkidle", timeout=30000)
                await pg.wait_for_timeout(2000)
                await pg.screenshot(path=str(item["png_path"]), full_page=True)
            except Exception as e:
                print(f"  [ERROR] screenshot {item['slug']}: {e}")
        await browser.close()

def take_screenshots(items):
    import asyncio; asyncio.run(screenshots_async(items))

# ─── GIT ──────────────────────────────────────────────────────────────────────
def git_commit_push(files, message):
    try:
        subprocess.run(["git","-C",str(BASE_DIR),"add"]+[str(f) for f in files],
                       check=True, capture_output=True)
        subprocess.run(["git","-C",str(BASE_DIR),"commit","-m",message],
                       check=True, capture_output=True)
        subprocess.run(["git","-C",str(BASE_DIR),"push"],
                       check=True, capture_output=True)
        print(f"✅ git push: {message[:60]}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] git: {e.stderr.decode()[:200]}"); return False

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    print("="*60)
    print("Relatórios Igor Teixeira — Status ON")
    print("="*60)

    if not LOGO_B64:
        print(f"❌ Logo não encontrado: {LOGO_PATH}"); sys.exit(1)
    print(f"✅ Logo OK ({len(LOGO_B64)//1024}KB b64)")

    # 1) Notion
    print("\n[1/7] Buscando páginas Notion (Igor Teixeira, ON)...")
    pages = notion_get_igor_pages()
    print(f"  → {len(pages)} páginas encontradas")

    entries, sem_conta = [], []
    for p in pages:
        parsed = parse_page(p)
        if parsed["account_id"]:
            entries.append(parsed)
        else:
            sem_conta.append(parsed)

    print(f"  → {len(entries)} com conta válida")
    print(f"  → {len(sem_conta)} sem conta (serão ignoradas):")
    for e in sem_conta:
        print(f"     · {e['clinic_name']} (C.A: {e['ca_field']!r})")

    # 2) Campanhas (cache por conta)
    print("\n[2/7] Buscando campanhas...")
    camp_cache = {}
    for e in entries:
        acct = e["account_id"]
        if acct not in camp_cache:
            print(f"  Conta {acct}...")
            camp_cache[acct] = fetch_campaigns(acct)
            print(f"    → {len(camp_cache[acct])} campanhas")
            time.sleep(0.3)

    # 3) Insights 30 dias
    print("\n[3/7] Insights diários (30 dias)...")
    today  = date.today()
    since  = (today - timedelta(days=29)).isoformat()
    until  = today.isoformat()

    resultados, sem_camp = [], []
    for entry in entries:
        clinic = entry["clinic_name"]
        acct   = entry["account_id"]
        print(f"\n  [{clinic}]")

        camp = find_campaign(camp_cache.get(acct,[]), clinic)
        if not camp:
            print(f"    ⚠ campanha não encontrada")
            sem_camp.append(entry); continue

        print(f"    → {camp['name']} ({camp.get('effective_status','?')})")
        daily = fetch_daily_insights(camp["id"], since, until)
        print(f"    → {len(daily)} dias de dados")

        slug          = slugify(clinic)
        html_filename = f"relatorio_{slug}.html"
        png_filename  = f"relatorio_{slug}.png"
        html_path     = BASE_DIR / html_filename
        png_path      = BASE_DIR / png_filename

        html_path.write_text(generate_html(clinic, camp, acct, daily), encoding="utf-8")
        print(f"    → HTML: {html_filename}")
        resultados.append({
            "entry": entry, "campaign": camp, "slug": slug,
            "html_filename": html_filename, "png_filename": png_filename,
            "html_path": html_path, "png_path": png_path,
        })

    print(f"\n  ✅ {len(resultados)} HTMLs | ⚠ {len(sem_camp)} sem campanha")
    if not resultados:
        print("Nada a processar."); return

    # 4+5) Servidor + Screenshots
    print(f"\n[4/7] Servidor local porta {LOCAL_PORT}...")
    start_server(str(BASE_DIR), LOCAL_PORT); time.sleep(1)

    print(f"\n[5/7] Screenshots ({len(resultados)})...")
    take_screenshots([{"slug":r["slug"],"html_filename":r["html_filename"],"png_path":r["png_path"]}
                      for r in resultados])

    # 6) Git
    print("\n[6/7] Git commit + push...")
    all_files = [r["html_path"] for r in resultados]
    all_files += [r["png_path"] for r in resultados if r["png_path"].exists()]
    if all_files:
        git_commit_push(all_files,
            f"Relatórios Igor Teixeira — {len(resultados)} clínicas — {today.isoformat()}")

    # 7) Notion
    print("\n[7/7] Atualizando Notion...")
    for r in resultados:
        entry    = r["entry"]
        html_url = f"{GH_PAGES_BASE}/{r['html_filename']}"
        png_url  = f"{GH_PAGES_BASE}/{r['png_filename']}"
        page_id  = entry["page_id"]
        print(f"  [{entry['clinic_name']}]")
        ok  = notion_update_url(page_id, html_url)
        print(f"    → URL: {'✅' if ok else '❌'}")
        time.sleep(0.3)
        ok2 = notion_add_blocks(page_id, png_url)
        print(f"    → Blocos: {'✅' if ok2 else '❌'}")
        time.sleep(0.3)

    # ─── RESUMO ───────────────────────────────────────────────────────────────
    print("\n"+"="*60)
    print(f"✅ Sucesso:        {len(resultados)}")
    print(f"⚠  Sem campanha:  {len(sem_camp)}")
    print(f"⚠  Sem conta:     {len(sem_conta)}")
    if sem_camp:
        print("\n⚠ Sem campanha:")
        for e in sem_camp: print(f"   · {e['clinic_name']} (conta {e['account_id']})")
    if sem_conta:
        print("\n⚠ Sem conta:")
        for e in sem_conta: print(f"   · {e['clinic_name']} (C.A: {e['ca_field']!r})")
    print("="*60)

if __name__ == "__main__":
    main()
