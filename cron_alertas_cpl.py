#!/usr/bin/env python3
"""
Orquestrador diário dos alertas de CPL (chamado via python3 no cron — evita o
bloqueio 'Operation not permitted' do macOS ao rodar .sh em ~/Downloads).
Detecta altas -> publica alertas.json (painel do dashboard) -> Telegram -> Discord.
"""
import subprocess, sys, time
from pathlib import Path

BASE = Path("/Users/alexrangelalves/Downloads/Conexão mtds")
PY = sys.executable

def log(m): print(f'[{time.strftime("%Y-%m-%d %H:%M:%S")}] {m}', flush=True)

def run(args):
    r = subprocess.run(args, cwd=str(BASE), capture_output=True, text=True)
    if r.stdout: print(r.stdout.rstrip())
    if r.returncode != 0 and r.stderr: print('ERR:', r.stderr[-300:])
    return r

log('=== alertas CPL: início ===')
run([PY, str(BASE / 'detectar_variacao_cpl.py')])

# publica alertas.json (atualiza o painel do dashboard no GitHub Pages)
subprocess.run(['git', '-C', str(BASE), 'add', 'alertas.json'], capture_output=True, text=True)
c = subprocess.run(['git', '-C', str(BASE), 'commit', '-m', f'alertas CPL {time.strftime("%Y-%m-%d")}'],
                   capture_output=True, text=True)
if c.returncode == 0:
    subprocess.run(['git', '-C', str(BASE), 'push'], capture_output=True, text=True)
    log('alertas.json publicado')
else:
    log('alertas.json sem mudanças')

run([PY, str(BASE / 'notificar_telegram.py')])
run([PY, str(BASE / 'notificar_discord.py')])
log('=== alertas CPL: fim ===')
