#!/usr/bin/env /Library/Frameworks/Python.framework/Versions/3.14/bin/python3
"""
Busca dados diários de todas as contas do System User.
Incremental: mantém histórico e adiciona novos dias sem sobrescrever dados existentes.
Atualiza a cada 5 horas via cron.
"""

import os, json, requests, time
from datetime import datetime, date, timedelta
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

TOKEN = os.getenv("META_ACCESS_TOKEN")
BASE  = "https://graph.facebook.com/v21.0"
OUT   = os.path.join(os.path.dirname(__file__), "dashboard_data.json")

BRAGA_ACCOUNTS = [
    {"id": "795680591769062",  "name": "CT02 - Braga",                 "currency": "BRL"},
    {"id": "350266333900752",  "name": "CT03 - São José do Rio Preto", "currency": "BRL"},
    {"id": "613666203841045",  "name": "CT05 - Braga",                 "currency": "BRL"},
    {"id": "1534753857104914", "name": "CDC Odontologia",              "currency": "BRL"},
    {"id": "627225619698621",  "name": "Contagem",                     "currency": "BRL"},
    {"id": "684292170965131",  "name": "Dbout Aquec 02 CA01",          "currency": "BRL"},
    {"id": "1385771249133770", "name": "Dbout Aquec 02 CA02",          "currency": "BRL"},
    {"id": "1492720022172340", "name": "Dbout Aquec 02 CA03",          "currency": "BRL"},
    {"id": "784528807407228",  "name": "Mirassol Orthodontic CA01",    "currency": "BRL"},
    {"id": "1221130892436075", "name": "MOGI/SUZANO CA01",             "currency": "BRL"},
    {"id": "945748271201968",  "name": "CA 02 - RIO CLARO",            "currency": "BRL"},
]

IGOR_ACCOUNTS = [
    {"id": "5648874101844136", "name": "CT03 - Guaramirim - IGOR",          "currency": "BRL"},
    {"id": "449000287288780",  "name": "CT02 - Unaí - IGOR",                "currency": "BRL"},
    {"id": "1181454115989018", "name": "CT03 - Fhilipe - IGOR",             "currency": "BRL"},
    {"id": "1191525622298805", "name": "CT05 - DBOUT 02 - IGOR",            "currency": "BRL"},
    {"id": "412153471621510",  "name": "CT02 - MJOLNIR - IGOR",             "currency": "BRL"},
    {"id": "391009870578696",  "name": "AQC 00 - IGOR",                     "currency": "BRL"},
    {"id": "1583196522529565", "name": "CT01 - DRACO - IGOR",               "currency": "BRL"},
    {"id": "1329276834986407", "name": "Orthodontic Aparecida Goiânia IGOR","currency": "BRL"},
    {"id": "566170923166415",  "name": "Ortomais 1.1 - IGOR",               "currency": "BRL"},
    {"id": "1132321672289497", "name": "Brasil Odontologia Rio do Sul IGOR", "currency": "BRL"},
]

# Todos os gestores
GESTORES = [
    {"id": "thiago_braga",  "name": "Thiago Braga",  "accounts": BRAGA_ACCOUNTS},
    {"id": "igor_teixeira", "name": "Igor Teixeira",  "accounts": IGOR_ACCOUNTS},
]

ACCOUNTS = BRAGA_ACCOUNTS + IGOR_ACCOUNTS

# Busca últimos 7 dias a cada execução
FETCH_DAYS = 7
SINCE = (date.today() - timedelta(days=FETCH_DAYS - 1)).strftime("%Y-%m-%d")
UNTIL = date.today().strftime("%Y-%m-%d")
TIME_RANGE = json.dumps({"since": SINCE, "until": UNTIL})

# Mantém histórico de 30 dias
KEEP_DAYS = 30
CUTOFF = (date.today() - timedelta(days=KEEP_DAYS - 1)).strftime("%Y-%m-%d")

# Dias que sempre atualiza (hoje e ontem podem ter dados parciais)
ALWAYS_REFRESH = {
    date.today().strftime("%Y-%m-%d"),
    (date.today() - timedelta(days=1)).strftime("%Y-%m-%d"),
}


# ─── API ─────────────────────────────────────────────────────────────────────

def get(path, params=None):
    p = {"access_token": TOKEN}
    if params:
        p.update(params)
    try:
        r = requests.get(f"{BASE}{path}", params=p, timeout=30)
        data = r.json()
        if "error" in data:
            print(f"  API error: {data['error'].get('message','?')[:80]}")
            return {}
        return data
    except Exception as e:
        print(f"  Request error: {e}")
        return {}


def get_all_pages(path, params):
    results = []
    resp = get(path, params)
    results.extend(resp.get("data", []))
    while resp.get("paging", {}).get("next"):
        try:
            r = requests.get(resp["paging"]["next"], timeout=30)
            resp = r.json()
            results.extend(resp.get("data", []))
        except:
            break
    return results


# ─── PARSE ───────────────────────────────────────────────────────────────────

def parse_actions(row):
    msgs = purchases = add_cart = initiate = lpv = 0
    for a in row.get("actions", []):
        t = a["action_type"]
        v = int(float(a.get("value", 0)))
        if t in ("onsite_conversion.messaging_first_reply",
                 "onsite_conversion.send_message",
                 "onsite_conversion.messaging_conversation_started_7d"):
            msgs += v
        if t == "purchase":           purchases += v
        if t == "add_to_cart":        add_cart += v
        if t == "initiate_checkout":  initiate += v
        if t == "landing_page_view":  lpv += v

    cost_msg = 0
    for c in row.get("cost_per_action_type", []):
        if c["action_type"] in ("onsite_conversion.messaging_first_reply",
                                "onsite_conversion.send_message"):
            cost_msg = float(c.get("value", 0))

    spend = float(row.get("spend", 0))
    if msgs > 0 and cost_msg == 0:
        cost_msg = round(spend / msgs, 2)

    return {
        "msgs":      msgs,
        "cost_msg":  round(cost_msg, 2),
        "purchases": purchases,
        "add_cart":  add_cart,
        "initiate":  initiate,
        "lpv":       lpv,
    }


def aggregate_daily(daily_dict):
    """Soma todos os dias em um único objeto de métricas."""
    total = {"spend": 0, "impressions": 0, "msgs": 0, "lpv": 0,
             "purchases": 0, "add_cart": 0, "initiate": 0}
    for day_data in daily_dict.values():
        for k in total:
            total[k] += day_data.get(k, 0)
    total["spend"] = round(total["spend"], 2)
    total["cost_msg"] = round(total["spend"] / total["msgs"], 2) if total["msgs"] > 0 else 0
    total["cpm"] = round(total["spend"] / total["impressions"] * 1000, 2) if total["impressions"] > 0 else 0
    return total


# ─── HISTÓRICO ───────────────────────────────────────────────────────────────

def load_existing_ads():
    """Carrega dados existentes e retorna lookup por ad_id."""
    if not os.path.exists(OUT):
        return {}
    try:
        with open(OUT) as f:
            data = json.load(f)
        ad_lookup = {}
        # Suporta estrutura nova (gestores) e antiga (accounts direto)
        all_accounts = []
        if "gestores" in data:
            for g in data.get("gestores", []):
                all_accounts.extend(g.get("accounts", []))
        else:
            all_accounts = data.get("accounts", [])
        for acc in all_accounts:
            for camp in acc.get("campaigns", []):
                for ad in camp.get("ads", []):
                    ad_lookup[ad["id"]] = {
                        "thumbnail":     ad.get("thumbnail", ""),
                        "preview_url":   ad.get("preview_url", ""),
                        "age_breakdown": ad.get("age_breakdown", []),
                        "daily":         {
                            k: v for k, v in ad.get("daily", {}).items()
                            if k >= CUTOFF
                        },
                        "name":          ad.get("name", ""),
                        "adset":         ad.get("adset", ""),
                        "created_at":    ad.get("created_at", ""),
                        "updated_at":    ad.get("updated_at", ""),
                        "first_active":  ad.get("first_active", ""),
                    }
        print(f"  Histórico: {len(ad_lookup)} anúncios carregados")
        return ad_lookup
    except Exception as e:
        print(f"  Aviso: não foi possível carregar histórico ({e})")
        return {}


# ─── CONTA ───────────────────────────────────────────────────────────────────

def fetch_account(acc, ad_lookup):
    acct_id = acc["id"]
    print(f"\n  [{acc['name']}] act_{acct_id}")

    # 1. Campanhas ativas
    camps_raw = get_all_pages(f"/act_{acct_id}/campaigns", {
        "fields": "id,name,objective,effective_status",
        "effective_status": '["ACTIVE"]',
        "limit": 50,
    })
    if not camps_raw:
        print(f"    Sem campanhas ativas")
        return {"id": acct_id, "name": acc["name"], "currency": acc["currency"], "campaigns": []}

    print(f"    {len(camps_raw)} campanhas ativas")
    camp_ids = [c["id"] for c in camps_raw]

    # 2. Insights DIÁRIOS — últimos 7 dias (time_increment=1)
    print(f"    Buscando insights diários...")
    insights_raw = get_all_pages(f"/act_{acct_id}/insights", {
        "fields": "campaign_id,campaign_name,adset_id,adset_name,ad_id,ad_name,"
                  "date_start,spend,impressions,clicks,ctr,cpm,frequency,"
                  "actions,cost_per_action_type",
        "level": "ad",
        "time_range": TIME_RANGE,
        "time_increment": "1",
        "filtering": json.dumps([{"field": "campaign.id", "operator": "IN", "value": camp_ids}]),
        "limit": 500,
    })
    print(f"    {len(insights_raw)} linhas de insights diários")

    # 3. Age breakdown — aggregate últimos 7 dias
    print(f"    Buscando breakdown por idade...")
    age_raw = get_all_pages(f"/act_{acct_id}/insights", {
        "fields": "ad_id,spend,impressions,actions,cost_per_action_type",
        "level": "ad",
        "time_range": TIME_RANGE,
        "breakdowns": "age",
        "filtering": json.dumps([{"field": "campaign.id", "operator": "IN", "value": camp_ids}]),
        "limit": 500,
    })
    print(f"    {len(age_raw)} linhas de breakdown")

    # 4. Thumbnails e status
    print(f"    Buscando thumbnails...")
    ads_meta_raw = get_all_pages(f"/act_{acct_id}/ads", {
        "fields": "id,name,effective_status,created_time,updated_time,creative{thumbnail_url}",
        "filtering": json.dumps([{"field": "campaign.id", "operator": "IN", "value": camp_ids}]),
        "limit": 200,
    })
    thumb_map   = {}
    status_map  = {}
    created_map = {}
    updated_map = {}
    for ad in ads_meta_raw:
        thumb_map[ad["id"]]   = ad.get("creative", {}).get("thumbnail_url", "")
        status_map[ad["id"]]  = ad.get("effective_status", "PAUSED")
        created_map[ad["id"]] = ad.get("created_time", "")[:10]  # YYYY-MM-DD
        updated_map[ad["id"]] = ad.get("updated_time", "")[:10]

    # 5. Indexa insights diários por ad_id → date
    new_daily = {}   # {ad_id: {date_str: metrics}}
    ad_info   = {}   # {ad_id: {campaign_id, adset, ad_name}}

    for row in insights_raw:
        ad_id    = row.get("ad_id")
        date_str = row.get("date_start")
        if not ad_id or not date_str:
            continue
        sp = float(row.get("spend", 0))
        if sp < 0.01:
            continue
        m = parse_actions(row)
        m.update({
            "spend":       round(sp, 2),
            "impressions": int(row.get("impressions", 0)),
            "ctr":         round(float(row.get("ctr", 0)), 2),
            "cpm":         round(float(row.get("cpm", 0)), 2),
            "frequency":   round(float(row.get("frequency", 0)), 2),
        })
        new_daily.setdefault(ad_id, {})[date_str] = m
        if ad_id not in ad_info:
            ad_info[ad_id] = {
                "campaign_id": row.get("campaign_id"),
                "adset":       row.get("adset_name", ""),
                "ad_name":     row.get("ad_name", ""),
            }

    # 6. Age breakdown index
    age_index = {}
    for row in age_raw:
        ad_id = row.get("ad_id")
        if not ad_id:
            continue
        sp = float(row.get("spend", 0))
        if sp < 0.01:
            continue
        m = parse_actions(row)
        m.update({
            "age":         row.get("age", ""),
            "spend":       round(sp, 2),
            "impressions": int(row.get("impressions", 0)),
        })
        age_index.setdefault(ad_id, []).append(m)

    # 7. Merge com histórico e monta estrutura por campanha
    camp_ads = {}

    all_ad_ids = set(new_daily.keys())

    for ad_id in all_ad_ids:
        existing = ad_lookup.get(ad_id, {})

        # Merge diário: mantém histórico, atualiza dias recentes
        merged_daily = dict(existing.get("daily", {}))  # cópia
        for date_str, day_m in new_daily.get(ad_id, {}).items():
            if date_str in ALWAYS_REFRESH or date_str not in merged_daily:
                merged_daily[date_str] = day_m

        if not merged_daily:
            continue

        # Dados estáticos: prefere existentes
        thumbnail   = existing.get("thumbnail") or thumb_map.get(ad_id, "")
        preview_url = existing.get("preview_url", "")
        age_bd      = age_index.get(ad_id) or existing.get("age_breakdown", [])
        created_at  = created_map.get(ad_id) or existing.get("created_at", "")
        updated_at  = updated_map.get(ad_id) or existing.get("updated_at", "")

        info    = ad_info.get(ad_id, {})
        camp_id = info.get("campaign_id")
        if not camp_id:
            continue

        # Agrega métricas de todos os dias
        agg = aggregate_daily(merged_daily)

        is_active  = status_map.get(ad_id, "PAUSED") == "ACTIVE"
        first_date = min(merged_daily.keys()) if merged_daily else ""
        camp_ads.setdefault(camp_id, []).append({
            "id":            ad_id,
            "name":          info.get("ad_name") or existing.get("name", ad_id),
            "active":        is_active,
            "adset":         info.get("adset") or existing.get("adset", ""),
            "thumbnail":     thumbnail,
            "preview_url":   preview_url,
            "created_at":    created_at,
            "updated_at":    updated_at,
            "first_active":  first_date,
            "metrics":       agg,
            "age_breakdown": sorted(age_bd, key=lambda x: x.get("age", "")),
            "daily":         dict(sorted(merged_daily.items())),
        })

    # 8. Monta campanhas
    campaigns = []
    for camp in camps_raw:
        camp_id = camp["id"]
        ads = sorted(camp_ads.get(camp_id, []), key=lambda x: x["metrics"]["spend"], reverse=True)
        if not ads:
            continue

        total = {"spend": 0, "impressions": 0, "msgs": 0, "lpv": 0, "purchases": 0}
        for ad in ads:
            for k in total:
                total[k] += ad["metrics"].get(k, 0)
        total["spend"]    = round(total["spend"], 2)
        total["cost_msg"] = round(total["spend"] / total["msgs"], 2) if total["msgs"] > 0 else 0

        campaigns.append({
            "id":        camp["id"],
            "name":      camp["name"],
            "objective": camp.get("objective", ""),
            "metrics":   total,
            "ads":       ads,
        })

    campaigns.sort(key=lambda x: x["metrics"]["spend"], reverse=True)

    return {
        "id":        acct_id,
        "name":      acc["name"],
        "currency":  acc["currency"],
        "campaigns": campaigns,
    }


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    print(f"=== Gerando dashboard_data.json (incremental, diário) ===")
    print(f"Período de busca: {SINCE} → {UNTIL}")
    print(f"Histórico mantido: últimos {KEEP_DAYS} dias (desde {CUTOFF})")
    print(f"Contas: {len(ACCOUNTS)}\n")

    # Carrega dados existentes para merge incremental
    ad_lookup = load_existing_ads()

    # Dias disponíveis: existentes (dentro do corte) + novos
    all_days = set()
    for ex in ad_lookup.values():
        all_days.update(d for d in ex.get("daily", {}).keys() if d >= CUTOFF)
    d_iter = date.today() - timedelta(days=FETCH_DAYS - 1)
    while d_iter <= date.today():
        all_days.add(d_iter.strftime("%Y-%m-%d"))
        d_iter += timedelta(days=1)

    result = {
        "updated_at":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "since":          CUTOFF,
        "until":          UNTIL,
        "days_available": sorted(all_days),
        "accounts":       [],
    }

    for acc in ACCOUNTS:
        try:
            data = fetch_account(acc, ad_lookup)
            result["accounts"].append(data)
            # Adiciona dias encontrados nesta conta
            for camp in data.get("campaigns", []):
                for ad in camp.get("ads", []):
                    all_days.update(ad.get("daily", {}).keys())
        except Exception as e:
            print(f"  ERRO {acc['name']}: {e}")
            result["accounts"].append({
                "id": acc["id"], "name": acc["name"],
                "currency": acc["currency"], "campaigns": [], "error": str(e),
            })
        time.sleep(0.5)

    result["days_available"] = sorted(all_days)

    # ── Agrupamento por gestor ────────────────────────────────────────────────
    gestores_out = []
    for g in GESTORES:
        g_ids   = {a["id"] for a in g["accounts"]}
        g_accts = [a for a in result["accounts"] if a["id"] in g_ids]
        g_days  = set()
        for acc in g_accts:
            for camp in acc.get("campaigns", []):
                for ad in camp.get("ads", []):
                    g_days.update(ad.get("daily", {}).keys())
        gestores_out.append({
            "id":             g["id"],
            "name":           g["name"],
            "days_available": sorted(g_days),
            "accounts":       g_accts,
        })
    result["gestores"] = gestores_out

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    total_camps = sum(len(a["campaigns"]) for a in result["accounts"])
    total_ads   = sum(sum(len(c["ads"]) for c in a["campaigns"]) for a in result["accounts"])
    days_list   = result["days_available"]
    print(f"\n✅ Salvo: {OUT}")
    print(f"   {len(ACCOUNTS)} contas ({len(BRAGA_ACCOUNTS)} Braga + {len(IGOR_ACCOUNTS)} Igor)")
    print(f"   {total_camps} campanhas | {total_ads} anúncios")
    print(f"   {len(days_list)} dias disponíveis: {days_list[0] if days_list else '—'} → {days_list[-1] if days_list else '—'}")
    print(f"   Atualizado em: {result['updated_at']}")
    for g in gestores_out:
        g_camps = sum(len(a["campaigns"]) for a in g["accounts"])
        g_ads   = sum(sum(len(c["ads"]) for c in a["campaigns"]) for a in g["accounts"])
        print(f"   [{g['name']}] {len(g['accounts'])} contas | {g_camps} campanhas | {g_ads} anúncios")


if __name__ == "__main__":
    main()
