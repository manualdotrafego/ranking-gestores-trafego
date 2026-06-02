#!/usr/bin/env python3
"""Gera mapa_cpl_data.json com CPL por estado — ANO TODO (01/01/2026 → hoje), via Meta API."""
import os, json, re, time, unicodedata, requests
from pathlib import Path
from collections import defaultdict
from datetime import date
from dotenv import load_dotenv

BASE = Path('/Users/alexrangelalves/Downloads/Conexão mtds')
load_dotenv(dotenv_path=BASE/'.env')
TOKEN = os.getenv('META_ACCESS_TOKEN'); APIB='https://graph.facebook.com/v21.0'

SINCE='2026-01-01'; UNTIL=date.today().isoformat()

# Todas as contas (50) dos 6 gestores
ACCOUNTS = (
 # Braga (15)
 ['795680591769062','350266333900752','613666203841045','1534753857104914','627225619698621','684292170965131','1385771249133770','1492720022172340','784528807407228','1221130892436075','945748271201968','1191172178527886','931356816330864','2098001153669315','760466882917549']
 # Igor (10)
 +['5648874101844136','449000287288780','1181454115989018','1191525622298805','412153471621510','391009870578696','1583196522529565','1329276834986407','566170923166415','1132321672289497']
 # Milena (6)
 +['929466455169259','1085576095862723','1092388468506879','8918374284933128','821690284057436','1256638916269263']
 # Victor (3)
 +['816831793052077','1145079426101184','1229765484942576']
 # Bueno (11)
 +['844368963369490','762767474947500','514946917180994','646063993729347','1473069363640157','1512288279712118','1874417206315032','3656827834577801','421023317498662','969549934748192','1417247788994678']
 # Mota (5)
 +['5278613945567179','388602330121239','140805155678128','959827441932943','782257763801898']
)

# ── helpers (copiados de build_mapa_cpl.py) ──
TAG=re.compile(r'#(\d+)')
UFS={'AC','AL','AM','AP','BA','CE','DF','ES','GO','MA','MG','MS','MT','PA','PB','PE','PI','PR','RJ','RN','RO','RR','RS','SC','SE','SP','TO'}
UF_TOK=re.compile(r'[/\-\s\(]([A-Z]{2})\b')
def norm(s):
    s=unicodedata.normalize('NFD',s); return ''.join(c for c in s if unicodedata.category(c)!='Mn').upper()
def clean_city(n):
    s=re.sub(r'#\d+\s*[\|\-]?\s*','',n); s=re.sub(r'\[[^\]]*\]','',s); s=re.sub(r'\([^\)]*\)','',s)
    s=re.sub(r'R?\$\s*[\d.,]+','',s); s=re.sub(r'\b\d{1,2}[/.]\d{1,2}(?:[/.]\d{2,4})?\b','',s); s=re.sub(r'\b\d{2,6}\b','',s)
    s=re.sub(r'\b(C\d|CP\d+|CBO|ABO|DBOUT|MARCA|ORTO|PROTESE|PRÓTESE|IMPLANTE|IMPLANTES|LEADS|ENGAJAMENTO|TRAFEGO|TRÁFEGO|TESTE|CONEGO|CÔNEGO|REPUBLICADA|REPUBLICADO|CLINICO|CLÍNICO|S/M|SEM GRÁTIS|SEM GRATIS|COP|LIQUIDO|PAG NOVA|PÁG NOVA)\b','',s,flags=re.I)
    s=re.sub(r'[|/\-–—.,]+',' ',s); s=re.sub(r'\s+',' ',s).strip(); return s

# importa o dicionário grande do build_mapa_cpl.py sem rodá-lo
import ast
src = (BASE/'build_mapa_cpl.py').read_text()
m = re.search(r'CITY_UF = (\{.*?\n\})', src, re.S)
CITY_UF = ast.literal_eval(m.group(1))
CITY_KEYS = sorted(CITY_UF, key=lambda x: -len(x))
UF_NOME={'AC':'Acre','AL':'Alagoas','AM':'Amazonas','AP':'Amapá','BA':'Bahia','CE':'Ceará','DF':'Distrito Federal','ES':'Espírito Santo','GO':'Goiás','MA':'Maranhão','MG':'Minas Gerais','MS':'Mato Grosso do Sul','MT':'Mato Grosso','PA':'Pará','PB':'Paraíba','PE':'Pernambuco','PI':'Piauí','PR':'Paraná','RJ':'Rio de Janeiro','RN':'Rio Grande do Norte','RO':'Rondônia','RR':'Roraima','RS':'Rio Grande do Sul','SC':'Santa Catarina','SE':'Sergipe','SP':'São Paulo','TO':'Tocantins'}
def detect_uf(raw, city_clean):
    for x in UF_TOK.findall(raw):
        if x in UFS: return x
    nr=norm(raw)
    for k in CITY_KEYS:
        if k in nr: return CITY_UF[k]
    nc=norm(city_clean)
    for k in CITY_KEYS:
        if k in nc: return CITY_UF[k]
    return None
def lead(actions):
    for a in (actions or []):
        if a['action_type']=='onsite_conversion.messaging_conversation_started_7d': return float(a['value'])
    return 0

# ── fetch ano todo, agrega por #NNN ──
print(f'Buscando {SINCE} → {UNTIL} em {len(ACCOUNTS)} contas...')
by_tag={}
for i,acc in enumerate(ACCOUNTS,1):
    url=f'{APIB}/act_{acc}/insights'
    p={'access_token':TOKEN,'fields':'campaign_name,spend,actions','time_range':json.dumps({'since':SINCE,'until':UNTIL}),'level':'campaign','limit':500}
    while url:
        try: r=requests.get(url,params=p,timeout=60); dd=r.json()
        except Exception as e: print(f'  err {acc}: {e}'); break
        if 'error' in dd: print(f'  err {acc}: {dd["error"].get("message","")[:50]}'); break
        for row in dd.get('data',[]):
            mt=TAG.search(row.get('campaign_name',''))
            if not mt: continue
            t='#'+mt.group(1)
            sp=float(row.get('spend',0)); ms=lead(row.get('actions'))
            if t not in by_tag: by_tag[t]={'spend':0,'msgs':0,'raw':row['campaign_name']}
            by_tag[t]['spend']+=sp; by_tag[t]['msgs']+=ms
        url=dd.get('paging',{}).get('next'); p={}
        if not url: break
    if i%10==0: print(f'  {i}/{len(ACCOUNTS)} contas...')
    time.sleep(0.05)

# ── agrega por UF ──
uf=defaultdict(lambda:{'spend':0,'msgs':0,'cidades':[]}); nd=[]
for t,info in by_tag.items():
    if info['msgs']<1 and info['spend']<1: continue
    city=clean_city(info['raw']); u=detect_uf(info['raw'],city)
    cpl=info['spend']/info['msgs'] if info['msgs'] else 0
    rec={'tag':t,'cidade':city[:32] or t,'spend':round(info['spend'],2),'msgs':int(info['msgs']),'cpl':round(cpl,2)}
    if u: uf[u]['spend']+=info['spend']; uf[u]['msgs']+=info['msgs']; uf[u]['cidades'].append(rec)
    else: nd.append(rec)

estados=[]
for u,v in uf.items():
    cpl=v['spend']/v['msgs'] if v['msgs'] else 0
    estados.append({'id':f'BR-{u}','uf':u,'nome':UF_NOME[u],'cpl':round(cpl,2),'spend':round(v['spend'],2),'msgs':int(v['msgs']),'n_cidades':len(v['cidades']),'cidades':sorted(v['cidades'],key=lambda x:x['cpl'])})
estados.sort(key=lambda x:x['cpl'])
tot_sp=sum(e['spend'] for e in estados); tot_ms=sum(e['msgs'] for e in estados)
print(f'\nEstados: {len(estados)} | sem UF: {len(nd)} | CPL geral R$ {tot_sp/tot_ms:.2f}')
for e in estados: print(f"  {e['uf']}: R${e['cpl']:.2f} | {e['n_cidades']} cid | {e['msgs']} msgs")

json.dump({'estados':estados,'nao_identificados':nd,'periodo':{'since':SINCE,'until':UNTIL},'updated_at':UNTIL},
          open(BASE/'mapa_cpl_data.json','w'),ensure_ascii=False,indent=1)
print('\n✅ mapa_cpl_data.json (ano todo) salvo')
