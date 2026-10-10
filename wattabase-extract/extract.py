"""
Extraction des métadonnées d'un arrêté préfectoral ICPE (pages 1-2).

Usage : uv run extract.py

Remarque qualité (clauses « VU ») : avec pdfplumber, les clauses longues
sont coupées en plusieurs lignes (retraits de paragraphe) et les incises
restent dans le flux ; il faut recoller les lignes d'une clause avant de
l'analyser. Le numéro de page « 2/36 » du pied de page se retrouve collé
à la fin d'une clause et doit être nettoyé. Les coquilles du document
source (« située à Nantes, ; », « équipement 26 janvier 2006 ») sont
conservées telles quelles. pdfplumber suit l'ordre visuel de lecture ;
pypdf peut placer le pied de page avant l'en-tête.

Choix « exploitant » : « S.A.S. VALSPAR », nom utilisé dans la clause
décrivant la demande (successeur de la Société GEORGET, ancien exploitant).
« S.A.S. THE VALSPAR Corporation » n'apparaît que dans les clauses de
procédure ; c'est probablement une autre dénomination de la même société
ou une entité liée (hypothèse : le document ne le précise pas).
"""
import csv
import re
from pathlib import Path

import pdfplumber
import requests

URL = ("https://www.georisques.gouv.fr/webappReport/ws/installations/"
       "document/a34c9176e16c45aab2705704ac415621")
PDF = Path("data.pdf")
OUT = Path("output")
NB_PAGES = 2


# ---------- 1. Téléchargement et extraction brute ----------
def download():
    PDF.parent.mkdir(exist_ok=True)
    if not PDF.exists():  # sinon, copie locale fournie
        r = requests.get(URL, timeout=60)
        r.raise_for_status()
        PDF.write_bytes(r.content)


def normalize(t: str) -> str:
    t = t.replace("\u2019", "'").replace("\u2018", "'")  # apostrophes
    t = t.replace("\u00a0", " ")                          # espaces insécables
    return t


def extract_pages():
    with pdfplumber.open(PDF) as pdf:
        return [normalize(p.extract_text() or "") for p in pdf.pages[:NB_PAGES]]


def write_raw(pages):
    OUT.mkdir(exist_ok=True)
    with open(OUT / "raw_text.txt", "w", encoding="utf-8") as f:
        for i, p in enumerate(pages, 1):
            f.write(f"=== PAGE {i} ===\n{p}\n\n")


# ---------- 2. Utilitaires ----------
def flat(s):
    return re.sub(r"\s+", " ", s).strip()


def search(pattern, text, group=0, flags=0):
    m = re.search(pattern, text, flags)
    return flat(m.group(group)) if m else ""


def split_clauses(text):
    """Découpe le texte en clauses commençant par VU / CONSIDERANT / SUR."""
    parts = re.split(r"(?m)^(?=(?:VU|CONSIDERANT|SUR)\b)", text)
    clauses = []
    for p in parts:
        if re.match(r"(VU|CONSIDERANT|SUR)\b", p):
            c = flat(p)
            c = re.sub(r"\s*\d+/\d+$", "", c)  # pied de page « 2/36 » collé
            clauses.append(c)
    return clauses


def find_address(text):
    """Adresse après « située à <ville>, » ; ignore la clause à coquille."""
    m = re.search(
        r"situ[ée]e?\s+à\s+([A-ZÉ][\w\-éèê]+),\s*"
        r"(\d+\s*,?\s*(?:bd|boulevard|rue|avenue|quai|route)\s+[^;,]+?)\s*;",
        flat(text))
    return f"{m.group(2).strip()}, {m.group(1)}" if m else ""


def find_prefecture(text):
    m = re.search(r"PR[ÉE]FECTURE\s+DE\s+LA\s+([A-ZÉÈ\-]+)", text)
    return f"Préfecture de la {m.group(1).title()}" if m else ""


def find_objet(vu):
    clause = next((c for c in vu if re.search(r"régulariser", c, re.I)), "")
    if not clause:
        return ""
    return search(r"l'autorisation de régulariser.*?(?=,?\s*située|;|$)",
                  clause, flags=re.I)


# ---------- 3. Programme principal ----------
def main():
    download()
    pages = extract_pages()
    write_raw(pages)
    text = "\n".join(pages)

    clauses = split_clauses(text)
    vu = [c for c in clauses if c.startswith("VU")]
    cons = [c for c in clauses if c.startswith("CONSIDERANT")]
    sur = [c for c in clauses if c.startswith("SUR")]

    row = {
        "reference": search(r"\d{4}\s*ICPE/\d+", text),
        "date_signature": "",  # hors périmètre : jamais devinée
        "exploitant": ("S.A.S. VALSPAR"
                       if re.search(r"S\.A\.S\.\s+VALSPAR", text) else ""),
        "adresse": find_address(text),
        "prefecture": find_prefecture(text),
        "objet": find_objet(vu),
        "nb_clauses_vu": len(vu),
        "nb_clauses_considerant": len(cons),
        "nb_clauses_sur": len(sur),
    }

    OUT.mkdir(exist_ok=True)
    with open(OUT / "arrete.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()), delimiter=";")
        w.writeheader()
        w.writerow(row)


if __name__ == "__main__":
    main()