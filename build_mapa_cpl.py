#!/usr/bin/env python3
"""Gera mapa coroplético do Brasil com CPL médio por estado (amCharts5) + tooltip com cidades."""
import json, re, unicodedata
from pathlib import Path
from collections import defaultdict

BASE = Path('/Users/alexrangelalves/Downloads/Conexão mtds')
d = json.load(open(BASE/'dashboard_data.json'))

TAG = re.compile(r'#(\d+)')
UFS = {'AC','AL','AM','AP','BA','CE','DF','ES','GO','MA','MG','MS','MT','PA','PB','PE','PI','PR','RJ','RN','RO','RR','RS','SC','SE','SP','TO'}
UF_TOK = re.compile(r'[/\-\s\(]([A-Z]{2})\b')

def norm(s):
    s = unicodedata.normalize('NFD', s)
    return ''.join(c for c in s if unicodedata.category(c)!='Mn').upper()

def clean_city(n):
    s = re.sub(r'#\d+\s*[\|\-]?\s*', '', n)
    s = re.sub(r'\[[^\]]*\]', '', s)
    s = re.sub(r'\([^\)]*\)', '', s)
    s = re.sub(r'R?\$\s*[\d.,]+', '', s)
    s = re.sub(r'\b\d{1,2}[/.]\d{1,2}(?:[/.]\d{2,4})?\b', '', s)
    s = re.sub(r'\b\d{2,6}\b', '', s)
    s = re.sub(r'\b(C\d|CP\d+|CBO|ABO|DBOUT|MARCA|ORTO|PROTESE|PRÓTESE|IMPLANTE|IMPLANTES|LEADS|ENGAJAMENTO|TRAFEGO|TRÁFEGO|TESTE|CONEGO|CÔNEGO|REPUBLICADA|REPUBLICADO|CLINICO|CLÍNICO|S/M|SEM GRÁTIS|SEM GRATIS|COP|LIQUIDO|PAG NOVA|PÁG NOVA)\b', '', s, flags=re.I)
    s = re.sub(r'[|/\-–—.,]+', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s

# Dicionário cidade(normalizada, substring) -> UF
CITY_UF = {
 'SAO PAULO':'SP','SOROCABA':'SP','SAO JOSE DO RIO PRETO':'SP','SJRP':'SP','RIBEIRAO PRETO':'SP','SAO JOSE DOS CAMPOS':'SP','SJC':'SP','BAURU':'SP','ARARAQUARA':'SP','BATATAIS':'SP','ITAPETININGA':'SP','ITU':'SP','JAGUARIUNA':'SP','MARILIA':'SP','MATAO':'SP','MAUA':'SP','OSASCO':'SP','PRESIDENTE PRUDENTE':'SP','SANTO ANDRE':'SP','SAO BERNARDO':'SP','SAO CAETANO':'SP','SAO VICENTE':'SP','TAUBATE':'SP','TUPA':'SP','INDAIATUBA':'SP','MIRASSOL':'SP','MOGI':'SP','OLIMPIA':'SP','PEDREIRA':'SP','PRAIA GRANDE':'SP','SALTO':'SP','SAO CARLOS':'SP','SUMARE':'SP','TUCURUVI':'SP','TATUAPE':'SP','VILA FORMOSA':'SP','SANTA BARBARA D':'SP','SANTOS':'SP','GUARULHOS':'SP','HORTOLANDIA':'SP','SAO MIGUEL PAULISTA':'SP','VINCY BEAUTY CAMBUCI':'SP','CAMBUCI':'SP','MOOCA':'SP','BANGU':'SP','ARUJA':'SP','PROMISSAO':'SP','ITUVERAVA':'SP','CATANDUVA':'SP','PERUS':'SP','MORRO DOCE':'SP','SAO PEDRO DA ADEIA':'RJ',
 'RIO DE JANEIRO':'RJ','CABO FRIO':'RJ','ARARUAMA':'RJ','NOVA FRIBURGO':'RJ','MADUREIRA':'RJ','RIO BONITO':'RJ','SANTO ANTONIO DE PADUA':'RJ','SANTO ANTONIO PADUA':'RJ','PADUA':'RJ','NITEROI':'RJ','VOLTA REDONDA':'RJ','BARRA MANSA':'RJ','DUQUE DE CAXIAS':'RJ','RECANTO DAS EMAS':'DF','SAO JOAO DE MERITI':'RJ','NOVA IGUACU':'RJ',
 'BELO HORIZONTE':'MG','BETIM':'MG','IPATINGA':'MG','JUIZ DE FORA':'MG','UBERLANDIA':'MG','MONTE CARMELO':'MG','RESPLENDOR':'MG','JOAO MONLEVADE':'MG','AIMORES':'MG','MONTES CLAROS':'MG','MOC':'MG','OURO PRETO':'MG','MARIANA':'MG','PASSOS':'MG','BOTELHOS':'MG','POCOS DE CALDAS':'MG','TIMOTEO':'MG','VICOSA':'MG','SANTA BARBARA':'MG','UNAI':'MG','PARACATU':'MG','PATO DE MINAS':'MG','PATOS DE MINAS':'MG','CONSELHEIRO LAFAIETE':'MG','BARAO DE COCAIS':'MG','ESPERA FELIZ':'MG','SAO LOURENCO':'MG','DIVINO':'MG','CURVELO':'MG','GOV VALADARES':'MG','GOVERNADOR VALADARES':'MG','IEB GOV':'MG','UBA':'MG','UBÁ':'MG','SETE LAGOAS':'MG','PIRAPORA':'MG','CONSELHEIRO':'MG','ITAUNA':'MG','SANTANA':'MG',
 'PORTO ALEGRE':'RS','GRAVATAI':'RS','CACHOEIRINHA':'RS','CAMPO BOM':'RS','FARROUPILHA':'RS','SAO LEOPOLDO':'RS','SAPIRANGA':'RS','SANTA MARIA':'RS','TRES DE MAIO':'RS','SANTO ANTONIO DA PATRULHA':'RS','VENANCIO AIRES':'RS','LAJEADO':'RS','PASSO FUNDO':'RS','ERECHIM':'RS','ALVORADA':'RS','TRAMANDAI':'RS','SANTA CRUZ DO SUL':'RS','SARANDI':'RS',
 'CURITIBA':'PR','COLOMBO':'PR','CAMPO LARGO':'PR','PINHAIS':'PR','PIRAQUARA':'PR','PONTA GROSSA':'PR','CASCAVEL':'PR','CAMPO MOURAO':'PR','ARAPONGAS':'PR','PARANAVAI':'PR','CAMBE':'PR','CAMPINA GRANDE DO SUL':'PR','FAZENDA RIO':'PR','SAO JOSE DOS PINHAIS':'PR','MARECHAL':'PR','XV NOVEBRO':'PR','XV DE NOVEMBRO':'PR','IBIPORA':'PR','MARINGA':'PR','FLORIANO PEIXOTO':'PR',
 'JOINVILLE':'SC','BRUSQUE':'SC','CRICIUMA':'SC','ITAJAI':'SC','CHAPECO':'SC','BALNEARIO CAMBORIU':'SC','CAMBORIU':'SC','NAVEGANTES':'SC','ITUPORANGA':'SC','PRESIDENTE GETULIO':'SC','RIO DO SUL':'SC','FLORIPA':'SC','FLORIANOPOLIS':'SC',
 'SALVADOR':'BA','CAETITE':'BA','LUIS EDUARDO MAGALHAES':'BA','VITORIA DA CONQUISTA':'BA','ITABUNA':'BA','GUANAMBI':'BA','JUAZEIRO':'BA','SENHOR DO BONFIM':'BA','BARREIRAS':'BA','JACOBINA':'BA','SANTA MARIA DA VITORIA':'BA','CAJAZEIRAS':'BA',
 'GOIANIA':'GO','APARECIDA DE GOIANIA':'GO','APARECDIA':'GO','CATALAO':'GO','SENADOR CANEDO':'GO','LUZIANIA':'GO','QUIRINOPOLIS':'GO','AGUAS LINDAS':'GO','VALPARAISO':'GO','ITUMBIARA':'GO','CALDAS NOVAS':'GO','TRINDADE':'GO','GAMA':'DF','PLANALTINA':'DF','PARANOA':'DF','CEILANDIA':'DF','VICENTE PIRES':'DF','BRASILIA':'DF','BRAZLANDIA':'DF',
 'CUIABA':'MT','RONDONOPOLIS':'MT','SINOP':'MT','LUCAS DO RIO VERDE':'MT','NOVA MUTUM':'MT','PRIMAVERA DO LESTE':'MT','SORRISO':'MT',
 'CAMPO GRANDE':'MS','DOURADOS':'MS','TRES LAGOAS':'MS','CORUMBA':'MS','DOIS IRMAO':'MS','ROLIM DE MOURA':'RO',
 'RECIFE':'PE','PETROLINA':'PE','CARUARU':'PE','PALMAS':'TO',
 'MANAUS':'AM','BELEM':'PA','SOURE':'PA','ABAETETUBA':'PA','SAO MATEUS':'ES','VILA VELHA':'ES','SERRA':'ES','LINHARES':'ES','CACHOEIRO':'ES','COLATINA':'ES','GUARAPARI':'ES','JOAO NEIVA':'ES','VITORIA':'ES','BAIXO GUANDU':'ES','NOVA VENECIA':'ES','CONSELHEIRO PENA':'MG',
 'FORTALEZA':'CE','CRATO':'CE','JUAZEIRO DO NORTE':'CE','BATURITE':'CE','ARACATI':'CE','ACARAU':'CE','COIFE ACARAU':'CE',
 'JOAO PESSOA':'PB','CAMPINA GRANDE':'PB','QUEIMADAS':'PB','NATAL':'RN','TEIXEIRA DE FREITAS':'BA','MACEIO':'AL',
 'TEOFILO':'MG','BOCAIUVA':'MG','GRAJAU':'MA','TAGUATINGA':'DF','SANTA ROSA':'RS','CARAZINHO':'RS','OLINDA':'PE','IBATIBA':'ES','VESPASIANO':'MG','CONTAGEM':'MG','ITAPEVI':'SP','SAO JOAO DO IVAI':'PR','SAO CONRADO':'RJ','SANTO AMARO':'SP','LINS':'SP','PEIXOTO AZEVEDO':'MT','BACABAL':'MA','VOTUPORANGA':'SP','UMUARAMA':'PR','CRICIUMA':'SC',
 'RIO CLARO':'SP','FRANCA':'SP','BOTUCATU':'SP','BARUERI':'SP','LAPA':'SP','SAO SEBASTIAO':'SP','CAMPOS DOS GOYTACASES':'RJ','CAMPO DOS GOYTACASES':'RJ','GOYTACASES':'RJ','GOYTACAZES':'RJ','DOURADOS':'MS','ITAGUAI':'RJ','BAIXO GUANDU':'ES','POCOS DE CALDAS':'MG','PALMARES':'PE','GUARULHOS':'SP','JAU':'SP','JAU SP':'SP','SABARA':'MG','LUMINA BH':'MG','ESPIRITO SANTO':'ES',
 'CAMETA':'PA','ANTONIO DA PATRULHA':'RS','SAO GONCALO':'RJ','PCS DE CALDAS':'MG','S.J IVAI':'PR','S J IVAI':'PR','JARU':'RO','GOIANIRA':'GO','JANDIRA':'SP','PARANAIBA':'MS','SIMONESIA':'MG','SUZANO':'SP','DOIS IRMAO':'RS','2IRMAO':'RS','ODONTOVIP':'RJ','V. REDONDA':'RJ','V REDONDA':'RJ','JACAREI':'SP','JANUARIA':'MG','VICENTE PIRES':'DF','ITAGUAI':'RJ',
 'SAO PEDRO DA ALDEIA':'RJ','PRADO':'BA','CONS.PENA':'MG','CONS PENA':'MG','SJ. RIO PRETO':'SP','SJ RIO PRETO':'SP','RIO PRETO':'SP','PEIXOTO DE AZEVEDO':'MT','CAIEIRAS':'SP',
}
# ordena por tamanho desc para casar mais específico primeiro
CITY_KEYS = sorted(CITY_UF, key=lambda x: -len(x))

UF_NOME = {'AC':'Acre','AL':'Alagoas','AM':'Amazonas','AP':'Amapá','BA':'Bahia','CE':'Ceará','DF':'Distrito Federal','ES':'Espírito Santo','GO':'Goiás','MA':'Maranhão','MG':'Minas Gerais','MS':'Mato Grosso do Sul','MT':'Mato Grosso','PA':'Pará','PB':'Paraíba','PE':'Pernambuco','PI':'Piauí','PR':'Paraná','RJ':'Rio de Janeiro','RN':'Rio Grande do Norte','RO':'Rondônia','RR':'Roraima','RS':'Rio Grande do Sul','SC':'Santa Catarina','SE':'Sergipe','SP':'São Paulo','TO':'Tocantins'}

def detect_uf(raw, city_clean):
    # 1) UF token explícito
    for m in UF_TOK.findall(raw):
        if m in UFS: return m
    # 2) dicionário por substring no NOME BRUTO (pega cidades em [colchetes])
    nr = norm(raw)
    for k in CITY_KEYS:
        if k in nr: return CITY_UF[k]
    # 3) dicionário no nome limpo
    nc = norm(city_clean)
    for k in CITY_KEYS:
        if k in nc: return CITY_UF[k]
    return None

# Agrega por código #NNN
by_tag = {}
for g in d['gestores']:
    for acc in g['accounts']:
        for c in acc.get('campaigns', []):
            m = TAG.search(c['name'])
            if not m: continue
            tag = '#'+m.group(1)
            mt = c.get('metrics',{})
            sp = float(mt.get('spend',0)); ms = float(mt.get('msgs',0))
            if tag not in by_tag:
                by_tag[tag] = {'spend':0,'msgs':0,'name':c['name'],'raw':c['name']}
            by_tag[tag]['spend'] += sp
            by_tag[tag]['msgs'] += ms

# UF por código + agrega
uf_data = defaultdict(lambda: {'spend':0,'msgs':0,'cidades':[]})
nd = []
for tag, info in by_tag.items():
    if info['msgs'] < 1 and info['spend'] < 1: continue
    city = clean_city(info['name'])
    uf = detect_uf(info['raw'], city)
    cpl = info['spend']/info['msgs'] if info['msgs'] else 0
    rec = {'tag':tag,'cidade':city[:32] or tag,'spend':round(info['spend'],2),'msgs':int(info['msgs']),'cpl':round(cpl,2)}
    if uf:
        uf_data[uf]['spend'] += info['spend']
        uf_data[uf]['msgs'] += info['msgs']
        uf_data[uf]['cidades'].append(rec)
    else:
        nd.append(rec)

# Monta saída por estado
estados = []
for uf, v in uf_data.items():
    cpl = v['spend']/v['msgs'] if v['msgs'] else 0
    cids = sorted(v['cidades'], key=lambda x: x['cpl'])
    estados.append({'id':f'BR-{uf}','uf':uf,'nome':UF_NOME[uf],
                    'cpl':round(cpl,2),'spend':round(v['spend'],2),'msgs':int(v['msgs']),
                    'n_cidades':len(cids),'cidades':cids})
estados.sort(key=lambda x: x['cpl'])

print(f'Estados com dados: {len(estados)}')
print(f'Códigos sem UF identificada: {len(nd)}')
tot_sp = sum(e['spend'] for e in estados); tot_ms = sum(e['msgs'] for e in estados)
print(f'CPL geral (mapeado): R$ {tot_sp/tot_ms:.2f}' if tot_ms else 'sem dados')
for e in estados:
    print(f"  {e['uf']}: CPL R${e['cpl']:.2f} | {e['n_cidades']} cidades | {e['msgs']} msgs")

json.dump({'estados':estados,'nao_identificados':nd,
           'periodo':{'since':d.get('since'),'until':d.get('until')},
           'updated_at':d.get('updated_at')},
          open(BASE/'mapa_cpl_data.json','w'), ensure_ascii=False, indent=1)
print('\n✅ mapa_cpl_data.json salvo')
