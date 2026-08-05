#!/usr/bin/env python3
"""
Atualiza a propriedade URL "Relatório Novo" de cada card com o link do HTML
gerado pelo pipeline. Uso: python3 atualizar_link_relatorio.py <slug_gestor>
"""
import os, sys, re, time, requests
from pathlib import Path
from collections import Counter
from dotenv import load_dotenv

BASE_DIR = Path(os.environ.get("PROJECT_DIR", "/Users/alexrangelalves/Downloads/Conexão mtds"))
sys.path.insert(0, str(BASE_DIR))
load_dotenv(dotenv_path=BASE_DIR / ".env")

from gerar_relatorios_todos_v2 import (
    GH_PAGES_BASE, notion_get_pages, parse_notion_page, slugify, NOTION_BASE,
)
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
HEADERS = {'Authorization': f'Bearer {NOTION_TOKEN}', 'Notion-Version':'2022-06-28', 'Content-Type':'application/json'}
TAG_RE = re.compile(r'#(\d+)')
PROP = 'Relatório Novo'

GESTOR_MAP = {
    'braga':'Thiago Braga','igor':'Igor Teixeira','milena':'Giovanni Azzi',
    'victor':'Victor Coutinho','bueno':'Gustavo Bueno','mota':'Gustavo Motta',
}
slug_g = sys.argv[1].lower() if len(sys.argv) > 1 else None
if slug_g not in GESTOR_MAP:
    print(f'Uso: python3 atualizar_link_relatorio.py <{"|".join(GESTOR_MAP)}>'); sys.exit(1)
GESTOR = GESTOR_MAP[slug_g]
print(f'═══ {GESTOR} — atualizando "{PROP}" ═══\n')

pages = notion_get_pages(GESTOR)
cards = []
for p in pages:
    nm = parse_notion_page(p)['clinic_name']
    m = TAG_RE.search(nm)
    if m:
        cards.append({'page_id': p['id'], 'name': nm, 'num': m.group(1), 'tag':'#'+m.group(1)})

# Pula tags duplicadas (mesma lógica do pipeline)
tc = Counter(c['tag'] for c in cards)
dups = {t for t,n in tc.items() if n>1}

ok = 0; missing = []; skipped = []
for c in cards:
    if c['tag'] in dups:
        skipped.append(c['tag']); continue
    slug = f'{slug_g}_{slugify(c["name"])[:50]}_{c["num"]}'
    html_path = BASE_DIR / f'relatorio_{slug}.html'
    if not html_path.exists():
        missing.append(c); continue
    url = f'{GH_PAGES_BASE}/relatorio_{slug}.html'
    try:
        r = requests.patch(f'{NOTION_BASE}/pages/{c["page_id"]}', headers=HEADERS,
                           json={'properties': {PROP: {'url': url}}}, timeout=30)
        if r.status_code == 200:
            ok += 1
            print(f'  ✅ {c["tag"]:>6}  {c["name"][:48]}')
        else:
            print(f'  ❌ {c["tag"]:>6}  HTTP {r.status_code}: {r.text[:80]}')
    except Exception as e:
        print(f'  ❌ {c["tag"]:>6}  {e}')
    time.sleep(0.15)

print(f'\n🎉 {ok} links atualizados')
if missing:
    print(f'⚠️  {len(missing)} sem HTML gerado (sem campanha no Meta):')
    for c in missing:
        print(f'   ❌ {c["tag"]:>6}  {c["name"][:50]}')
if skipped:
    print(f'⏭️  {len(skipped)} pulados (tag duplicada): {sorted(set(skipped))}')
