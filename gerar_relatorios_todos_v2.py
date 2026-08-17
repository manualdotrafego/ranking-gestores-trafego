#!/usr/bin/env /Library/Frameworks/Python.framework/Versions/3.14/bin/python3
"""
gerar_relatorios_todos_v2.py
Gera/atualiza relatórios HTML + screenshots para TODOS os gestores.
Últimos 15 dias de dados. Commit + push automático ao final.

Uso:
  python3 gerar_relatorios_todos_v2.py                  # todos
  python3 gerar_relatorios_todos_v2.py --gestor braga   # só Thiago Braga
  python3 gerar_relatorios_todos_v2.py --gestor igor
  python3 gerar_relatorios_todos_v2.py --gestor milena  # Giovanni Azzi
  python3 gerar_relatorios_todos_v2.py --gestor bueno
  python3 gerar_relatorios_todos_v2.py --gestor mota
  python3 gerar_relatorios_todos_v2.py --gestor victor
  python3 gerar_relatorios_todos_v2.py --test "177 - Águas Lindas de Goiás"
"""

import os, re, sys, json, time, base64, subprocess, unicodedata
import http.server, threading, requests, socket
from datetime import date, timedelta
from pathlib import Path
from dotenv import load_dotenv

# ─── CONFIG ───────────────────────────────────────────────────────────────────
BASE_DIR  = Path(os.environ.get("PROJECT_DIR", "/Users/alexrangelalves/Downloads/Conexão mtds"))
LOGO_PATH = Path(os.environ.get("LOGO_PATH", str(BASE_DIR / "Logo Dbout.png")))
load_dotenv(dotenv_path=BASE_DIR / ".env")

META_TOKEN    = os.getenv("META_ACCESS_TOKEN")
META_BASE     = "https://graph.facebook.com/v21.0"
NOTION_TOKEN  = os.getenv("NOTION_TOKEN", "")
NOTION_DB_ID  = "115e97e8e1368028b3c1fe0a465f8b07"   # Data Base de Tudo [BACKUP]
NOTION_BASE   = "https://api.notion.com/v1"
GH_PAGES_BASE = "https://manualdotrafego.github.io/ranking-gestores-trafego"
LOCAL_PORT    = 0   # 0 = escolhe porta livre automaticamente

DAYS_BACK = 90   # janela móvel: mínimo 40 dias de histórico navegável
DEFAULT_DISPLAY = 15   # fallback (não usado quando FIXED_RANGE ativo)
# Período fixo de exibição padrão nos relatórios
FIXED_SINCE = "2026-05-20"
FIXED_UNTIL = "2026-08-17"

# ─── CONTAS POR GESTOR ────────────────────────────────────────────────────────
GESTORES_ACCOUNTS = {
    "Thiago Braga": {
        "795680591769062",   # CT02 - Braga
        "350266333900752",   # CT03 - São José do Rio Preto
        "613666203841045",   # CT05 - Braga
        "1534753857104914",  # CDC Odontologia
        "627225619698621",   # Contagem
        "684292170965131",   # Dbout Aquec 02 CA01
        "1385771249133770",  # Dbout Aquec 02 CA02
        "1492720022172340",  # Dbout Aquec 02 CA03
        "784528807407228",   # Mirassol Orthodontic CA01
        "1221130892436075",  # MOGI/SUZANO CA01
        "945748271201968",   # CA 02 - RIO CLARO
        "1191172178527886",  # São José dos Campos Vilaça
    },
    "Igor Teixeira": {
        "5648874101844136",  # CT03 - Guaramirim
        "449000287288780",   # CT02 - Unaí
        "1181454115989018",  # CT03 - Fhilipe
        "1191525622298805",  # CT05 - DBOUT 02
        "412153471621510",   # CT02 - MJOLNIR
        "391009870578696",   # AQC 00
        "1583196522529565",  # CT01 - DRACO
        "1329276834986407",  # Orthodontic Aparecida Goiânia
        "566170923166415",   # Ortomais 1.1
        "1132321672289497",  # Brasil Odontologia Rio do Sul
    },
    "Giovanni Azzi": {
        "929466455169259",   # C.A 01 MKT DBOUT - MILENA
        "1085576095862723",  # C.A 02 MKT DBOUT - MILENA
        "1092388468506879",  # C.A 03 MKT DBOUT - MILENA
        "8918374284933128",  # C.A 04 MKT DBOUT - MILENA
        "821690284057436",   # C.A 05 MKT DBOUT - MILENA
        "1256638916269263",  # C.A 06 MKT DBOUT - MILENA
    },
    "Victor Coutinho": {
        "816831793052077",   # CT01 - Victor
        "1145079426101184",  # CT02 - Victor
        "1229765484942576",  # CA 04 - EQUITY+ Victor
    },
    "Gustavo Bueno": {
        "844368963369490",   # CT09 - BM04 - Closer Brasil
        "762767474947500",   # CT 01 - Mercado da Patrícia
        "514946917180994",   # CT08 - BM04 - Closer Brasil
        "646063993729347",   # CT10 - BM04 - Closer Brasil
        "1473069363640157",  # CT 03 - Operação Sorriso
        "1512288279712118",  # CT 01 - Operação Sorriso
        "1874417206315032",  # CT12 - BM04 Closer Brasil
        "3656827834577801",  # CT14 - BM04 Closer Brasil
        "421023317498662",   # CT13 - BM04 Closer Brasil
        "969549934748192",   # CT11 - BM04 Closer Brasil
        "3143685079159710",  # 01 Cayman - BM Carazinhosorrisoperfeito (Planaltina/GO #150)
    },
    "Gustavo Motta": {
        "5278613945567179",  # CT01 - BM02 - Mota
        "388602330121239",   # CT03 - BM02 - Mota
        "140805155678128",   # CT1 - Mota
        "959827441932943",   # CT04 - Cartão Cliente Pinhais
        "782257763801898",   # CT06 - Mota
        "716772110646661",   # CT07 - Dbout Mota (Formosa #652 etc.)
    },
}

ALL_VALID_ACCOUNTS = set()
for accounts in GESTORES_ACCOUNTS.values():
    ALL_VALID_ACCOUNTS |= accounts

# ID fixes: alguns registros Notion têm dígito a menos
ID_FIX = {
    "41215347621510":  "412153471621510",
    "11915262298805":  "1191525622298805",
}

# Mapeamento gestor Notion → chave GESTORES_ACCOUNTS
GESTOR_FILTER_MAP = {
    "braga":  "Thiago Braga",
    "igor":   "Igor Teixeira",
    "milena": "Giovanni Azzi",
    "gio":    "Giovanni Azzi",
    "bueno":  "Gustavo Bueno",
    "mota":   "Gustavo Motta",
    "victor": "Victor Coutinho",
}

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t)
    return "".join(c for c in t if not unicodedata.combining(c)).lower()

def slugify(t: str) -> str:
    t = norm(t)
    t = re.sub(r"[^\w\s-]", "", t)
    return re.sub(r"[\s\-]+", "_", t).strip("_")

def load_logo_b64() -> str:
    """Carrega logo, processa em círculo 120×120 e retorna base64 PNG."""
    try:
        from PIL import Image, ImageDraw
        import io as _io
        img = Image.open(LOGO_PATH).convert("RGBA")
        w, h = img.size
        size = min(w, h)
        img = img.crop(((w - size) // 2, (h - size) // 2,
                        (w - size) // 2 + size, (h - size) // 2 + size))
        img = img.resize((120, 120), Image.LANCZOS)
        mask = Image.new("L", (120, 120), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, 119, 119), fill=255)
        out = Image.new("RGBA", (120, 120), (255, 255, 255, 0))
        out.paste(img, (0, 0), mask)
        buf = _io.BytesIO()
        out.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""

LOGO_B64 = load_logo_b64()

def meta_get(path: str, params: dict | None = None) -> dict:
    p = {"access_token": META_TOKEN, "limit": 500}
    if params:
        p.update(params)
    r = requests.get(f"{META_BASE}{path}", params=p, timeout=30)
    r.raise_for_status()
    return r.json()

def notion_headers() -> dict:
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type":   "application/json",
    }

# ─── NOTION: BUSCAR PÁGINAS ───────────────────────────────────────────────────

def notion_get_pages(gestor_filter: str | None = None) -> list[dict]:
    """Busca todas as entradas ON do banco Notion (todos os gestores ou só 1)."""
    pages = []
    has_more = True
    start_cursor = None

    base_filter: list[dict] = [
        {"property": "Status", "status": {"equals": "ON"}},
    ]
    if gestor_filter:
        base_filter.append(
            {"property": "Gestor de Tráfego", "select": {"equals": gestor_filter}}
        )

    while has_more:
        body: dict = {
            "page_size": 100,
            "filter": {"and": base_filter},
        }
        if start_cursor:
            body["start_cursor"] = start_cursor
        r = requests.post(
            f"{NOTION_BASE}/databases/{NOTION_DB_ID}/query",
            headers=notion_headers(),
            json=body,
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        pages.extend(data.get("results", []))
        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")

    return pages


def extract_account_id(ca_value: str) -> str | None:
    if not ca_value:
        return None
    # Tenta fix de IDs incompletos
    ca_stripped = ca_value.strip()
    # Busca números de 15 ou 16 dígitos
    matches = re.findall(r"\b(\d{15,16})\b", ca_value)
    for m in matches:
        if m in ALL_VALID_ACCOUNTS:
            return m
        if m in ID_FIX:
            fixed = ID_FIX[m]
            if fixed in ALL_VALID_ACCOUNTS:
                return fixed
    return None


def parse_notion_page(page: dict) -> dict:
    props = page.get("properties", {})

    def rich_text(key):
        items = props.get(key, {}).get("rich_text", [])
        return "".join(t.get("plain_text", "") for t in items).strip()

    def title_text():
        for k, v in props.items():
            if v.get("type") == "title":
                items = v.get("title", [])
                text = "".join(t.get("plain_text", "") for t in items).strip()
                if text:
                    return text
        return ""

    def select_val(key):
        s = props.get(key, {}).get("select")
        return s.get("name", "") if s else ""

    def url_val(key):
        return props.get(key, {}).get("url") or ""

    clinic_name = title_text()
    ca_field = rich_text("C.A") or rich_text("CA")
    gestor = select_val("Gestor de Tráfego")
    rel_novo = url_val("Relatório Novo")
    campaign_name_hint = rich_text("Nome da campanha")

    return {
        "page_id":        page["id"],
        "clinic_name":    clinic_name,
        "gestor":         gestor,
        "ca_field":       ca_field,
        "account_id":     extract_account_id(ca_field),
        "rel_novo":       rel_novo,
        "campaign_hint":  campaign_name_hint,
    }

# ─── META API ─────────────────────────────────────────────────────────────────

_campaign_cache: dict[str, list[dict]] = {}

def fetch_campaigns_for_account(account_id: str) -> list[dict]:
    if account_id in _campaign_cache:
        return _campaign_cache[account_id]
    campaigns = []
    for status in (["ACTIVE"], ["PAUSED", "CAMPAIGN_PAUSED"]):
        try:
            resp = meta_get(f"/act_{account_id}/campaigns", {
                "fields": "id,name,effective_status",
                "effective_status": json.dumps(status),
                "limit": 500,
            })
            campaigns.extend(resp.get("data", []))
            time.sleep(0.2)
        except Exception as e:
            print(f"    [WARN] Conta {account_id} status {status}: {e}")
    _campaign_cache[account_id] = campaigns
    return campaigns


def find_campaign(campaigns: list[dict], clinic_name: str, hint: str) -> dict | None:
    if not campaigns:
        return None
    active = [c for c in campaigns if c.get("effective_status") == "ACTIVE"]
    pool = active if active else campaigns

    # 1) Hint exato
    if hint:
        hint_l = hint.strip().lower()
        for c in pool:
            if c["name"].strip().lower() == hint_l:
                return c
        for c in pool:
            if hint_l in c["name"].lower():
                return c

    # 2) Número da clínica
    num_m = re.match(r"^(\d+)", clinic_name.strip())
    if num_m:
        num = num_m.group(1)
        for c in pool:
            if num in c["name"]:
                return c

    # 3) Palavras-chave (>3 chars, não número)
    words = [w for w in re.split(r"[\s\-_/]+", clinic_name) if len(w) > 3 and not w.isdigit()]
    for word in words:
        wn = norm(word)
        for c in pool:
            if wn in norm(c["name"]):
                return c

    # 4) Primeira ativa
    return pool[0] if pool else None


def find_all_active_campaigns(campaigns: list[dict], clinic_name: str, hint: str) -> list[dict]:
    """Para clínicas com múltiplas campanhas ativas, retorna todas."""
    active = [c for c in campaigns if c.get("effective_status") == "ACTIVE"]
    if not active:
        best = find_campaign(campaigns, clinic_name, hint)
        return [best] if best else []

    # Se só uma ativa, retorna ela
    if len(active) == 1:
        return active

    # Filtra pelas que têm match com a clínica
    matched = []
    num_m = re.match(r"^(\d+)", clinic_name.strip())
    if num_m:
        num = num_m.group(1)
        matched = [c for c in active if num in c["name"]]
    if not matched:
        words = [w for w in re.split(r"[\s\-_/]+", clinic_name) if len(w) > 3 and not w.isdigit()]
        for word in words:
            wn = norm(word)
            matched = [c for c in active if wn in norm(c["name"])]
            if matched:
                break
    return matched if matched else [active[0]]


def fetch_daily_insights(campaign_id: str, since: str, until: str) -> list[dict]:
    try:
        resp = meta_get(f"/{campaign_id}/insights", {
            "fields": "date_start,spend,actions,impressions,cpm,ctr",
            "time_range": json.dumps({"since": since, "until": until}),
            "time_increment": "1",
            "limit": 400,   # janela de 40+ dias: 50 truncaria os dias mais antigos
        })
        rows = resp.get("data", [])
        time.sleep(0.25)

        daily = []
        for row in rows:
            # Conversão unificada: conversas iniciadas (campanhas de mensagem)
            # OU preenchimentos de formulário nativo (campanhas lead gen ON_AD).
            # 1 lead de formulário conta como 1 mensagem. Usamos max() em vez de
            # soma porque campanhas de formulário puro ainda registram algumas
            # mensagens incidentais — somar contaria a mesma pessoa duas vezes.
            conv_msg = 0
            form_leads = 0
            for a in row.get("actions", []):
                at = a.get("action_type")
                try:
                    v = int(float(a["value"]))
                except Exception:
                    continue
                if at == "onsite_conversion.messaging_conversation_started_7d":
                    conv_msg += v
                elif at == "onsite_conversion.lead_grouped":
                    form_leads += v
            msgs = max(conv_msg, form_leads)
            spend = float(row.get("spend", 0))
            impr  = int(row.get("impressions", 0))
            cpm   = float(row.get("cpm", 0))
            ctr   = float(row.get("ctr", 0))
            cost_msg = round(spend / msgs, 2) if msgs > 0 else 0.0
            daily.append({
                "date": row["date_start"],
                "spend": round(spend, 2),
                "msgs":  msgs,
                "cost_msg": cost_msg,
                "impr": impr,
                "cpm":  round(cpm, 2),
                "ctr":  round(ctr, 2),
            })
        daily.sort(key=lambda x: x["date"], reverse=True)
        return daily
    except Exception as e:
        print(f"    [ERROR] Insights {campaign_id}: {e}")
        return []


def load_existing_daily(html_path) -> list[dict]:
    """Lê o array DAILY do relatório já publicado (histórico acumulado).
    Retorna [] se o arquivo não existe ou não tem DAILY."""
    try:
        p = Path(html_path)
        if not p.exists():
            return []
        m = re.search(r'const DAILY = (\[.*?\]);', p.read_text(encoding="utf-8"), flags=re.S)
        return json.loads(m.group(1)) if m else []
    except Exception:
        return []


def accumulate_daily(existing: list[dict], fresh: list[dict]) -> list[dict]:
    """Une o histórico já publicado com os dias recém-buscados.
    Dias novos são acrescentados; dias que voltaram na busca são atualizados
    (a atribuição do Meta muda nos primeiros dias). Nenhum dia é apagado."""
    by_date = {d["date"]: d for d in existing if isinstance(d, dict) and d.get("date")}
    for d in fresh:
        by_date[d["date"]] = d
    return sorted(by_date.values(), key=lambda x: x["date"], reverse=True)


def merge_daily(all_daily: list[list[dict]]) -> list[dict]:
    """Consolida insights de múltiplas campanhas por data (soma spend + msgs)."""
    by_date: dict[str, dict] = {}
    for daily in all_daily:
        for row in daily:
            d = row["date"]
            if d not in by_date:
                by_date[d] = {"date": d, "spend": 0.0, "msgs": 0, "impr": 0, "cpm": 0.0, "ctr": 0.0, "_n": 0}
            by_date[d]["spend"] += row["spend"]
            by_date[d]["msgs"]  += row["msgs"]
            by_date[d]["impr"]  += row["impr"]
            # CPM e CTR: média ponderada simplificada
            by_date[d]["_n"] += 1
            by_date[d]["cpm"] += row["cpm"]
            by_date[d]["ctr"] += row["ctr"]

    result = []
    for d, v in sorted(by_date.items(), reverse=True):
        n = max(v["_n"], 1)
        result.append({
            "date": d,
            "spend": round(v["spend"], 2),
            "msgs":  v["msgs"],
            "cost_msg": round(v["spend"] / v["msgs"], 2) if v["msgs"] > 0 else 0.0,
            "impr": v["impr"],
            "cpm":  round(v["cpm"] / n, 2),
            "ctr":  round(v["ctr"] / n, 2),
        })
    return result

# ─── HTML ─────────────────────────────────────────────────────────────────────

def generate_html(clinic_name: str, campaigns: list[dict], account_id: str, daily: list[dict],
                  fixed_since: str = FIXED_SINCE, fixed_until: str = FIXED_UNTIL) -> str:
    camp_names  = " + ".join(c.get("name", "—") for c in campaigns[:3])
    if len(campaigns) > 3:
        camp_names += f" (+{len(campaigns)-3})"
    camp_status  = campaigns[0].get("effective_status", "UNKNOWN") if campaigns else "UNKNOWN"
    status_color = "#42b72a" if camp_status == "ACTIVE" else "#e2a01d"
    status_label = "Ativa" if camp_status == "ACTIVE" else "Pausada"
    dot_color    = status_color
    gen_date     = date.today().strftime("%d/%m/%Y")
    daily_json   = json.dumps(daily, ensure_ascii=False)
    logo_html    = f'<img class="dbout-logo" src="data:image/png;base64,{LOGO_B64}" alt="Dbout"/>' if LOGO_B64 else ""
    default_days = DEFAULT_DISPLAY

    html = f"""<!DOCTYPE html>
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
.header-left{{display:flex;align-items:center;gap:10px}}
.fb-wordmark{{font-size:22px;font-weight:800;color:#1877f2;line-height:1}}
.fb-sub{{font-size:11px;color:#606770;font-weight:500}}
.dbout-logo{{width:52px;height:52px;border-radius:50%;object-fit:cover;box-shadow:0 2px 8px rgba(0,0,0,.15);border:1px solid #e8e8e8;flex-shrink:0}}
.camp-info{{background:#fff;border-radius:8px;padding:13px 20px;margin-bottom:16px;
           box-shadow:0 1px 3px rgba(0,0,0,.1);display:flex;align-items:center;gap:12px}}
.camp-dot{{width:10px;height:10px;border-radius:50%;background:{dot_color};flex-shrink:0}}
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
.day-picker{{margin-top:14px;padding-top:12px;border-top:1px solid #e4e6eb}}
.day-picker-label{{font-size:10px;font-weight:700;color:#606770;text-transform:uppercase;
                  letter-spacing:.4px;margin-bottom:8px}}
.day-btns{{display:flex;flex-wrap:wrap;gap:5px;max-height:132px;overflow-y:auto;padding-right:4px}}
.day-btn{{padding:5px 9px;border-radius:6px;font-size:10.5px;font-weight:600;cursor:pointer;
         border:1px solid #dddfe2;background:#fff;color:#606770;white-space:nowrap;line-height:1.3}}
.day-btn:hover{{border-color:#1877f2;color:#1877f2}}
.day-btn.active{{background:#1877f2;color:#fff;border-color:#1877f2}}
.day-btn.weekend{{background:#fffbe6;color:#8a6d1d;border-color:#f0e2b6}}
.day-btn.weekend.active{{background:#1877f2;color:#fff;border-color:#1877f2}}
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
@media(max-width:620px){{
  .kpi-grid{{grid-template-columns:1fr}}
  #dateRangeInput{{min-width:220px}}
}}
</style>
</head>
<body>
<div class="page">

<div class="header">
  <div class="header-left">
    <div>
      <div class="fb-wordmark">facebook</div>
      <div class="fb-sub">Ads</div>
    </div>
  </div>
  {logo_html}
</div>

<div class="camp-info">
  <div class="camp-dot"></div>
  <div>
    <div class="camp-name">{camp_names}</div>
    <div class="camp-status">{status_label}</div>
  </div>
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
    <button class="ps-btn" onclick="applyShortcut(45)">Últimos 45 dias</button>
  </div>
  <div class="day-picker">
    <div class="day-picker-label">Ou escolha um dia específico</div>
    <div class="day-btns" id="dayBtns"></div>
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
  <div class="section-sub">Diário · Histórico completo</div>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th style="text-align:left">Dia</th>
          <th>Valor Investido</th>
          <th>Mensagens</th>
          <th>Custo/Msg</th>
          <th>Impressões</th>
          <th>CPM</th>
          <th>CTR</th>
        </tr>
      </thead>
      <tbody id="tableBody"></tbody>
    </table>
  </div>
</div>

<div class="footer">
  Gerado em {gen_date} · {clinic_name} · Meta API v21.0
</div>
</div>

<script>
const DAILY = {daily_json};
const DEFAULT_DAYS = {default_days};
const FIXED_SINCE = '{fixed_since}';
const FIXED_UNTIL = '{fixed_until}';
const PT_M = ['jan','fev','mar','abr','mai','jun','jul','ago','set','out','nov','dez'];
const PT_MF = ['janeiro','fevereiro','março','abril','maio','junho','julho','agosto','setembro','outubro','novembro','dezembro'];
let chart=null, activeSince=null, activeUntil=null;
function fmtBRL(v){{return 'R$ '+Number(v).toLocaleString('pt-BR',{{minimumFractionDigits:2,maximumFractionDigits:2}})}}
function fmtNum(v){{return Number(v).toLocaleString('pt-BR')}}
function fmtShort(iso){{const[y,m,d]=iso.split('-');return `${{+d}} de ${{PT_M[+m-1]}}.`}}
function fmtFull(iso){{const[y,m,d]=iso.split('-');return `${{+d}} de ${{PT_MF[+m-1]}} de ${{y}}`}}
function addDays(iso,n){{const d=new Date(iso+'T12:00:00');d.setDate(d.getDate()+n);return d.toISOString().slice(0,10)}}
function today(){{return DAILY.length>0?DAILY[0].date:new Date().toISOString().slice(0,10)}}
const minDate=DAILY.length>0?DAILY[DAILY.length-1].date:undefined;
const maxDate=DAILY.length>0?DAILY[0].date:undefined;
const fp=flatpickr('#dateRangeInput',{{
  mode:'range',locale:'pt',dateFormat:'d \\de M. \\de Y',
  minDate,maxDate,showMonths:1,
  onChange(selectedDates){{
    if(selectedDates.length===2){{
      clearShortcuts(); clearDayButtons();
      applyRange(selectedDates[0].toISOString().slice(0,10),selectedDates[1].toISOString().slice(0,10));
    }}
  }}
}});
function applyShortcut(days){{
  clearShortcuts(); clearDayButtons();
  const btns=document.querySelectorAll('.ps-btn');
  const idx=[0,1,7,15,30,45].indexOf(days);
  if(idx>=0)btns[idx].classList.add('active');
  const until=today();
  const since=days===0?until:days===1?addDays(until,-1):addDays(until,-(days-1));
  const sinceEnd=days===1?addDays(until,-1):until;
  fp.setDate([since,sinceEnd],false);
  applyRange(since,sinceEnd);
}}
function clearShortcuts(){{document.querySelectorAll('.ps-btn').forEach(b=>b.classList.remove('active'))}}
const PT_WD=['Dom','Seg','Ter','Qua','Qui','Sex','Sáb'];
function buildDayButtons(){{
  const box=document.getElementById('dayBtns'); if(!box)return;
  box.innerHTML='';
  // DAILY vem ordenado do mais recente para o mais antigo
  DAILY.forEach(d=>{{
    const dt=new Date(d.date+'T12:00:00');
    const wd=dt.getDay();
    const b=document.createElement('button');
    b.className='day-btn'+(wd===0||wd===6?' weekend':'');
    b.dataset.date=d.date;
    b.textContent=`${{PT_WD[wd]}} ${{d.date.slice(8,10)}}/${{d.date.slice(5,7)}}`;
    b.onclick=()=>selectSingleDay(d.date);
    box.appendChild(b);
  }});
}}
function clearDayButtons(){{document.querySelectorAll('.day-btn').forEach(b=>b.classList.remove('active'))}}
function selectSingleDay(iso){{
  clearShortcuts(); clearDayButtons();
  const b=document.querySelector(`.day-btn[data-date="${{iso}}"]`);
  if(b)b.classList.add('active');
  fp.setDate([iso,iso],false);
  applyRange(iso,iso);
}}
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
  document.getElementById('kpi-cpmsg-sub').textContent='';
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
    options:{{
      responsive:true,maintainAspectRatio:false,
      interaction:{{mode:'index',intersect:false}},
      plugins:{{
        legend:{{display:true,position:'top',align:'start',
          labels:{{font:{{size:11,family:'Inter'}},color:'#606770',boxWidth:14,padding:14,usePointStyle:true}}}},
        tooltip:{{backgroundColor:'#fff',titleColor:'#1c1e21',bodyColor:'#606770',
          borderColor:'#dddfe2',borderWidth:1,padding:10,
          callbacks:{{label(c){{return c.dataset.label==='Valor Investido'?' '+fmtBRL(c.raw):' '+fmtNum(c.raw)+' msgs'}}}}}}
      }},
      scales:{{
        yL:{{type:'linear',position:'left',beginAtZero:true,
            title:{{display:true,text:'Mensagens Iniciadas',color:'#606770',font:{{size:10}}}},
            ticks:{{color:'#606770',font:{{size:10}}}},grid:{{color:'rgba(0,0,0,.05)'}}}},
        yR:{{type:'linear',position:'right',beginAtZero:true,
            title:{{display:true,text:'Valor Investido',color:'#606770',font:{{size:10}}}},
            ticks:{{color:'#606770',font:{{size:10}},callback:v=>'R$'+v.toFixed(0)}},
            grid:{{display:false}}}},
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
    const label=`${{+day}} de ${{PT_M[+m-1]}}.`;
    const cpClass=d.cost_msg<=10?'td-good':d.cost_msg<=15?'td-warn':'td-bad';
    const tr=document.createElement('tr');
    if(isToday)tr.className='today-row';
    else if(!inSel)tr.className='out-range';
    tr.innerHTML=`
      <td>${{label}}${{isToday?'<span class="today-badge">HOJE</span>':''}}${{inSel&&!isToday?'<span class="range-badge">✓</span>':''}}</td>
      <td class="td-spend">${{fmtBRL(d.spend)}}</td>
      <td class="td-msgs">${{fmtNum(d.msgs)}}</td>
      <td class="${{cpClass}}">${{fmtBRL(d.cost_msg)}}</td>
      <td>${{fmtNum(d.impr)}}</td>
      <td>${{fmtBRL(d.cpm)}}</td>
      <td>${{d.ctr.toFixed(2)}}%</td>
    `;
    tbody.appendChild(tr);
  }});
}}
window.addEventListener('load',()=>{{
  // Abre nos últimos 15 dias por padrão. O histórico completo continua
  // disponível no calendário, nos atalhos e nos botões dia a dia.
  buildDayButtons();
  applyRange("2026-08-01","2026-08-15");
}});
</script>
</body>
</html>"""
    return html

# ─── NOTION UPDATE ────────────────────────────────────────────────────────────

def notion_update_relatorio_novo(page_id: str, url: str) -> bool:
    try:
        r = requests.patch(
            f"{NOTION_BASE}/pages/{page_id}",
            headers=notion_headers(),
            json={"properties": {"Relatório Novo": {"url": url}}},
            timeout=30,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"    [ERROR] Notion update {page_id}: {e}")
        return False


def notion_get_blocks(page_id: str) -> list[dict]:
    try:
        r = requests.get(
            f"{NOTION_BASE}/blocks/{page_id}/children",
            headers=notion_headers(),
            params={"page_size": 100},
            timeout=30,
        )
        r.raise_for_status()
        return r.json().get("results", [])
    except Exception:
        return []


def notion_update_preview_image(page_id: str, png_url: str) -> bool:
    """Cria ou atualiza bloco de preview (heading_3 + image) na página Notion.
    Adiciona cache-buster ?v=<timestamp> para forçar Notion a re-baixar a imagem."""
    # Cache-buster: garante refresh do CDN do Notion
    sep = '&' if '?' in png_url else '?'
    png_url = f"{png_url}{sep}v={int(time.time())}"
    blocks = notion_get_blocks(page_id)

    # Procura bloco de imagem existente
    img_block_id = None
    heading_block_id = None
    for b in blocks:
        if b.get("type") == "heading_3":
            texts = b.get("heading_3", {}).get("rich_text", [])
            if any("Preview do Relatório" in t.get("plain_text", "") for t in texts):
                heading_block_id = b["id"]
        if b.get("type") == "image" and heading_block_id:
            img_block_id = b["id"]
            break

    if img_block_id:
        # Atualiza imagem existente (Notion PATCH não aceita 'type', só o objeto direto)
        try:
            r = requests.patch(
                f"{NOTION_BASE}/blocks/{img_block_id}",
                headers=notion_headers(),
                json={"image": {"external": {"url": png_url}}},
                timeout=30,
            )
            r.raise_for_status()
            return True
        except Exception as e:
            print(f"    [WARN] Atualizar imagem: {e}")

    # Adiciona novos blocos
    try:
        payload = {"children": [
            {"object": "block", "type": "heading_3",
             "heading_3": {"rich_text": [{"type": "text", "text": {"content": "📊 Preview do Relatório"}}]}},
            {"object": "block", "type": "image",
             "image": {"type": "external", "external": {"url": png_url}}}
        ]}
        r = requests.patch(
            f"{NOTION_BASE}/blocks/{page_id}/children",
            headers=notion_headers(), json=payload, timeout=30,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"    [ERROR] Adicionar blocos: {e}")
        return False

# ─── SCREENSHOTS ──────────────────────────────────────────────────────────────

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args): pass

_active_port: int = 0

def start_local_server(directory: str, port: int) -> int:
    """Inicia servidor HTTP local; port=0 → escolhe porta livre. Retorna porta usada."""
    global _active_port
    os.chdir(directory)
    server = http.server.HTTPServer(("", port), QuietHandler)
    _active_port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return _active_port

async def take_screenshots_async(items: list[dict], port: int) -> None:
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 920, "height": 800})
        page = await ctx.new_page()
        for item in items:
            try:
                url = f"http://localhost:{port}/{item['html_filename']}"
                await page.goto(url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(2000)
                await page.screenshot(path=str(item["png_path"]), full_page=True)
                print(f"    📸 {item['slug']}")
            except Exception as e:
                print(f"    [ERROR] Screenshot {item['slug']}: {e}")
        await browser.close()

def take_screenshots(items: list[dict], port: int) -> None:
    import asyncio
    asyncio.run(take_screenshots_async(items, port))

# ─── GIT ─────────────────────────────────────────────────────────────────────

def git_commit_and_push(files: list[Path], message: str) -> bool:
    repo = str(BASE_DIR)
    try:
        file_args = [str(f) for f in files]
        subprocess.run(["git", "-C", repo, "add"] + file_args, check=True, capture_output=True)
        subprocess.run(["git", "-C", repo, "commit", "-m", message], check=True, capture_output=True)
        print(f"  ✅ Commit: {message}")
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode() if e.stderr else str(e)
        if "nothing to commit" in err:
            print("  (nada para commitar)")
            return True
        print(f"  [ERROR] Commit: {err[:200]}")
        return False
    try:
        subprocess.run(["git", "-C", repo, "push", "origin", "main"],
                       check=True, capture_output=True, timeout=120)
        print("  ✅ Push realizado → GitHub Pages")
        return True
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode() if e.stderr else str(e)
        print(f"  [ERROR] Push: {err[:200]}")
        return False

# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    # Parse args
    gestor_filter = None
    test_clinic   = None
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--gestor" and i + 1 < len(args):
            key = args[i+1].lower()
            gestor_filter = GESTOR_FILTER_MAP.get(key, args[i+1])
            i += 2
        elif args[i] == "--test" and i + 1 < len(args):
            test_clinic = args[i+1]
            i += 2
        else:
            i += 1

    label = gestor_filter or (f"teste: {test_clinic}" if test_clinic else "TODOS os gestores")
    print("=" * 70)
    print(f"Gerando relatórios — {label}")
    print("=" * 70)

    # 1) Buscar páginas do Notion
    print("\n[1/6] Buscando páginas Notion...")
    try:
        pages = notion_get_pages(gestor_filter)
    except Exception as e:
        print(f"  [ERRO] Notion: {e}")
        return
    print(f"  → {len(pages)} páginas ON encontradas")

    # 2) Parsear e filtrar
    entries = []
    sem_conta = []
    for page in pages:
        parsed = parse_notion_page(page)
        if test_clinic and norm(test_clinic) not in norm(parsed["clinic_name"]):
            continue
        if parsed["account_id"]:
            entries.append(parsed)
        else:
            sem_conta.append(parsed)

    print(f"  → {len(entries)} com conta válida | {len(sem_conta)} sem conta")

    if not entries:
        print("  Nenhuma entrada para processar.")
        return

    # 3) Buscar campanhas (cache por conta)
    print(f"\n[2/6] Buscando campanhas...")
    account_ids = list(set(e["account_id"] for e in entries))
    for acct in account_ids:
        print(f"  Conta {acct}...", end=" ", flush=True)
        camps = fetch_campaigns_for_account(acct)
        print(f"{len(camps)} campanhas")
        time.sleep(0.2)

    # 4) Insights diários — período fixo 15/04 → 01/05
    today = date.today()
    since = FIXED_SINCE
    until = FIXED_UNTIL
    print(f"\n[3/6] Insights diários ({since} → {until})...")

    resultados = []
    sem_campanha = []
    com_erro = []

    for entry in entries:
        acct  = entry["account_id"]
        clinic = entry["clinic_name"]
        hint   = entry["campaign_hint"]
        print(f"\n  [{clinic}]")

        campaigns = _campaign_cache.get(acct, [])

        # Busca múltiplas campanhas ativas se necessário
        matching_camps = find_all_active_campaigns(campaigns, clinic, hint)
        if not matching_camps:
            print(f"    ⚠ Campanha não encontrada")
            sem_campanha.append(entry)
            continue

        camp_labels = ", ".join(f"{c['name'][:40]} ({c.get('effective_status','')})" for c in matching_camps[:2])
        print(f"    → {len(matching_camps)} campanha(s): {camp_labels}")

        # Busca insights de todas as campanhas
        all_daily = []
        for camp in matching_camps:
            d = fetch_daily_insights(camp["id"], since, until)
            if d:
                all_daily.append(d)

        daily = merge_daily(all_daily) if all_daily else []
        if not daily:
            print(f"    ⚠ Sem dados de insights (relatório com dados zerados)")

        slug          = slugify(clinic)
        html_filename = f"relatorio_{slug}.html"
        png_filename  = f"relatorio_{slug}.png"
        html_path     = BASE_DIR / html_filename
        png_path      = BASE_DIR / png_filename

        html_content = generate_html(clinic, matching_camps, acct, daily, since, until)
        try:
            html_path.write_text(html_content, encoding="utf-8")
            print(f"    → HTML: {html_filename}")
        except Exception as e:
            print(f"    [ERROR] Escrever HTML: {e}")
            com_erro.append(entry)
            continue

        resultados.append({
            "entry": entry,
            "campaigns": matching_camps,
            "slug": slug,
            "html_filename": html_filename,
            "png_filename": png_filename,
            "html_path": html_path,
            "png_path": png_path,
        })

    # 5) Screenshots
    if resultados:
        print(f"\n[4/6] Screenshots ({len(resultados)} clínicas)...")
        port = start_local_server(str(BASE_DIR), LOCAL_PORT)
        print(f"  → Servidor local na porta {port}")
        time.sleep(1)
        screenshot_items = [
            {"slug": r["slug"], "html_filename": r["html_filename"], "png_path": r["png_path"]}
            for r in resultados
        ]
        take_screenshots(screenshot_items, port)

    # 6) Git commit + push
    print("\n[5/6] Git commit + push...")
    all_files = []
    for r in resultados:
        all_files.append(r["html_path"])
        if r["png_path"].exists():
            all_files.append(r["png_path"])
    if all_files:
        gestores_set = set(r["entry"]["gestor"] for r in resultados)
        gestores_str = ", ".join(sorted(gestores_set)) or "todos"
        msg = f"Relatórios {gestores_str} — {len(resultados)} clínicas — {today.isoformat()}"
        git_commit_and_push(all_files, msg)

    # 7) Atualizar Notion
    print("\n[6/6] Atualizando Notion...")
    for r in resultados:
        entry = r["entry"]
        slug  = r["slug"]
        html_url = f"{GH_PAGES_BASE}/{r['html_filename']}"
        png_url  = f"{GH_PAGES_BASE}/{r['png_filename']}"

        print(f"  [{entry['clinic_name']}]")
        ok1 = notion_update_relatorio_novo(entry["page_id"], html_url)
        if ok1:
            print(f"    → Relatório Novo: {html_url}")
        time.sleep(0.3)

        ok2 = notion_update_preview_image(entry["page_id"], png_url)
        if ok2:
            print(f"    → Preview imagem atualizada")
        time.sleep(0.3)

    # Relatório final
    print("\n" + "=" * 70)
    print("RESULTADO FINAL")
    print("=" * 70)
    print(f"✅ Sucesso:        {len(resultados)}")
    print(f"⚠  Sem campanha:  {len(sem_campanha)}")
    print(f"⚠  Sem conta:     {len(sem_conta)}")
    print(f"❌ Com erro:       {len(com_erro)}")

    if sem_campanha:
        print("\n⚠  Sem campanha:")
        for e in sem_campanha:
            print(f"   - {e['clinic_name']} (conta: {e['account_id']})")

    if sem_conta:
        print("\n⚠  Sem conta:")
        for e in sem_conta:
            print(f"   - {e['clinic_name']} (C.A: '{e['ca_field']}')")

    print()


if __name__ == "__main__":
    main()
