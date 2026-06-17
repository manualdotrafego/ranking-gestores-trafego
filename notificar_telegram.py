#!/usr/bin/env python3
"""
notificar_telegram.py
Lê alertas.json e envia as altas de CPL por Telegram.
Configurar no .env:  TELEGRAM_BOT_TOKEN=...   TELEGRAM_CHAT_ID=...
Se não houver token/chat configurado, sai sem erro (skip gracioso).
Não envia mensagem quando não há altas (evita spam).
"""
import os, json, html
from pathlib import Path
from dotenv import load_dotenv
import requests

BASE = Path("/Users/alexrangelalves/Downloads/Conexão mtds")
load_dotenv(dotenv_path=BASE / ".env")
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT  = os.getenv("TELEGRAM_CHAT_ID", "").strip()
ALERTAS = BASE / "alertas.json"

def fmt_day(iso):
    p = iso.split('-'); return f'{p[2]}/{p[1]}' if len(p) == 3 else iso

def brl(v):
    return 'R$ ' + f'{float(v):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')

def build_message(d):
    base = d.get('baseline_days', [])
    base_txt = f'{fmt_day(base[0])}–{fmt_day(base[-1])}' if base else ''
    crit = d.get('criteria', {})
    lines = [f'🔴 <b>{d["count"]} alta(s) de CPL</b> — dia {fmt_day(d["ref_day"])}',
             f'<i>vs média de {base_txt} · ≥{crit.get("min_pct",30):.0f}% e ≥{brl(crit.get("min_abs",1))}</i>', '']
    for a in d['alerts']:
        tag = f' {a["tag"]}' if a.get('tag') else ''
        lines.append(
            f'• <b>{html.escape(a["clinica"])}</b>{tag} — {html.escape(a["gestor"])}\n'
            f'   {brl(a["cpl_ant"])} → <b>{brl(a["cpl_atual"])}</b>  '
            f'+{brl(a["var_abs"])} (+{a["var_pct"]:.0f}%) · {a["msgs_atual"]} msgs')
    return '\n'.join(lines)

def main():
    if not ALERTAS.exists():
        print('alertas.json não encontrado — rode detectar_variacao_cpl.py antes'); return
    d = json.load(open(ALERTAS, encoding='utf-8'))
    if not d.get('count'):
        print('Sem altas — nada a enviar.'); return
    if not TOKEN or not CHAT:
        print('⚠️  TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID não configurados no .env — skip.')
        print(f'   ({d["count"]} altas estariam no envio)'); return
    msg = build_message(d)
    r = requests.post(f'https://api.telegram.org/bot{TOKEN}/sendMessage',
                      json={'chat_id': CHAT, 'text': msg, 'parse_mode': 'HTML',
                            'disable_web_page_preview': True}, timeout=30)
    if r.status_code == 200:
        print(f'✅ Telegram enviado ({d["count"]} altas) para chat {CHAT}')
    else:
        print(f'❌ Telegram erro {r.status_code}: {r.text[:200]}')

if __name__ == '__main__':
    main()
