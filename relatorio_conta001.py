#!/usr/bin/env /Library/Frameworks/Python.framework/Versions/3.14/bin/python3
"""
Relatório — CONTA 001 (310500857276337)
Polos: SJRP, Joinville, Bento Gonçalves+Serra, Arapongas
Campanhas de Vendas: todas as OUTCOME_SALES ativas
Envia via Telegram.
"""

import os, json, requests
from datetime import date, timedelta
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(dotenv_path=Path("/Users/alexrangelalves/Downloads/Conexão mtds/.env"))

TOKEN      = os.getenv("META_ACCESS_TOKEN")
ACCOUNT_ID = "310500857276337"
BASE       = "https://graph.facebook.com/v21.0"

TELEGRAM_BOT_TOKEN = "8599130496:AAGFNj6JYinKyjEELoX6VuMmPYm8CD6Bo8Y"
TELEGRAM_CHAT_ID   = "966407012"

# Fragmentos que identificam cada grupo de polo (case-insensitive)
POLO_GROUPS = {
    "POLOS SJRP":              ["POLOS SJRP"],
    "JOINVILLE S DO SUL":      ["JOINVILLE"],
    "Bento Gonçalves + Serra": ["BENTO", "SERRA G"],
    "POLOS ARAPONGAS":         ["ARAPONGAS"],
}

def meta_get(path, params=None):
    p = {"access_token": TOKEN}
    if params:
        p.update(params)
    r = requests.get(f"{BASE}{path}", params=p, timeout=30)
    return r.json()

def all_campaigns(objective=None, status=None):
    """Busca campanhas. objective ex: 'OUTCOME_SALES'. status ex: ['ACTIVE']."""
    params = {
        "fields": "id,name,effective_status,objective",
        "effective_status": json.dumps(status or ["ACTIVE", "PAUSED"]),
        "limit": 200,
    }
    resp = meta_get(f"/act_{ACCOUNT_ID}/campaigns", params)
    camps = resp.get("data", [])
    if objective:
        camps = [c for c in camps if c.get("objective") == objective]
    return camps

def match_group(camp_name, fragments):
    n = camp_name.upper()
    return any(f.upper() in n for f in fragments)

def get_insights(camp_id, since, until):
    """Retorna (spend, leads, impressions, clicks) para o período."""
    resp = meta_get(f"/{camp_id}/insights", {
        "fields": "spend,impressions,actions,clicks",
        "time_range": json.dumps({"since": since, "until": until}),
    })
    data = resp.get("data", [{}])
    if not data:
        return 0.0, 0, 0, 0

    row     = data[0]
    spend   = float(row.get("spend", 0))
    impress = int(row.get("impressions", 0))
    clicks  = int(row.get("clicks", 0))
    leads   = 0
    for a in row.get("actions", []):
        if a["action_type"] in ("lead", "onsite_conversion.lead_grouped",
                                 "onsite_conversion.messaging_first_reply",
                                 "onsite_conversion.messaging_conversation_started_7d"):
            leads += int(float(a["value"]))
    return spend, leads, impress, clicks

def get_insights_vendas(camp_id, since, until):
    """Retorna (spend, purchases, impressions, clicks) para campanhas de vendas."""
    resp = meta_get(f"/{camp_id}/insights", {
        "fields": "spend,impressions,actions,clicks",
        "time_range": json.dumps({"since": since, "until": until}),
    })
    data = resp.get("data", [{}])
    if not data:
        return 0.0, 0, 0, 0

    row       = data[0]
    spend     = float(row.get("spend", 0))
    impress   = int(row.get("impressions", 0))
    clicks    = int(row.get("clicks", 0))
    purchases = 0
    for a in row.get("actions", []):
        if a["action_type"] in ("purchase", "omni_purchase",
                                 "offsite_conversion.fb_pixel_purchase"):
            purchases += int(float(a["value"]))
    return spend, purchases, impress, clicks

def fmt_cpl(spend, leads):
    if leads > 0:
        return f"R${spend/leads:.2f}"
    return "—"

def fmt_cpv(spend, purchases):
    if purchases > 0:
        return f"R${spend/purchases:.2f}"
    return "—"

def fmt_ctr(clicks, impress):
    if impress > 0:
        return f"{clicks/impress*100:.2f}%"
    return "—"

def fmt_money(v):
    return f"R${v:,.2f}".replace(",","X").replace(".",",").replace("X",".")

def shorten_name(name, max_len=35):
    """Remove prefixos de bracket e limita tamanho."""
    # Remove tudo entre [ ] para deixar mais legível
    import re
    clean = re.sub(r'\[([^\]]*)\]', r'\1', name).strip(' —-')
    clean = re.sub(r'\s+', ' ', clean)
    return clean[:max_len] + ("…" if len(clean) > max_len else "")

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    r = requests.post(url, data={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
    }, timeout=15)
    return r.json()

def gerar_relatorio(since=None, until=None):
    today     = date.today().strftime("%Y-%m-%d")
    yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    since     = since or today
    until     = until or today

    # ── LEADS (polos) ──────────────────────────────────────────────────
    all_camps = all_campaigns()
    grupos = {}
    for label, frags in POLO_GROUPS.items():
        matched = [c for c in all_camps if match_group(c["name"], frags)]
        if matched:
            grupos[label] = matched

    linhas_periodo = []
    linhas_hoje    = []
    linhas_ontem   = []

    for label, matched_camps in grupos.items():
        sp_p = leads_p = imp_p = cl_p = 0
        sp_h = leads_h = imp_h = cl_h = 0
        sp_o = leads_o = imp_o = cl_o = 0

        for c in matched_camps:
            s, l, i, cl = get_insights(c["id"], since, until)
            sp_p += s; leads_p += l; imp_p += i; cl_p += cl

            s, l, i, cl = get_insights(c["id"], today, today)
            sp_h += s; leads_h += l; imp_h += i; cl_h += cl

            s, l, i, cl = get_insights(c["id"], yesterday, yesterday)
            sp_o += s; leads_o += l; imp_o += i; cl_o += cl

        if sp_p > 0 or leads_p > 0:
            linhas_periodo.append(
                f"*[{label}]*\n"
                f"💰 Gasto: {fmt_money(sp_p)}\n"
                f"👥 Leads: {leads_p}\n"
                f"📉 CPL: {fmt_cpl(sp_p, leads_p)}\n"
                f"📊 CTR: {fmt_ctr(cl_p, imp_p)}"
            )

        if sp_h > 0 or leads_h > 0:
            linhas_hoje.append(
                f"*[{label}]*\n"
                f"💰 Gasto: {fmt_money(sp_h)}\n"
                f"👥 Leads: {leads_h}\n"
                f"📉 CPL: {fmt_cpl(sp_h, leads_h)}\n"
                f"📊 CTR: {fmt_ctr(cl_h, imp_h)}"
            )

        if sp_o > 0 or leads_o > 0:
            linhas_ontem.append(
                f"*[{label}]*\n"
                f"💰 Gasto: {fmt_money(sp_o)}\n"
                f"👥 Leads: {leads_o}\n"
                f"📉 CPL: {fmt_cpl(sp_o, leads_o)}\n"
                f"📊 CTR: {fmt_ctr(cl_o, imp_o)}"
            )

    # ── VENDAS (apenas campanhas OUTCOME_SALES ativas) ─────────────────
    sales_camps = all_campaigns(objective="OUTCOME_SALES", status=["ACTIVE"])
    vendas_periodo = []
    vendas_hoje    = []
    vendas_ontem   = []

    for c in sales_camps:
        nome = shorten_name(c["name"])

        sp_p, purch_p, imp_p, cl_p = get_insights_vendas(c["id"], since, until)
        sp_h, purch_h, imp_h, cl_h = get_insights_vendas(c["id"], today, today)
        sp_o, purch_o, imp_o, cl_o = get_insights_vendas(c["id"], yesterday, yesterday)

        if sp_p > 0 or purch_p > 0:
            vendas_periodo.append(
                f"*{nome}*\n"
                f"💰 Gasto: {fmt_money(sp_p)}\n"
                f"🛒 Vendas: {purch_p}\n"
                f"📉 CPV: {fmt_cpv(sp_p, purch_p)}"
            )

        if sp_h > 0 or purch_h > 0:
            vendas_hoje.append(
                f"*{nome}*\n"
                f"💰 Gasto: {fmt_money(sp_h)}\n"
                f"🛒 Vendas: {purch_h}\n"
                f"📉 CPV: {fmt_cpv(sp_h, purch_h)}"
            )

        if sp_o > 0 or purch_o > 0:
            vendas_ontem.append(
                f"*{nome}*\n"
                f"💰 Gasto: {fmt_money(sp_o)}\n"
                f"🛒 Vendas: {purch_o}\n"
                f"📉 CPV: {fmt_cpv(sp_o, purch_o)}"
            )

    # ── MONTA MENSAGEM ─────────────────────────────────────────────────
    since_fmt = date.fromisoformat(since).strftime("%d/%m")
    until_fmt = date.fromisoformat(until).strftime("%d/%m/%Y")

    msg = f"📊 *RELATÓRIO CONTA 001*\n"
    msg += f"_{since_fmt} → {until_fmt}_\n"

    # Acumulado — leads
    if linhas_periodo:
        msg += f"\n━━━━━━━━━━━━━━\n"
        msg += f"📅 *ACUMULADO — POLOS ({since_fmt} → {until_fmt})*\n"
        msg += "━━━━━━━━━━━━━━\n"
        msg += "\n\n".join(linhas_periodo)

    # Acumulado — vendas
    if vendas_periodo:
        msg += f"\n\n━━━━━━━━━━━━━━\n"
        msg += f"🛍️ *ACUMULADO — VENDAS ({since_fmt} → {until_fmt})*\n"
        msg += "━━━━━━━━━━━━━━\n"
        msg += "\n\n".join(vendas_periodo)

    # Hoje — leads
    if linhas_hoje:
        msg += f"\n\n━━━━━━━━━━━━━━\n"
        msg += f"🟢 *HOJE — POLOS*\n"
        msg += "━━━━━━━━━━━━━━\n"
        msg += "\n\n".join(linhas_hoje)

    # Hoje — vendas
    if vendas_hoje:
        msg += f"\n\n━━━━━━━━━━━━━━\n"
        msg += f"🟢 *HOJE — VENDAS*\n"
        msg += "━━━━━━━━━━━━━━\n"
        msg += "\n\n".join(vendas_hoje)

    # Ontem — leads
    if linhas_ontem:
        msg += f"\n\n━━━━━━━━━━━━━━\n"
        msg += f"🕐 *ONTEM — POLOS*\n"
        msg += "━━━━━━━━━━━━━━\n"
        msg += "\n\n".join(linhas_ontem)

    # Ontem — vendas
    if vendas_ontem:
        msg += f"\n\n━━━━━━━━━━━━━━\n"
        msg += f"🕐 *ONTEM — VENDAS*\n"
        msg += "━━━━━━━━━━━━━━\n"
        msg += "\n\n".join(vendas_ontem)

    if not any([linhas_periodo, vendas_periodo, linhas_hoje, vendas_hoje,
                linhas_ontem, vendas_ontem]):
        msg += "\n_Nenhuma campanha com dados no período._"

    return msg


def monday_of_week(ref: date) -> date:
    """Retorna a segunda-feira da semana de ref (weekday 0 = seg)."""
    return ref - timedelta(days=ref.weekday())


if __name__ == "__main__":
    import sys
    today_d = date.today()

    # Sem argumentos → segunda desta semana até hoje (relatório diário às 08h)
    # Com argumentos → uso manual: python relatorio_conta001.py [since] [until]
    if len(sys.argv) >= 3:
        since_arg = sys.argv[1]
        until_arg = sys.argv[2]
    elif len(sys.argv) == 2:
        since_arg = sys.argv[1]
        until_arg = today_d.strftime("%Y-%m-%d")
    else:
        since_arg = monday_of_week(today_d).strftime("%Y-%m-%d")
        until_arg = today_d.strftime("%Y-%m-%d")

    print(f"Buscando dados de {since_arg} até {until_arg}...")
    msg = gerar_relatorio(since=since_arg, until=until_arg)
    print(msg)
    print("\nEnviando via Telegram...")
    result = send_telegram(msg)
    if result.get("ok"):
        print("✅ Enviado com sucesso!")
    else:
        print(f"❌ Erro: {result}")
