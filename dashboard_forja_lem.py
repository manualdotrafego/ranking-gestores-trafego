#!/usr/bin/env python3
"""Dashboard de conversao em vendas - campanha [FORJA LEM].
Puxa insights (funil de vendas via pixel) do Meta e gera dashboard_forja_lem.html.
Roda a cada 6h na VPS; com PUSH=1 faz commit+push para o GitHub Pages.
"""
import os, re, json, time, subprocess, datetime as dt
from pathlib import Path
from dotenv import load_dotenv

BASE = Path(os.environ.get("PROJECT_DIR", "/Users/alexrangelalves/Downloads/Conexão mtds"))
load_dotenv(dotenv_path=BASE / ".env")
TOK = os.getenv("META_ACCESS_TOKEN")
ACC = "753068846198086"
CID = "120248881846520470"
NAME = "[FORJA LEM] - [GUILHERME FREIRE]"
SINCE = "2026-08-15"
B = "https://graph.facebook.com/v21.0"
OUT = BASE / "dashboard_forja_lem.html"
GH = "https://manualdotrafego.github.io/ranking-gestores-trafego/dashboard_forja_lem.html"


def av(actions, t):
    for a in actions or []:
        if a["action_type"] == t:
            return float(a["value"])
    return 0.0


def fetch():
    until = dt.date.today().isoformat()
    r = requests.get(f"{B}/{CID}/insights", params={
        "access_token": TOK, "time_range": json.dumps({"since": SINCE, "until": until}),
        "time_increment": 1,
        "fields": "date_start,spend,impressions,reach,inline_link_clicks,actions,action_values"}).json()
    days = []
    for d in r.get("data", []):
        acts, vals = d.get("actions"), d.get("action_values")
        days.append({
            "date": d["date_start"],
            "spend": round(float(d.get("spend", 0)), 2),
            "impr": int(float(d.get("impressions", 0))),
            "reach": int(float(d.get("reach", 0))),
            "clicks": int(float(d.get("inline_link_clicks", 0))),
            "lpv": int(av(acts, "landing_page_view")),
            "atc": int(av(acts, "add_to_cart")),
            "ic": int(av(acts, "initiate_checkout")),
            "api": int(av(acts, "add_payment_info")),
            "lead": int(av(acts, "lead")),
            "purch": int(av(acts, "purchase")),
            "rev": round(av(vals, "purchase"), 2),
        })
    days.sort(key=lambda x: x["date"])
    return days


def build(days):
    def s(k): return sum(d[k] for d in days)
    tot = {k: s(k) for k in ("spend", "impr", "reach", "clicks", "lpv", "atc", "ic", "api", "lead", "purch", "rev")}
    spend, purch, rev = tot["spend"], tot["purch"], tot["rev"]
    kpi = {
        "spend": spend, "purch": purch, "rev": rev,
        "roas": (rev / spend) if spend else 0,
        "cpa": (spend / purch) if purch else 0,
        "ticket": (rev / purch) if purch else 0,
        "convrate": (purch / tot["clicks"] * 100) if tot["clicks"] else 0,
        "ctr": (tot["clicks"] / tot["impr"] * 100) if tot["impr"] else 0,
        "cpc": (spend / tot["clicks"]) if tot["clicks"] else 0,
        "cpm": (spend / tot["impr"] * 1000) if tot["impr"] else 0,
    }
    funnel = [
        ("Impressoes", tot["impr"]), ("Cliques no link", tot["clicks"]),
        ("Visualizacoes da pagina", tot["lpv"]), ("Adicoes ao carrinho", tot["atc"]),
        ("Checkout iniciado", tot["ic"]), ("Info de pagamento", tot["api"]),
        ("Compras", tot["purch"]),
    ]
    updated = (dt.datetime.utcnow() - dt.timedelta(hours=3)).strftime("%d/%m/%Y %H:%M")
    per = f'{days[0]["date"][8:10]}/{days[0]["date"][5:7]} a {days[-1]["date"][8:10]}/{days[-1]["date"][5:7]}' if days else "-"
    payload = {"kpi": kpi, "tot": tot, "funnel": funnel, "days": days,
               "name": NAME, "acc": ACC, "updated": updated, "period": per}
    html = TEMPLATE.replace("__DATA__", json.dumps(payload, ensure_ascii=False))
    OUT.write_text(html, encoding="utf-8")
    return kpi, len(days)


def push():
    def g(*a): return subprocess.run(["git", "-C", str(BASE), *a], capture_output=True, text=True)
    g("add", str(OUT))
    if "nothing to commit" in (g("status", "--porcelain").stdout or "") and False:
        return
    g("commit", "-m", f"Dashboard Forja LEM {dt.datetime.utcnow().isoformat()}")
    for f in ("dashboard_data.json", "alertas.json"):
        g("checkout", "--", f)
    for _ in range(3):
        g("pull", "--rebase", "--autostash", "origin", "main")
        if g("push", "origin", "main").returncode == 0:
            print("push OK"); return
    print("push falhou")


TEMPLATE = r"""<!doctype html><html lang="pt-BR"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Forja LEM - Conversao em Vendas</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:Inter,system-ui,Arial,sans-serif;background:#0e1420;color:#e7ecf3;padding:22px;max-width:1180px;margin:0 auto}
.hd{display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:10px;margin-bottom:18px}
.hd h1{font-size:22px;font-weight:800;letter-spacing:.2px}
.hd .sub{color:#8a97a8;font-size:13px;margin-top:4px}
.hd .upd{color:#8a97a8;font-size:12px;text-align:right}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:20px}
.card{background:#161f2e;border:1px solid #23304a;border-radius:14px;padding:16px}
.card .lbl{color:#8a97a8;font-size:11px;text-transform:uppercase;letter-spacing:.6px;font-weight:600}
.card .val{font-size:26px;font-weight:800;margin-top:6px}
.card .val small{font-size:14px;color:#8a97a8;font-weight:600}
.card.hi{background:linear-gradient(135deg,#173a2a,#12261d);border-color:#1f6a45}
.card.hi .val{color:#41d693}
.card.warn .val{color:#ffcf5c}
.sec{background:#161f2e;border:1px solid #23304a;border-radius:14px;padding:18px;margin-bottom:20px}
.sec h2{font-size:15px;font-weight:700;margin-bottom:14px;color:#cdd7e5}
.fnl{display:flex;flex-direction:column;gap:8px}
.frow{display:grid;grid-template-columns:190px 1fr 130px;align-items:center;gap:12px}
.frow .fn{font-size:13px;color:#b9c4d4}
.fbar{height:30px;background:#1d2942;border-radius:7px;overflow:hidden;position:relative}
.fbar>span{display:block;height:100%;background:linear-gradient(90deg,#3b82f6,#6366f1);border-radius:7px}
.frow .fv{font-size:13px;text-align:right;font-variant-numeric:tabular-nums}
.frow .fv b{font-size:15px}
.frow .fv .pct{color:#8a97a8;font-size:11px}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th,td{padding:8px 6px;text-align:right;border-bottom:1px solid #223049;font-variant-numeric:tabular-nums}
th{color:#8a97a8;font-weight:600;text-transform:uppercase;font-size:10px;letter-spacing:.5px}
td:first-child,th:first-child{text-align:left}
.wrap{overflow-x:auto}
.ft{color:#66727f;font-size:11px;text-align:center;margin-top:8px}
</style></head><body>
<div class="hd">
  <div><h1 id="cn"></h1><div class="sub" id="cs"></div></div>
  <div class="upd" id="cu"></div>
</div>
<div class="grid" id="kpis"></div>
<div class="sec"><h2>Funil de conversao</h2><div class="fnl" id="fnl"></div></div>
<div class="sec"><h2>Tendencia diaria</h2><canvas id="ch" height="90"></canvas></div>
<div class="sec"><h2>Detalhamento diario</h2><div class="wrap"><table id="tbl"></table></div></div>
<div class="ft">Meta Ads API v21.0 - dados de pixel (janela de atribuicao padrao 7d clique / 1d visualizacao)</div>
<script>
const D=__DATA__;
const brl=n=>'R$ '+(n||0).toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2});
const num=n=>(n||0).toLocaleString('pt-BR');
document.getElementById('cn').textContent=D.name;
document.getElementById('cs').textContent='Conta '+D.acc+'  -  Periodo '+D.period+'  -  Conversao em vendas';
document.getElementById('cu').textContent='Atualizado em '+D.updated+' (BRT)';
const k=D.kpi;
const cards=[
 ['Investimento',brl(k.spend),''],
 ['Compras',num(k.purch),'hi'],
 ['Receita',brl(k.rev),'hi'],
 ['ROAS',(k.roas).toLocaleString('pt-BR',{maximumFractionDigits:2})+'x',k.roas>=1?'hi':'warn'],
 ['Custo por compra',brl(k.cpa),''],
 ['Ticket medio',brl(k.ticket),''],
 ['Taxa de conversao',(k.convrate).toFixed(1)+'%','' ],
 ['CTR',(k.ctr).toFixed(2)+'%',''],
 ['CPC',brl(k.cpc),''],
 ['CPM',brl(k.cpm),''],
];
document.getElementById('kpis').innerHTML=cards.map(c=>`<div class="card ${c[2]}"><div class="lbl">${c[0]}</div><div class="val">${c[1]}</div></div>`).join('');
const topN=D.funnel[0][1]||1;
document.getElementById('fnl').innerHTML=D.funnel.map((f,i)=>{
 const prev=i>0?D.funnel[i-1][1]:f[1];
 const stepPct=prev? (f[1]/prev*100):0;
 const w=Math.max(2,(f[1]/topN*100));
 return `<div class="frow"><div class="fn">${f[0]}</div><div class="fbar"><span style="width:${w}%"></span></div><div class="fv"><b>${num(f[1])}</b>${i>0?` <span class="pct">(${stepPct.toFixed(1)}%)</span>`:''}</div></div>`;
}).join('');
const labels=D.days.map(d=>d.date.slice(8,10)+'/'+d.date.slice(5,7));
new Chart(document.getElementById('ch'),{data:{labels,datasets:[
 {type:'bar',label:'Investimento (R$)',data:D.days.map(d=>d.spend),backgroundColor:'#3b82f6',yAxisID:'y',order:3},
 {type:'line',label:'Receita (R$)',data:D.days.map(d=>d.rev),borderColor:'#41d693',backgroundColor:'#41d693',tension:.3,yAxisID:'y',order:1},
 {type:'line',label:'Compras',data:D.days.map(d=>d.purch),borderColor:'#ffcf5c',backgroundColor:'#ffcf5c',tension:.3,yAxisID:'y2',order:0},
]},options:{responsive:true,plugins:{legend:{labels:{color:'#b9c4d4'}}},
 scales:{y:{position:'left',ticks:{color:'#8a97a8'},grid:{color:'#1d2942'}},
 y2:{position:'right',ticks:{color:'#8a97a8'},grid:{drawOnChartArea:false}},
 x:{ticks:{color:'#8a97a8'},grid:{color:'#1d2942'}}}}});
const rows=D.days.slice().reverse();
document.getElementById('tbl').innerHTML=
 '<thead><tr><th>Dia</th><th>Invest.</th><th>Impr.</th><th>Cliques</th><th>LPV</th><th>Carrinho</th><th>Checkout</th><th>Compras</th><th>Receita</th><th>ROAS</th></tr></thead><tbody>'+
 rows.map(d=>`<tr><td>${d.date.slice(8,10)+'/'+d.date.slice(5,7)}</td><td>${brl(d.spend)}</td><td>${num(d.impr)}</td><td>${num(d.clicks)}</td><td>${num(d.lpv)}</td><td>${num(d.atc)}</td><td>${num(d.ic)}</td><td><b>${num(d.purch)}</b></td><td>${brl(d.rev)}</td><td>${(d.spend?d.rev/d.spend:0).toFixed(2)}x</td></tr>`).join('')+'</tbody>';
</script></body></html>"""

if __name__ == "__main__":
    import requests
    days = fetch()
    kpi, n = build(days)
    print(f"gerado {OUT.name}: {n} dias | spend R${kpi['spend']:.2f} | {kpi['purch']} compras | ROAS {kpi['roas']:.2f}")
    if os.environ.get("PUSH") == "1":
        push()
