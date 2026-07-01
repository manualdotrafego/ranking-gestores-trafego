"""
Agente de busca de criativos — Meta Ad Library (Playwright, sem API/token)
Nicho: Aparelho Dental, Implante, Canal dentário | Países: BR, US, PT
Ranking: Longevidade (dias no ar)

Uso:
    python3 ad_library_scraper.py
    python3 ad_library_scraper.py --termo "implante dental" --pais BR --limite 30
"""

import argparse
import re
import time
from datetime import datetime, date
from math import log
from typing import Optional

import pandas as pd
from playwright.sync_api import sync_playwright

# ─────────────────────────────────────────
# CONFIGURAÇÕES
# ─────────────────────────────────────────

TERMOS_NICHO = [
    "aparelho dental",
    "aparelho ortodôntico",
    "aparelho invisível",
    "ortodontia",
    "orthodontic braces",
    "invisalign",
    "aparelho dentário",
    "alinhador dental",
]

PAISES = ["BR", "US", "PT"]

MESES_PT = {
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
}
MESES_EN = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# ─────────────────────────────────────────
# PARSING DE DATA
# ─────────────────────────────────────────

def _parse_data(texto: str) -> Optional[date]:
    """
    Extrai data de strings como:
      'Veiculação iniciada em 18 de out de 2024'
      'Started running on Jan 18, 2024'
    """
    # PT: "18 de out de 2024"
    m = re.search(r'(\d{1,2})\s+de\s+(\w+)\.?\s+de\s+(\d{4})', texto, re.IGNORECASE)
    if m:
        dia, mes_str, ano = int(m.group(1)), m.group(2).lower()[:3], int(m.group(3))
        mes = MESES_PT.get(mes_str)
        if mes:
            return date(ano, mes, dia)

    # EN: "Jan 18, 2024"
    m = re.search(r'(\w+)\s+(\d{1,2}),\s+(\d{4})', texto, re.IGNORECASE)
    if m:
        mes_str, dia, ano = m.group(1).lower()[:3], int(m.group(2)), int(m.group(3))
        mes = MESES_EN.get(mes_str)
        if mes:
            return date(ano, mes, dia)

    # ISO: "2024-01-18"
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', texto)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    return None


def _dias_no_ar(inicio: Optional[date]) -> int:
    if not inicio:
        return 0
    return max((date.today() - inicio).days, 0)


def _score(dias: int) -> float:
    return round(log(dias + 1) * 10, 2)


# ─────────────────────────────────────────
# PARSER DO TEXTO DA PÁGINA
# ─────────────────────────────────────────

def _parse_pagina(texto_completo: str) -> list[dict]:
    """
    Analisa o texto completo da página e extrai blocos de anúncios.
    Estrutura conhecida do Meta Ad Library:
      Ativo|Encerrado
      Identificação da biblioteca: {ID}
      Veiculação iniciada em {DATA}
      ...
      {NOME DA PÁGINA}
      Patrocinado
      {COPY DO ANÚNCIO}
    """
    linhas = [l.strip() for l in texto_completo.split("\n") if l.strip() and l.strip() != "​"]

    anuncios = []
    i = 0
    while i < len(linhas):
        linha = linhas[i]

        # Detecta início de bloco de anúncio
        status = None
        if linha in ("Ativo", "Active"):
            status = "ATIVO"
        elif linha in ("Encerrado", "Inactive", "Completed"):
            status = "ENCERRADO"

        if status:
            ad_id = ""
            data_inicio = None
            pagina = ""
            copy_linhas = []
            encontrou_patrocinado = False

            j = i + 1
            while j < len(linhas) and j < i + 40:
                l = linhas[j]

                # ID da biblioteca
                m_id = re.search(r'(?:Identificação da biblioteca|Library ID)[:\s]+(\d+)', l)
                if m_id:
                    ad_id = m_id.group(1)
                    j += 1
                    continue

                # Data de início
                if any(kw in l for kw in ["Veiculação iniciada", "Started running", "iniciada em"]):
                    data_inicio = _parse_data(l)
                    j += 1
                    continue

                # Nome da página (linha antes de "Patrocinado")
                if l in ("Patrocinado", "Sponsored"):
                    if j > 0 and not pagina:
                        pagina = linhas[j - 1] if linhas[j - 1] not in (
                            "Ativo", "Encerrado", "Active", "Inactive", "Plataformas", "Platforms"
                        ) else ""
                    encontrou_patrocinado = True
                    j += 1
                    continue

                # Copy: linhas após "Patrocinado" até próximo anúncio
                if encontrou_patrocinado:
                    if l in ("Ativo", "Encerrado", "Active", "Inactive", "Completed"):
                        break
                    if len(l) > 20 and not re.match(r'^(Plataformas|Platforms|Filtros|Classificar|Ver detalhes)', l):
                        copy_linhas.append(l)
                    if len(copy_linhas) >= 3:
                        break

                j += 1

            # Só adiciona se tiver ID (confirma que é um anúncio real)
            if ad_id:
                dias = _dias_no_ar(data_inicio)
                anuncios.append({
                    "ad_id": ad_id,
                    "pagina": pagina,
                    "status": status,
                    "dias_no_ar": dias,
                    "data_inicio": str(data_inicio) if data_inicio else "",
                    "score": _score(dias),
                    "copy_principal": " | ".join(copy_linhas[:2])[:300],
                    "link_criativo": f"https://www.facebook.com/ads/library/?id={ad_id}",
                })
                i = j
                continue

        i += 1

    return anuncios


# ─────────────────────────────────────────
# SCRAPER
# ─────────────────────────────────────────

def scrape_ads(termo: str, pais: str, limite: int, page) -> list[dict]:
    url = (
        f"https://www.facebook.com/ads/library/"
        f"?active_status=all&ad_type=all&country={pais}"
        f"&q={termo.replace(' ', '+')}&search_type=keyword_unordered&media_type=video"
    )

    print(f"  [{pais}] '{termo}' → {url[:70]}...")
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(4)

    # Fecha modal de cookies
    for seletor in [
        "button[title='Aceitar tudo']", "button[title='Accept All']",
        "[data-testid='cookie-policy-manage-dialog-accept-button']",
    ]:
        try:
            btn = page.locator(seletor).first
            if btn.is_visible(timeout=1500):
                btn.click()
                time.sleep(1)
                break
        except Exception:
            pass

    anuncios = []
    sem_progresso = 0

    while len(anuncios) < limite and sem_progresso < 4:
        texto = page.evaluate("() => document.body.innerText")
        novos = _parse_pagina(texto)

        # Filtra apenas os não vistos
        ids_vistos = {a["ad_id"] for a in anuncios}
        novos_unicos = [a for a in novos if a["ad_id"] not in ids_vistos]

        if not novos_unicos:
            sem_progresso += 1
        else:
            sem_progresso = 0
            for a in novos_unicos:
                a["pais"] = pais
            anuncios.extend(novos_unicos)

        if len(anuncios) < limite:
            page.evaluate("window.scrollBy(0, 2500)")
            time.sleep(2.5)

    return anuncios[:limite]


# ─────────────────────────────────────────
# PROCESSAMENTO E RANKING
# ─────────────────────────────────────────

def processar(todos: list[dict], ultimos_dias: int = 0) -> pd.DataFrame:
    df = pd.DataFrame(todos)
    if df.empty:
        return df
    df = df.drop_duplicates(subset="ad_id")
    if ultimos_dias > 0:
        df = df[df["dias_no_ar"] <= ultimos_dias]
    df = df.sort_values("score", ascending=False).reset_index(drop=True)
    df.index += 1
    df.index.name = "rank"
    return df


# ─────────────────────────────────────────
# EXPORTAÇÃO
# ─────────────────────────────────────────

def exportar(df: pd.DataFrame, sufixo: str = ""):
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    arquivo = f"criativos_dental_{ts}{sufixo}.xlsx"

    # Prepara df sem a coluna de link (vai ser recriada como hiperlink)
    df_export = df.copy()
    links = df_export["link_criativo"].tolist() if "link_criativo" in df_export.columns else []
    df_export = df_export.drop(columns=["link_criativo"], errors="ignore")

    with pd.ExcelWriter(arquivo, engine="openpyxl") as writer:
        df_export.to_excel(writer, sheet_name="Criativos", index=True)
        ws = writer.sheets["Criativos"]

        # Larguras das colunas
        larguras = {"A": 6, "B": 42, "C": 8, "D": 8, "E": 13, "F": 8, "G": 8, "H": 90}
        for col, w in larguras.items():
            ws.column_dimensions[col].width = w

        # Cabeçalho — fundo azul escuro, texto branco, negrito
        header_fill = PatternFill("solid", fgColor="1F3864")
        header_font = Font(bold=True, color="FFFFFF", size=10)
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        # Adiciona coluna "Ver Criativo" com hiperlinks clicáveis
        link_col = ws.max_column + 1
        link_col_letter = get_column_letter(link_col)
        ws.column_dimensions[link_col_letter].width = 18
        ws.cell(row=1, column=link_col, value="Ver Criativo").font = header_font
        ws.cell(row=1, column=link_col).fill = header_fill
        ws.cell(row=1, column=link_col).alignment = Alignment(horizontal="center")

        link_font = Font(color="1155CC", underline="single", size=10)
        alt_fill = PatternFill("solid", fgColor="EEF2F7")

        for i, url in enumerate(links):
            row = i + 2
            cell = ws.cell(row=row, column=link_col)
            if url:
                cell.value = "🔗 Abrir anúncio"
                cell.hyperlink = url
                cell.font = link_font
            cell.alignment = Alignment(horizontal="center", vertical="center")

            # Zebrado nas linhas
            if i % 2 == 1:
                for c in range(1, link_col + 1):
                    ws.cell(row=row, column=c).fill = alt_fill

            # Altura e wrap nas linhas de dados
            ws.row_dimensions[row].height = 40
            for c in range(1, link_col):
                ws.cell(row=row, column=c).alignment = Alignment(vertical="center", wrap_text=True)

        # Congela linha do cabeçalho
        ws.freeze_panes = "A2"

    print(f"\nExportado: {arquivo}")
    return arquivo


# ─────────────────────────────────────────
# AGENTE PRINCIPAL
# ─────────────────────────────────────────

def rodar_agente(termos=None, paises=None, limite_por_busca=20, exportar_resultado=True, ultimos_dias=0, top_n=20):
    termos  = termos  or TERMOS_NICHO
    paises  = paises  or PAISES

    print("=" * 60)
    print("  AGENTE — META AD LIBRARY | NICHO DENTAL")
    print(f"  {len(termos)} termos × {len(paises)} países | {limite_por_busca} ads/busca")
    print("=" * 60)

    todos = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="pt-BR",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        for pais in paises:
            for termo in termos:
                try:
                    ads = scrape_ads(termo, pais, limite_por_busca, page)
                    print(f"  → {len(ads)} anúncios coletados")
                    todos.extend(ads)
                except Exception as e:
                    print(f"  ERRO: {e}")

        browser.close()

    if not todos:
        print("\nNenhum anúncio encontrado.")
        return None

    df = processar(todos, ultimos_dias=ultimos_dias)
    filtro_str = f" (filtro: últimos {ultimos_dias} dias)" if ultimos_dias > 0 else ""
    print(f"\nTotal único: {len(df)} anúncios{filtro_str}")

    print("\n" + "=" * 60)
    print(f"  TOP {top_n} — RANKING POR LONGEVIDADE{filtro_str.upper()}")
    print("=" * 60)
    cols = ["pagina", "status", "pais", "dias_no_ar", "score", "copy_principal"]
    print(df.head(top_n)[cols].to_string())

    if exportar_resultado:
        exportar(df)

    return df


# ─────────────────────────────────────────
# CLI
# ─────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Meta Ad Library Scraper — Nicho Dental")
    parser.add_argument("--termo", nargs="+", help="Termos de busca customizados")
    parser.add_argument("--pais",  nargs="+", default=["BR", "US", "PT"])
    parser.add_argument("--limite", type=int, default=20, help="Anúncios por busca (padrão: 20)")
    parser.add_argument("--sem-export", action="store_true")
    parser.add_argument("--ultimos-dias", type=int, default=0, help="Filtrar só anúncios dos últimos N dias (0 = sem filtro)")
    parser.add_argument("--top", type=int, default=20, help="Quantos resultados exibir no ranking (padrão: 20)")
    args = parser.parse_args()

    rodar_agente(
        termos=args.termo,
        paises=args.pais,
        limite_por_busca=args.limite,
        exportar_resultado=not args.sem_export,
        ultimos_dias=args.ultimos_dias,
        top_n=args.top,
    )
