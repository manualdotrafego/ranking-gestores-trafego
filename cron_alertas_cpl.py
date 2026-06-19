#!/usr/bin/env python3
"""
Orquestrador diário dos alertas de CPL (chamado via python3 no cron — evita o
bloqueio 'Operation not permitted' do macOS ao rodar .sh em ~/Downloads).
Detecta altas -> publica alertas.json (painel do dashboard) -> Telegram -> Discord.
Roda de SEGUNDA a SEXTA (configurado no cron: 35 9 * * 1-5).
Qualquer falha em qualquer etapa é notificada no Telegram (chat pessoal), em vez
de ser ignorada.
"""
import subprocess, sys, time, os
from pathlib import Path
from dotenv import load_dotenv
import requests

BASE = Path(os.environ.get("PROJECT_DIR", "/Users/alexrangelalves/Downloads/Conexão mtds"))
PY = sys.executable
load_dotenv(dotenv_path=BASE / ".env")
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TG_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "").strip()

def log(m): print(f'[{time.strftime("%Y-%m-%d %H:%M:%S")}] {m}', flush=True)

def notify_failure(stage, detail):
    """Avisa no Telegram (chat pessoal) que uma etapa falhou."""
    msg = (f'⚠️ <b>Falha na rotina de alertas de CPL</b>\n'
           f'Etapa: <b>{stage}</b>\n'
           f'<code>{(detail or "").strip()[-600:]}</code>\n'
           f'({time.strftime("%d/%m %H:%M")})')
    if not (TG_TOKEN and TG_CHAT):
        log(f'!! sem Telegram p/ avisar falha em {stage}'); return
    try:
        requests.post(f'https://api.telegram.org/bot{TG_TOKEN}/sendMessage',
                      json={'chat_id': TG_CHAT, 'text': msg, 'parse_mode': 'HTML'}, timeout=30)
        log(f'falha em "{stage}" notificada no Telegram')
    except Exception as e:
        log(f'!! não consegui notificar falha ({stage}): {e}')

def run(stage, args):
    """Executa uma etapa; retorna True se OK, False se falhou (e notifica)."""
    try:
        r = subprocess.run(args, cwd=str(BASE), capture_output=True, text=True, timeout=1800)
    except Exception as e:
        notify_failure(stage, f'exceção ao executar: {e}'); return False
    if r.stdout: print(r.stdout.rstrip())
    failed = (r.returncode != 0) or ('❌' in (r.stdout or ''))
    if failed:
        notify_failure(stage, (r.stdout or '')[-300:] + '\n' + (r.stderr or '')[-300:])
    return not failed

def main():
    log('=== alertas CPL: início ===')
    erros = []

    # 1) detecção
    if not run('detecção de altas', [PY, str(BASE / 'detectar_variacao_cpl.py')]):
        erros.append('detecção')
        # sem alertas.json válido não adianta seguir
        log('=== alertas CPL: abortado (falha na detecção) ==='); return

    # 2) publica alertas.json (painel do dashboard) — pulado no CI (workflow commita)
    if os.getenv('SKIP_GIT') == '1':
        log('SKIP_GIT=1 — publicação delegada ao workflow do GitHub Actions')
    else:
        try:
            subprocess.run(['git', '-C', str(BASE), 'add', 'alertas.json'], capture_output=True, text=True, timeout=120)
            c = subprocess.run(['git', '-C', str(BASE), 'commit', '-m', f'alertas CPL {time.strftime("%Y-%m-%d")}'],
                               capture_output=True, text=True, timeout=120)
            if c.returncode == 0:
                p = subprocess.run(['git', '-C', str(BASE), 'push'], capture_output=True, text=True, timeout=300)
                if p.returncode == 0:
                    log('alertas.json publicado')
                else:
                    erros.append('publicação dashboard'); notify_failure('publicação dashboard (git push)', p.stderr[-400:])
            else:
                log('alertas.json sem mudanças')
        except Exception as e:
            erros.append('publicação dashboard'); notify_failure('publicação dashboard', str(e))

    # 3) Telegram  | 4) Discord
    if os.getenv('DRY_RUN') == '1':
        log('DRY_RUN=1 — envio de Telegram/Discord PULADO (validação sem notificar o time)')
    else:
        if not run('envio Telegram', [PY, str(BASE / 'notificar_telegram.py')]): erros.append('Telegram')
        if not run('envio Discord',  [PY, str(BASE / 'notificar_discord.py')]):  erros.append('Discord')

    if erros:
        log(f'=== alertas CPL: fim COM FALHAS: {", ".join(erros)} ===')
    else:
        log('=== alertas CPL: fim (tudo ok) ===')

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        notify_failure('rotina (erro inesperado)', repr(e))
        raise
