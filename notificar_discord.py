#!/usr/bin/env python3
"""
notificar_discord.py
Lê alertas.json e envia as altas de CPL para um canal do Discord via Webhook.
Configurar no .env:  DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/.../...
Modo preview:  python3 notificar_discord.py preview   -> imprime o payload, NÃO envia.
Não envia quando não há altas (evita spam).
"""
import os, sys, json, time
from pathlib import Path
from dotenv import load_dotenv
import requests

BASE = Path(os.environ.get("PROJECT_DIR", "/Users/alexrangelalves/Downloads/Conexão mtds"))
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

CHUNK = 25  # limite do Discord: 25 campos por embed

def build_messages(d, ping=True):
    """Quebra os alertas em várias mensagens (≤25 campos cada) p/ respeitar
    os limites do Discord. Só a 1ª mensagem leva a menção (ping) e o cabeçalho."""
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
    uids = list(dict.fromkeys(filter(None, (gestor_id(a['gestor']) for a in d['alerts']))))
    content = ('🔔 Responsáveis: ' + ' '.join(f'<@{u}>' for u in uids)) if uids else ''
    chunks = [fields[i:i+CHUNK] for i in range(0, len(fields), CHUNK)] or [[]]
    msgs = []
    for idx, ch in enumerate(chunks):
        embed = {'color': RED, 'fields': ch}
        if idx == 0:
            embed['title'] = f'🔴 {d["count"]} alta(s) de CPL detectada(s)'
            embed['description'] = (f'Dia **{fmt_day(d["ref_day"])}** vs média de {base_txt}\n'
                                    f'_Critério: ≥{crit.get("min_pct",30):.0f}% e ≥{brl(crit.get("min_abs",1))} · só altas_')
        if idx == len(chunks) - 1:
            embed['footer'] = {'text': f'Manual do Tráfego · monitor de CPL · parte {idx+1}/{len(chunks)}' if len(chunks) > 1 else 'Manual do Tráfego · monitor de CPL'}
        p = {'username': 'Alertas CPL', 'embeds': [embed]}
        if idx == 0:
            p['content'] = content
            p['allowed_mentions'] = {'users': uids} if ping else {'parse': []}
        else:
            p['allowed_mentions'] = {'parse': []}
        msgs.append(p)
    return msgs

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ''
    preview = mode == 'preview'        # só imprime, não envia
    silent  = mode == 'silent'         # envia mas SEM pingar (teste de aparência)
    if not ALERTAS.exists():
        print('alertas.json não encontrado — rode detectar_variacao_cpl.py antes'); return
    d = json.load(open(ALERTAS, encoding='utf-8'))
    if not d.get('count'):
        print('Sem altas — nada a enviar.'); return
    msgs = build_messages(d, ping=not silent)
    if preview:
        print(json.dumps(msgs, ensure_ascii=False, indent=2)); return
    if not WEBHOOK:
        print('⚠️  DISCORD_WEBHOOK_URL não configurado no .env — skip.'); return
    ok = 0
    for i, p in enumerate(msgs):
        r = requests.post(WEBHOOK, json=p, timeout=30)
        if r.status_code in (200, 204):
            ok += 1
        else:
            print(f'❌ Discord erro {r.status_code} (msg {i+1}/{len(msgs)}): {r.text[:200]}')
        time.sleep(0.5)
    print(f'✅ Discord: {ok}/{len(msgs)} mensagem(ns) enviada(s) ({d["count"]} altas){" [sem ping]" if silent else " [com ping]"}')
    if ok < len(msgs):
        sys.exit(1)

if __name__ == '__main__':
    main()
