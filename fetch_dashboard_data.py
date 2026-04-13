#!/usr/bin/env /Library/Frameworks/Python.framework/Versions/3.14/bin/python3
"""
Busca dados de todas as contas do System User e salva em dashboard_data.json
Otimizado: busca insights por conta de uma vez com level=ad
"""

import os, json, requests, time
from datetime import datetime, date, timedelta
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

TOKEN = os.getenv("META_ACCESS_TOKEN")
BASE  = "https://graph.facebook.com/v21.0"
OUT   = os.path.join(os.path.dirname(__file__), "dashboard_data.json")

ACCOUNTS = [
    {"id": "753068846198086",  "name": "CT01",                         "currency": "BRL"},
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
    {"id": "310500857276337",  "name": "CONTA 001",                    "currency": "BRL"},
]

SINCE = (date.today() - timedelta(days=30)).strftime("%Y-%m-%d")
UNTIL = date.today().strftime("%Y-%m-%d")
TIME_RANGE = json.dumps({"since": SINCE, "until": UNTIL})


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
    """Busca todas as páginas de resultados."""
    results = []
    resp = get(path, params)
    results.extend(resp.get("data", []))
    while resp.get("paging", {}).get("next"):
        next_url = resp["paging"]["next"]
        try:
            r = requests.get(next_url, timeout=30)
            resp = r.json()
            results.extend(resp.get("data", []))
        except:
            break
    return results


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


def fetch_account(acc):
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
    camp_map = {c["id"]: c for c in camps_raw}

    # 2. Insights nível AD — uma chamada por conta (filtrando por campanhas ativas)
    print(f"    Buscando insights (ad level)...")
    insights_raw = get_all_pages(f"/act_{acct_id}/insights", {
        "fields": "campaign_id,campaign_name,adset_id,adset_name,ad_id,ad_name,"
                  "spend,impressions,clicks,ctr,cpm,frequency,"
                  "actions,cost_per_action_type",
        "level": "ad",
        "time_range": TIME_RANGE,
        "filtering": json.dumps([{"field": "campaign.id", "operator": "IN", "value": camp_ids}]),
        "limit": 500,
    })
    print(f"    {len(insights_raw)} linhas de insights")

    # 3. Insights por idade — uma chamada por conta (level=ad, breakdown=age)
    print(f"    Buscando breakdown por idade...")
    age_raw = get_all_pages(f"/act_{acct_id}/insights", {
        "fields": "ad_id,age,spend,impressions,actions,cost_per_action_type",
        "level": "ad",
        "time_range": TIME_RANGE,
        "breakdowns": "age",
        "filtering": json.dumps([{"field": "campaign.id", "operator": "IN", "value": camp_ids}]),
        "limit": 500,
    })
    print(f"    {len(age_raw)} linhas de breakdown")

    # 4. Thumbnails dos anúncios
    print(f"    Buscando thumbnails...")
    ads_meta_raw = get_all_pages(f"/act_{acct_id}/ads", {
        "fields": "id,name,effective_status,creative{thumbnail_url}",
        "filtering": json.dumps([{"field": "campaign.id", "operator": "IN", "value": camp_ids}]),
        "limit": 200,
    })
    thumb_map = {}
    status_map = {}
    for ad in ads_meta_raw:
        thumb_map[ad["id"]] = ad.get("creative", {}).get("thumbnail_url", "")
        status_map[ad["id"]] = ad.get("effective_status", "PAUSED")

    # 5. Organiza dados por campanha → anúncio
    # Índice por ad_id para insights
    ad_insights = {}
    for row in insights_raw:
        ad_id = row.get("ad_id")
        if not ad_id:
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
            "campaign_id": row.get("campaign_id"),
            "adset":       row.get("adset_name", ""),
            "ad_name":     row.get("ad_name", ""),
        })
        ad_insights[ad_id] = m

    # Índice por ad_id para breakdown etário
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

    # Monta estrutura por campanha
    camp_ads = {}
    for ad_id, m in ad_insights.items():
        camp_id = m.get("campaign_id")
        if camp_id:
            camp_ads.setdefault(camp_id, []).append({
                "id":            ad_id,
                "name":          m["ad_name"],
                "active":        status_map.get(ad_id, "PAUSED") == "ACTIVE",
                "adset":         m["adset"],
                "thumbnail":     thumb_map.get(ad_id, ""),
                "metrics":       {k: v for k, v in m.items() if k not in ("campaign_id","adset","ad_name")},
                "age_breakdown": sorted(age_index.get(ad_id, []), key=lambda x: x["age"]),
            })

    # Monta campanhas
    campaigns = []
    for camp in camps_raw:
        camp_id = camp["id"]
        ads = sorted(camp_ads.get(camp_id, []), key=lambda x: x["metrics"]["spend"], reverse=True)
        if not ads:
            continue

        # Soma métricas da campanha
        total = {"spend": 0, "impressions": 0, "msgs": 0, "lpv": 0, "purchases": 0}
        for ad in ads:
            for k in total:
                total[k] += ad["metrics"].get(k, 0)
        total["spend"] = round(total["spend"], 2)
        total["cost_msg"] = round(total["spend"] / total["msgs"], 2) if total["msgs"] > 0 else 0

        campaigns.append({
            "id":        camp_id,
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


def main():
    print(f"=== Gerando dashboard_data.json ===")
    print(f"Período: {SINCE} → {UNTIL}")
    print(f"Contas: {len(ACCOUNTS)}\n")

    result = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "since":      SINCE,
        "until":      UNTIL,
        "accounts":   [],
    }

    for acc in ACCOUNTS:
        try:
            data = fetch_account(acc)
            result["accounts"].append(data)
        except Exception as e:
            print(f"  ERRO {acc['name']}: {e}")
            result["accounts"].append({
                "id": acc["id"], "name": acc["name"],
                "currency": acc["currency"], "campaigns": [], "error": str(e),
            })
        time.sleep(0.5)

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    total_camps = sum(len(a["campaigns"]) for a in result["accounts"])
    total_ads   = sum(sum(len(c["ads"]) for c in a["campaigns"]) for a in result["accounts"])
    print(f"\n✅ Salvo: {OUT}")
    print(f"   {len(ACCOUNTS)} contas | {total_camps} campanhas | {total_ads} anúncios")
    print(f"   Atualizado em: {result['updated_at']}")


if __name__ == "__main__":
    main()
