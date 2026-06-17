#!/usr/bin/env python3
"""
notificar_discord.py
Lê alertas.json e envia as altas de CPL para um canal do Discord via Webhook.
Configurar no .env:  DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/.../...
Modo preview:  python3 notificar_discord.py preview   -> imprime o payload, NÃO envia.
Não envia quando não há altas (evita spam).
"""
import os, sys, json
from pathlib import Path
from dotenv import load_dotenv
import requests

BASE = Path("/Users/alexrangelalves/Downloads/Conexão mtds")
load_dotenv(dotenv_path=BASE / ".env")
WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
ALERTAS = BASE / "alertas.json"
RED = 0xED4245

# gestor (palavra-chave no nome) -> ID de usuário do Discord (para @menção)
GESTOR_IDS = {
    'braga':  '1431434979665252402',
    'igor':   '1376926480449409135',
    'milena': '1422292108047552744',
    'victor': '1459245514016165993',
    'bueno':  '1222265199499804795',
    'mot':    '1459235061336506513',  # Mota / motinha
}

def gestor_id(name):
    n = name.lower()
    for kw, uid in GESTOR_IDS.items():
        if kw in n:
            return uid
    return None

def fmt_day(iso):
    p = iso.split('-'); return f'{p[2]}/{p[1]}' if len(p) == 3 else iso

def brl(v):
    return 'R$ ' + f'{float(v):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')

def build_payload(d, ping=True):
    base = d.get('baseline_days', [])
    base_txt = f'{fmt_day(base[0])}–{fmt_day(base[-1])}' if base else ''
    crit = d.get('criteria', {})
    fields = []
    for a in d['alerts']:
        tag = f' · {a["tag"]}' if a.get('tag') else ''
        uid = gestor_id(a['gestor'])
        gestor_txt = f'<@{uid}>' if uid else f'**{a["gestor"]}**'
        fields.append({
            'name': f'🔺 {a["clinica"]}{tag}',
            'value': (f'{gestor_txt}\n'
                      f'{brl(a["cpl_ant"])} → **{brl(a["cpl_atual"])}**  '
                      f'`+{brl(a["var_abs"])} (+{a["var_pct"]:.0f}%)` · {a["msgs_atual"]} msgs'),
            'inline': False,
        })
    embed = {
        'title': f'🔴 {d["count"]} alta(s) de CPL detectada(s)',
        'description': f'Dia **{fmt_day(d["ref_day"])}** vs média de {base_txt}\n'
                       f'_Critério: ≥{crit.get("min_pct",30):.0f}% e ≥{brl(crit.get("min_abs",1))} · só altas_',
        'color': RED,
        'fields': fields,
        'footer': {'text': 'Manual do Tráfego · monitor de CPL'},
    }
    # menção (ping) dos responsáveis no texto da mensagem — só pinga via content
    uids = list(dict.fromkeys(filter(None, (gestor_id(a['gestor']) for a in d['alerts']))))
    content = '🔔 Responsáveis: ' + ' '.join(f'<@{u}>' for u in uids) if uids else ''
    payload = {'username': 'Alertas CPL', 'content': content, 'embeds': [embed]}
    payload['allowed_mentions'] = {'users': uids} if ping else {'parse': []}
    return payload

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ''
    preview = mode == 'preview'        # só imprime, não envia
    silent  = mode == 'silent'         # envia mas SEM pingar (teste de aparência)
    if not ALERTAS.exists():
        print('alertas.json não encontrado — rode detectar_variacao_cpl.py antes'); return
    d = json.load(open(ALERTAS, encoding='utf-8'))
    if not d.get('count'):
        print('Sem altas — nada a enviar.'); return
    payload = build_payload(d, ping=not silent)
    if preview:
        print(json.dumps(payload, ensure_ascii=False, indent=2)); return
    if not WEBHOOK:
        print('⚠️  DISCORD_WEBHOOK_URL não configurado no .env — skip.'); return
    r = requests.post(WEBHOOK, json=payload, timeout=30)
    if r.status_code in (200, 204):
        print(f'✅ Discord enviado ({d["count"]} altas){" [sem ping]" if silent else " [com ping]"}')
    else:
        print(f'❌ Discord erro {r.status_code}: {r.text[:200]}')

if __name__ == '__main__':
    main()
