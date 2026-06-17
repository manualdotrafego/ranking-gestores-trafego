#!/usr/bin/env python3
"""
detectar_variacao_cpl.py
Detecta altas de CPL por unidade comparando o último dia completo com a média
(ponderada) dos 3 dias anteriores. Gera alertas.json (consumido pelo dashboard)
e imprime o resumo. O envio por Telegram é feito por notificar_telegram.py.

Unidade = #NNN (soma de todas as campanhas/anúncios da tag no gestor).
Critério: só ALTAS, variação >= 30% E >= R$1,00 (com guarda de volume).
"""
import json, re, sys
from datetime import date
from pathlib import Path
from collections import defaultdict

BASE = Path("/Users/alexrangelalves/Downloads/Conexão mtds")
DATA = BASE / "dashboard_data.json"
OUT  = BASE / "alertas.json"

# ─── critérios (ajustáveis) ───
MIN_PCT      = 30.0   # variação mínima (%)
MIN_ABS      = 1.0    # variação mínima (R$)
MIN_MSG_REF  = 3      # mensagens mínimas no dia de referência
MIN_MSG_BASE = 6      # mensagens mínimas somadas no baseline (3 dias)
DIRECAO      = "alta" # "alta" = só CPL subindo

TAG_RE = re.compile(r'#(\d+)')

def clean_clinic(name):
    # remove prefixo "#NNN |", códigos "C1 -", números soltos e datas
    n = TAG_RE.sub('', name)
    n = re.sub(r'^\s*[|\-–]\s*', '', n)
    n = re.sub(r'\bC\d+\s*[-–]\s*', '', n)
    n = re.sub(r'\b\d{2,4}\$?\s*[-–]?\s*', '', n)
    n = re.sub(r'\d{1,2}[/.]\d{1,2}([/.]\d{2,4})?', '', n)
    n = n.replace('()', '')
    n = re.sub(r'[/\\]+', ' ', n)
    n = re.sub(r'[-–|]{1,}', ' ', n)
    n = re.sub(r'\s{2,}', ' ', n).strip(' -–|')
    return n or name

def run(run_today=None):
    d = json.load(open(DATA, encoding='utf-8'))
    today = run_today or date.today().isoformat()
    days = sorted(set(d.get('days_available', [])))
    past = [x for x in days if x < today]   # ignora hoje (parcial)
    if len(past) < 4:
        print(f'Dados insuficientes: {len(past)} dias completos disponíveis'); return None
    ref_day = past[-1]
    base_days = past[-4:-1]   # 3 dias anteriores ao ref

    # agrega spend/msgs por (gestor, tag) e por dia
    units = {}  # (gestor, tag) -> {clinic, ref:{sp,msg}, base:{sp,msg}}
    for g in d['gestores']:
        gname = g['name']
        for acc in g['accounts']:
            for camp in acc['campaigns']:
                m = TAG_RE.search(camp.get('name', ''))
                tag = '#' + m.group(1) if m else None
                key = (gname, tag or camp.get('name', '')[:40])
                u = units.setdefault(key, {'tag': tag, 'clinic': clean_clinic(camp.get('name','')),
                                           'ref_sp':0.0,'ref_msg':0.0,'base_sp':0.0,'base_msg':0.0})
                for ad in camp.get('ads', []):
                    daily = ad.get('daily', {})
                    r = daily.get(ref_day)
                    if r:
                        u['ref_sp']  += float(r.get('spend',0)); u['ref_msg'] += float(r.get('msgs',0))
                    for bd in base_days:
                        b = daily.get(bd)
                        if b:
                            u['base_sp'] += float(b.get('spend',0)); u['base_msg'] += float(b.get('msgs',0))

    alerts = []
    for (gname, _), u in units.items():
        if u['ref_msg'] < MIN_MSG_REF or u['base_msg'] < MIN_MSG_BASE:
            continue
        cpl_ref  = u['ref_sp']  / u['ref_msg']
        cpl_base = u['base_sp'] / u['base_msg']
        if cpl_base <= 0:
            continue
        var_abs = cpl_ref - cpl_base
        var_pct = var_abs / cpl_base * 100
        if DIRECAO == 'alta' and var_abs <= 0:
            continue
        if abs(var_abs) >= MIN_ABS and abs(var_pct) >= MIN_PCT:
            alerts.append({
                'gestor': gname, 'clinica': u['clinic'], 'tag': u['tag'],
                'cpl_ant': round(cpl_base,2), 'cpl_atual': round(cpl_ref,2),
                'var_abs': round(var_abs,2), 'var_pct': round(var_pct,1),
                'msgs_atual': int(u['ref_msg']), 'spend_atual': round(u['ref_sp'],2),
            })
    alerts.sort(key=lambda a: a['var_abs'], reverse=True)

    out = {
        'generated_at': today, 'ref_day': ref_day, 'baseline_days': base_days,
        'criteria': {'min_pct': MIN_PCT, 'min_abs': MIN_ABS, 'direction': DIRECAO,
                     'min_msg_ref': MIN_MSG_REF, 'min_msg_base': MIN_MSG_BASE},
        'count': len(alerts), 'alerts': alerts,
    }
    json.dump(out, open(OUT,'w',encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f'Dia ref: {ref_day}  | baseline: {base_days}')
    print(f'{len(alerts)} altas de CPL detectadas (>= {MIN_PCT:.0f}% e >= R${MIN_ABS:.2f}):\n')
    for a in alerts[:30]:
        print(f"  [{a['gestor'][:8]:<8}] {a['clinica'][:34]:<34} {a['tag'] or '':>6}  "
              f"R${a['cpl_ant']:>5.2f} -> R${a['cpl_atual']:>5.2f}  +R${a['var_abs']:>5.2f} (+{a['var_pct']:.0f}%)  [{a['msgs_atual']} msgs]")
    print(f'\nalertas.json salvo: {OUT}')
    return out

if __name__ == '__main__':
    run(sys.argv[1] if len(sys.argv) > 1 else None)
