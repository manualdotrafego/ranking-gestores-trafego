#!/usr/bin/env python3
"""
Atualiza diariamente os relatórios (prints) + links 'Relatório Novo' no Notion
de TODOS os gestores, com janela móvel dos últimos WINDOW_DAYS dias.
Agendado via crontab às 09:00. Roda os 6 gestores em sequência.
"""
import subprocess, re, sys, time
from datetime import date, timedelta
from pathlib import Path

BASE = Path('/Users/alexrangelalves/Downloads/Conexão mtds')
PY = sys.executable

def log(msg):
    print(f'[{time.strftime("%Y-%m-%d %H:%M:%S")}] {msg}', flush=True)

# ── PAUSA ──────────────────────────────────────────────────────────────────────
# Se existir o arquivo-flag, a atualização diária fica suspensa (período fixo
# definido manualmente). Basta apagar o flag para retomar a rotina normal.
PAUSE_FLAG = BASE / '.pause_relatorios'
if PAUSE_FLAG.exists():
    log(f'PAUSADO ({PAUSE_FLAG.name} existe) — atualização diária suspensa. '
        f'Apague o flag para retomar.')
    sys.exit(0)

# Janela móvel dos últimos WINDOW_DAYS dias (mínimo exigido: 40).
# Antes era "1º dia do mês → hoje", que no começo do mês deixava o relatório
# com 1-2 dias de dados e sem histórico para navegar por data.
WINDOW_DAYS = 45
today = date.today()
since = (today - timedelta(days=WINDOW_DAYS - 1)).isoformat()
until = today.isoformat()

# Atualiza FIXED_SINCE/UNTIL no módulo compartilhado
f = BASE/'gerar_relatorios_todos_v2.py'
s = f.read_text()
s = re.sub(r'FIXED_SINCE = "[\d-]+"', f'FIXED_SINCE = "{since}"', s)
s = re.sub(r'FIXED_UNTIL = "[\d-]+"', f'FIXED_UNTIL = "{until}"', s)
f.write_text(s)

log(f'=== INÍCIO — período {since} → {until} ===')

GESTORES = ['braga','igor','milena','victor','bueno','mota']
for g in GESTORES:
    log(f'--- {g}: gerando relatórios ---')
    r1 = subprocess.run([PY, str(BASE/'pipeline_gestor.py'), g], cwd=str(BASE),
                        capture_output=True, text=True)
    # resumo do pipeline
    for line in r1.stdout.splitlines():
        if any(t in line for t in ['🎉','sem match','jobs','com #NNN','❌']):
            log(f'   {line.strip()}')
    if r1.returncode != 0:
        log(f'   ⚠️ pipeline {g} erro: {r1.stderr[-300:]}')

    log(f'--- {g}: atualizando links Notion ---')
    r2 = subprocess.run([PY, str(BASE/'atualizar_link_relatorio.py'), g], cwd=str(BASE),
                        capture_output=True, text=True)
    for line in r2.stdout.splitlines():
        if '🎉' in line or 'sem HTML' in line:
            log(f'   {line.strip()}')
    if r2.returncode != 0:
        log(f'   ⚠️ links {g} erro: {r2.stderr[-300:]}')

log('=== FIM — todos gestores atualizados ===')
