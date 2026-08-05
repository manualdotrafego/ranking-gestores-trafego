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

BASE_DIR = Path(os.environ.get("PROJECT_DIR", "/Users/alexrangelalves/Downloads/Conexão mtds"))
sys.path.insert(0, str(BASE_DIR))
load_dotenv(dotenv_path=BASE_DIR / ".env")

import requests
from gerar_relatorios_todos_v2 import (
    META_BASE, GH_PAGES_BASE, FIXED_SINCE, FIXED_UNTIL,
    fetch_daily_insights, merge_daily, generate_html, take_screenshots,
    notion_update_preview_image, notion_update_relatorio_novo,
    start_local_server, notion_get_pages, parse_notion_page, slugify,
    load_existing_daily, accumulate_daily,
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
                     '421023317498662','969549934748192','1417247788994678',
                     '3143685079159710']),  # +01 Cayman (Planaltina/GO #150)
    'mota': ('Gustavo Motta', ['5278613945567179','388602330121239','140805155678128',
                     '959827441932943','782257763801898','1221130892436075','3894814770656049',
                     '716772110646661']),  # +CT07 Dbout Mota (Formosa #652)
}

# Campanhas extra a mesclar num card específico (ex.: clínica que trocou de
# gestor — junta a campanha pausada do gestor antigo com a ativa do novo).
EXTRA_CAMPAIGNS = {
    ('braga', '#287'): [{
        'id': '120243326195610145',
        'name': '#127 | São José dos Campos - R$ 4000(3.520) - [01 sjc] (Bueno - pausada)',
        'account': '1874417206315032', 'status': 'PAUSED'}],
    ('braga', '#288'): [{
        'id': '120244069345300145',
        'name': '#145 | São José dos Campos(Cônego) - MARCA R$ 600(528) (Bueno - movida)',
        'account': '1874417206315032', 'status': 'PAUSED'}],
    # Campanhas de FORMULÁRIO nativo sem o #código no nome — mescladas ao card certo.
    ('igor', '#429'): [{
        'id': '120251128984110421',
        'name': '429 | 3078 - CURITIBA XV NOV FORMULÁRIO - 07.07',
        'account': '391009870578696', 'status': 'ACTIVE'}],
    ('igor', '#465'): [{
        'id': '120248607838040239',
        'name': 'FORMS DIADEMA - 03.07',
        'account': '412153471621510', 'status': 'ACTIVE'}],
    ('igor', '#425'): [{
        'id': '120251623192790606',
        'name': 'FORMULÁRIO QUEIMADAS E ESPERANÇA - 01.07',
        'account': '566170923166415', 'status': 'ACTIVE'}],
    # (#124 Jaú não precisa mais de regra: a campanha de formulário foi renomeada
    #  com "#124" e casa pelo scan. Regra removida para não ficar redundante.)
    # Águas Lindas: unidade transferida Braga → Igor. Card #201 movido no Notion;
    # a campanha roda na CT01-DRACO (Igor) e não tem o #201 no nome.
    ('igor', '#201'): [{
        'id': '120250558802770663',
        'name': 'AGUAS LINDAS FORMULÁRIO - 30.06',
        'account': '1583196522529565', 'status': 'ACTIVE'}],
    # (#150 Planaltina/GO não precisa de regra: a campanha foi renomeada com o
    #  #150 e a conta 01 Cayman está na lista do Bueno — casa pelo scan normal.)
    # Mogi das Cruzes: a CP principal já foi renomeada com "#346" e casa pelo scan.
    # Só a de FORMS segue nomeada "346 | ..." (sem #) e precisa da regra.
    ('milena', '#346'): [
        {'id': '120249156678210052',
         'name': '346 | CP FORMS - MOGI DAS CRUZES - 1054K - 06/07',
         'account': '929466455169259', 'status': 'PAUSED'},
    ],
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
    matches = list(camp_by_tag.get(c['tag'], []))
    extra = EXTRA_CAMPAIGNS.get((slug, c['tag']), [])
    if extra:
        matches += extra
        print(f'  ➕ {c["tag"]} +{len(extra)} camp(s) extra (merge entre gestores)')
    # Dedup por ID: uma campanha com regra EXTRA que depois foi renomeada com a
    # #tag apareceria aqui duas vezes (pelo scan e pela regra), dobrando gasto/leads.
    seen_ids, uniq = set(), []
    for m in matches:
        if m['id'] in seen_ids:
            print(f'  ⚠️  {c["tag"]} campanha {m["id"]} duplicada (scan + EXTRA) — contada 1x')
            continue
        seen_ids.add(m['id']); uniq.append(m)
    matches = uniq
    if not matches:
        sem_match.append(c); continue
    primary = next((m['account'] for m in matches if m['status']=='ACTIVE'), matches[0]['account'])
    if len(matches) > 1:
        print(f'  🔀 {c["tag"]} mescla {len(matches)} camps')
    jobs.append({'slug': f'{slug}_{slugify(c["name"])[:50]}_{c["num"]}',
                 'clinic': c['name'], 'page_id': c['page_id'], 'account': primary,
                 'campaigns': [{'id':m['id'],'name':m['name'],'effective_status':m['status']} for m in matches]})
print(f'\n  → {len(jobs)} jobs | {len(sem_match)} sem match')

# 4. HTMLs
items = []
for job in jobs:
    rows = [fetch_daily_insights(c['id'], FIXED_SINCE, FIXED_UNTIL) for c in job['campaigns']]
    fresh = merge_daily(rows) if len(rows) > 1 else (rows[0] if rows else [])
    hp = BASE_DIR / f'relatorio_{job["slug"]}.html'
    pp = BASE_DIR / f'relatorio_{job["slug"]}.png'
    # Histórico acumulado: mantém todos os dias já publicados e acrescenta/atualiza
    # os da janela buscada. Nenhum dia antigo é perdido a cada rodada.
    daily = accumulate_daily(load_existing_daily(hp), fresh)
    hp.write_text(generate_html(job['clinic'], job['campaigns'], job['account'], daily, FIXED_SINCE, FIXED_UNTIL), encoding='utf-8')
    items.append({'slug':job['slug'],'html_filename':hp.name,'png_filename':pp.name,
                  'html_path':hp,'png_path':pp,'page_id':job['page_id'],'clinic':job['clinic']})

# 5. Screenshots
port = start_local_server(str(BASE_DIR), 0)
take_screenshots([{'slug':i['slug'],'html_filename':i['html_filename'],'png_path':i['png_path']} for i in items], port)

# 5b. Remove relatórios órfãos: mesmo #NNN de um card atual, mas com nome de
# arquivo antigo (o card foi renomeado → o slug mudou e sobrou o arquivo velho).
# Só remove quando existe o arquivo canônico atual p/ aquele #NNN (nunca remove
# relatório de card que apenas saiu de ON).
current_files = {i['html_filename'] for i in items} | {i['png_filename'] for i in items}
lead_re = re.compile(rf'^relatorio_{slug}_(\d+)_')
current_nums = {m.group(1) for i in items if (m := lead_re.match(i['html_filename']))}
orphans = []
for f in BASE_DIR.glob(f'relatorio_{slug}_*.html'):
    if f.name in current_files:
        continue
    m = lead_re.match(f.name)
    if m and m.group(1) in current_nums:
        orphans.append(f.name)
        png = f.with_suffix('.png').name
        if (BASE_DIR / png).exists():
            orphans.append(png)
if orphans:
    subprocess.run(['git','-C',str(BASE_DIR),'rm','-q','--ignore-unmatch']
                   + [str(BASE_DIR / o) for o in orphans])
    print(f'  🧹 {len(orphans)} órfão(s) removido(s): ' + ', '.join(orphans[:6])
          + ('…' if len(orphans) > 6 else ''))

# 6. Push
# dashboard_data.json/alertas.json são reescritos pelo cron do fetch e pela CI;
# descartamos alterações locais deles para não travar o commit nem conflitar no rebase.
def git(*args, **kw):
    return subprocess.run(['git', '-C', str(BASE_DIR), *args],
                          capture_output=True, text=True, **kw)

for f in ('dashboard_data.json', 'alertas.json'):
    git('checkout', '--', f)

files = [str(i['html_path']) for i in items] + [str(i['png_path']) for i in items]
git('add', *files)
res = git('commit', '-m',
          f'{GESTOR_NOTION} #NNN — {FIXED_SINCE}→{FIXED_UNTIL} ({len(items)} cards)')
if res.returncode == 0:
    # origin pode ter avançado (CI de alertas / cron): rebase antes de empurrar.
    for tentativa in range(3):
        git('pull', '--rebase', '--autostash', 'origin', 'main')
        for f in ('dashboard_data.json', 'alertas.json'):
            git('checkout', '--theirs', f); git('add', f)
        if git('push').returncode == 0:
            print('  ⏳ 15s GH Pages...'); time.sleep(15)
            break
        print(f'  ↻ push rejeitado, tentando de novo ({tentativa + 1}/3)')
    else:
        print('  ⚠️  push falhou após 3 tentativas — Notion será atualizado mesmo assim')
else:
    print('  ℹ️  Sem mudanças')

# 7. Notion — atualiza preview (imagem) E link "Relatório Novo" (HTML)
ok = 0
for i in items:
    try:
        notion_update_relatorio_novo(i['page_id'], f'{GH_PAGES_BASE}/{i["html_filename"]}')
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
