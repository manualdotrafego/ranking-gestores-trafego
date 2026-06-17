#!/bin/bash
# Detecta altas de CPL, publica alertas.json (atualiza o painel do dashboard)
# e envia o alerta por Telegram. Agendar de manhã, após o fetch do dashboard.
PY="/Library/Frameworks/Python.framework/Versions/3.14/bin/python3"
DIR="/Users/alexrangelalves/Downloads/Conexão mtds"
cd "$DIR" || exit 1

echo "===== $(date '+%Y-%m-%d %H:%M:%S') ====="
"$PY" detectar_variacao_cpl.py

# publica alertas.json no GitHub Pages (painel do dashboard)
git add alertas.json 2>/dev/null
if ! git diff --cached --quiet alertas.json 2>/dev/null; then
  git commit -m "alertas CPL $(date +%F)" >/dev/null 2>&1 && git push >/dev/null 2>&1 && echo "alertas.json publicado"
else
  echo "alertas.json sem mudanças"
fi

# notifica Telegram (skip gracioso se sem token)
"$PY" notificar_telegram.py

# notifica Discord (com ping dos responsáveis; skip gracioso se sem webhook)
"$PY" notificar_discord.py
