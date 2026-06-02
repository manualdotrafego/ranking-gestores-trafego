#!/usr/bin/env python3
"""
Pipeline #NNN ISOLADO por gestor — uso: python3 pipeline_gestor.py <slug>
slug: braga | igor | milena | victor | bueno | mota
Match primário por #NNN (mescla campanhas com MESMA tag). Sem merge por código.
Salvo no repo para não ser perdido em limpeza do /tmp.
"""
import os, sys, re, time, subprocess
from pathlib import Path
from dotenv import load_dotenv
from collections import Counter

BASE_DIR = Path("/Users/alexrangelalves/Downloads/Conexão mtds")
sys.path.insert(0, str(BASE_DIR))
load_dotenv(dotenv_path=BASE_DIR / ".env")

import requests
from gerar_relatorios_todos_v2 import (
    META_BASE, GH_PAGES_BASE, FIXED_SINCE, FIXED_UNTIL,
    fetch_daily_insights, merge_daily, generate_html, take_screenshots,
    notion_update_preview_image, start_local_server, notion_get_pages,
    parse_notion_page, slugify,
)

META_TOKEN = os.getenv("META_ACCESS_TOKEN")
TAG_RE = re.compile(r'#(\d+)')

GESTOR_CFG = {
    'braga': ('Thiago Braga', ['795680591769062','350266333900752','613666203841045','1534753857104914',
                     '627225619698621','684292170965131','1385771249133770','1492720022172340',
                     '784528807407228','1221130892436075','945748271201968','1191172178527886',
                     '931356816330864','2098001153669315','760466882917549']),
    'igor': ('Igor Teixeira', ['5648874101844136','449000287288780','1181454115989018','1191525622298805',
                     '412153471621510','391009870578696','1583196522529565','1329276834986407',
                     '566170923166415','1132321672289497']),
    'milena': ('Giovanni Azzi', ['929466455169259','1085576095862723','1092388468506879','8918374284933128',
                     '821690284057436','1256638916269263']),
    'victor': ('Victor Coutinho', ['816831793052077','1145079426101184','1229765484942576']),
    'bueno': ('Gustavo Bueno', ['844368963369490','762767474947500','514946917180994','646063993729347',
                     '1473069363640157','1512288279712118','1874417206315032','3656827834577801',
                     '421023317498662','969549934748192','1417247788994678']),
    'mota': ('Gustavo Motta', ['5278613945567179','388602330121239','140805155678128',
                     '959827441932943','782257763801898']),
}

slug = sys.argv[1].lower() if len(sys.argv) > 1 else None
if slug not in GESTOR_CFG:
    print(f'Uso: python3 pipeline_gestor.py <{"|".join(GESTOR_CFG)}>'); sys.exit(1)

GESTOR_NOTION, ACCOUNTS = GESTOR_CFG[slug]
print(f'═══ {GESTOR_NOTION} ═══  período {FIXED_SINCE} → {FIXED_UNTIL}\n')

# 1. Cards
pages = notion_get_pages(GESTOR_NOTION)
cards, sem_tag = [], 0
for p in pages:
    nm = parse_notion_page(p)['clinic_name']
    m = TAG_RE.search(nm)
    if m:
        cards.append({'page_id': p['id'], 'name': nm, 'tag':'#'+m.group(1), 'num': m.group(1)})
    else:
        sem_tag += 1
print(f'Cards ON: {len(pages)} | com #NNN: {len(cards)} | sem tag: {sem_tag}')
if not cards:
    sys.exit(0)

# 2. Varre Meta — index por #NNN
camp_by_tag = {}
for acc in ACCOUNTS:
    url = f'{META_BASE}/act_{acc}/campaigns'
    params = {'access_token': META_TOKEN, 'fields':'id,name,effective_status', 'limit':200}
    while url:
        r = requests.get(url, params=params, timeout=30)
        d = r.json()
        if 'error' in d: break
        for c in d.get('data', []):
            m = TAG_RE.search(c.get('name',''))
            if m:
                camp_by_tag.setdefault('#'+m.group(1), []).append({
                    'account': acc, 'id': c['id'], 'name': c['name'], 'status': c.get('effective_status')})
        nxt = d.get('paging',{}).get('next')
        if not nxt: break
        url = nxt; params = {}
    time.sleep(0.1)
print(f'Meta: {len(camp_by_tag)} tags únicas\n')

# 3. Match isolado por tag
tc = Counter(c['tag'] for c in cards)
dups = {t for t,n in tc.items() if n>1}
jobs, sem_match = [], []
for c in cards:
    if c['tag'] in dups:
        print(f'  ⏭️  {c["tag"]} PULADO (mesma tag em >1 card)'); continue
    matches = camp_by_tag.get(c['tag'], [])
    if not matches:
        sem_match.append(c); continue
    primary = next((m['account'] for m in matches if m['status']=='ACTIVE'), matches[0]['account'])
    if len(matches) > 1:
        print(f'  🔀 {c["tag"]} mescla {len(matches)} camps (mesma tag)')
    jobs.append({'slug': f'{slug}_{slugify(c["name"])[:50]}_{c["num"]}',
                 'clinic': c['name'], 'page_id': c['page_id'], 'account': primary,
                 'campaigns': [{'id':m['id'],'name':m['name'],'effective_status':m['status']} for m in matches]})
print(f'\n  → {len(jobs)} jobs | {len(sem_match)} sem match')

# 4. HTMLs
items = []
for job in jobs:
    rows = [fetch_daily_insights(c['id'], FIXED_SINCE, FIXED_UNTIL) for c in job['campaigns']]
    daily = merge_daily(rows) if len(rows) > 1 else (rows[0] if rows else [])
    hp = BASE_DIR / f'relatorio_{job["slug"]}.html'
    pp = BASE_DIR / f'relatorio_{job["slug"]}.png'
    hp.write_text(generate_html(job['clinic'], job['campaigns'], job['account'], daily, FIXED_SINCE, FIXED_UNTIL), encoding='utf-8')
    items.append({'slug':job['slug'],'html_filename':hp.name,'png_filename':pp.name,
                  'html_path':hp,'png_path':pp,'page_id':job['page_id'],'clinic':job['clinic']})

# 5. Screenshots
port = start_local_server(str(BASE_DIR), 0)
take_screenshots([{'slug':i['slug'],'html_filename':i['html_filename'],'png_path':i['png_path']} for i in items], port)

# 6. Push
files = [str(i['html_path']) for i in items] + [str(i['png_path']) for i in items]
subprocess.run(['git','-C',str(BASE_DIR),'add']+files, check=True)
res = subprocess.run(['git','-C',str(BASE_DIR),'commit','-m',
    f'{GESTOR_NOTION} #NNN — {FIXED_SINCE}→{FIXED_UNTIL} ({len(items)} cards)'],
    capture_output=True, text=True)
if res.returncode == 0:
    subprocess.run(['git','-C',str(BASE_DIR),'push'], check=True)
    print('  ⏳ 15s GH Pages...'); time.sleep(15)
else:
    print('  ℹ️  Sem mudanças')

# 7. Notion
ok = 0
for i in items:
    try:
        if notion_update_preview_image(i['page_id'], f'{GH_PAGES_BASE}/{i["png_filename"]}'):
            ok += 1
    except Exception as e:
        print(f'  ❌ {i["clinic"][:40]}: {e}')
    time.sleep(0.15)

print(f'\n🎉 {GESTOR_NOTION}: {ok}/{len(items)} cards atualizados')
if sem_match:
    print(f'⚠️  {len(sem_match)} sem match no Meta:')
    for c in sem_match:
        print(f'   ❌ {c["tag"]:>6}  {c["name"][:55]}')
