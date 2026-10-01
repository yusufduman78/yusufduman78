"""Generate profile artwork and statistics using GitHub's own API (stdlib only)."""

import json
import os
import re
from collections import Counter
from datetime import datetime
from html import escape
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OWNER = os.environ.get("PROFILE_OWNER", "yusufduman78")
if not re.fullmatch(r"[A-Za-z0-9-]+", OWNER):
    raise ValueError("Invalid GitHub username")

PALETTES = {
    "dark": {"bg": "#101B22", "panel": "#17272F", "line": "#2A4049", "ink": "#F1F6F4", "muted": "#A3B9BC", "accent": "#64DBBA"},
    "light": {"bg": "#F0F5F1", "panel": "#E5EEE8", "line": "#C5D6CC", "ink": "#142C29", "muted": "#4F6861", "accent": "#087F67"},
}


def api(path):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "yusuf-profile", "X-GitHub-Api-Version": "2022-11-28"}
    token = os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urlopen(Request("https://api.github.com/" + path, headers=headers), timeout=30) as response:
        return json.load(response)


def collect():
    repositories = []
    page = 1
    while True:
        batch = api(f"users/{OWNER}/repos?type=owner&per_page=100&page={page}")
        repositories.extend(repo for repo in batch if not repo["fork"] and not repo["private"])
        if len(batch) < 100:
            break
        page += 1
    languages = Counter()
    for repo in repositories:
        languages.update(api(f"repos/{OWNER}/{repo['name']}/languages"))
    return repositories, languages


def svg(width, height, palette, title, description, body):
    p = palette
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
<title id="title">{escape(title)}</title><desc id="desc">{escape(description)}</desc>
<rect width="{width}" height="{height}" rx="22" fill="{p['bg']}"/>
<g font-family="Arial, Helvetica, sans-serif">{body}</g></svg>\n'''


def header(p):
    lines = []
    points = [(885, 113), (990, 73), (1080, 145), (877, 229), (983, 192), (1090, 263), (955, 315)]
    for a, b in [(0, 1), (0, 3), (0, 4), (1, 2), (1, 4), (2, 4), (2, 5), (3, 4), (3, 6), (4, 5), (4, 6), (5, 6)]:
        x1, y1 = points[a]
        x2, y2 = points[b]
        lines.append(f'<path d="M{x1} {y1}L{x2} {y2}" fill="none" stroke="{p["line"]}" stroke-width="2"/>')
    for i, (x, y) in enumerate(points):
        lines.append(f'<circle cx="{x}" cy="{y}" r="{9 if i == 4 else 5}" fill="{p["accent"]}" opacity="{1 if i == 4 else .65}"/>')
    body = f'''
<path d="M44 53h26" stroke="{p['accent']}" stroke-width="4" stroke-linecap="round"/>
<text x="84" y="59" font-size="16" font-weight="700" letter-spacing="3" fill="{p['muted']}">YUSUFDUMAN78 / GITHUB</text>
<text x="44" y="167" font-size="80" font-weight="700" letter-spacing="-3" fill="{p['ink']}">Yusuf Duman<tspan fill="{p['accent']}">.</tspan></text>
<text x="48" y="220" font-size="23" fill="{p['muted']}">Gazi Üniversitesi · Bilgisayar Mühendisliği · 4. sınıf</text>
<text x="48" y="275" font-size="21" fill="{p['ink']}">Veriden modele, modelden uygulamaya.</text>
<rect x="44" y="317" width="668" height="42" rx="21" fill="{p['panel']}"/>
<text x="65" y="344" font-size="16" font-weight="700" fill="{p['accent']}">AGENTIC AI / LLM</text>
<circle cx="253" cy="338" r="2" fill="{p['muted']}"/>
<text x="273" y="344" font-size="16" font-weight="700" fill="{p['muted']}">BACKEND</text>
<circle cx="375" cy="338" r="2" fill="{p['muted']}"/>
<text x="395" y="344" font-size="16" font-weight="700" fill="{p['muted']}">BİLGİSAYARLI GÖRÜ</text>
{''.join(lines)}
<text x="846" y="364" font-family="monospace" font-size="13" letter-spacing="2" fill="{p['muted']}">LEARN. BUILD. ITERATE.</text>'''
    return svg(1200, 400, p, "Yusuf Duman", "Gazi Üniversitesi Bilgisayar Mühendisliği, 4. sınıf. Agentic AI, LLM, backend ve bilgisayarlı görü.", body)


def statistics(p, repositories, languages, date):
    top = languages.most_common(4)
    total_bytes = sum(languages.values())
    metrics = [(48, len(repositories), "ÖZGÜN REPO"), (281, sum(repo["stargazers_count"] for repo in repositories), "TOPLAM YILDIZ"), (514, len(languages), "KOD DİLİ")]
    body = f'<text x="48" y="50" font-size="16" font-weight="700" letter-spacing="2" fill="{p["muted"]}">GITHUB / ÜRETİM</text>'
    for x, value, label in metrics:
        body += f'<text x="{x}" y="120" font-size="48" font-weight="700" fill="{p["ink"]}">{value}</text><text x="{x}" y="152" font-size="13" font-weight="700" letter-spacing="1" fill="{p["muted"]}">{label}</text>'
    body += f'<path d="M749 44v174" stroke="{p["line"]}"/><text x="790" y="50" font-size="14" font-weight="700" fill="{p["muted"]}">KOD DAĞILIMI</text>'
    for i, (language, size) in enumerate(top):
        percent = size / total_bytes * 100 if total_bytes else 0
        y = 81 + i * 34
        body += f'<text x="790" y="{y}" font-size="14" fill="{p["ink"]}">{escape(language)}</text><text x="1149" y="{y}" text-anchor="end" font-size="14" fill="{p["muted"]}">%{percent:.1f}</text><rect x="790" y="{y + 7}" width="359" height="4" rx="2" fill="{p["panel"]}"/><rect x="790" y="{y + 7}" width="{359 * percent / 100:.1f}" height="4" rx="2" fill="{p["accent"]}"/>'
    body += f'<text x="48" y="215" font-family="monospace" font-size="12" fill="{p["muted"]}">GÜNCELLEME {date} · PUBLIC REPOS · FORKLAR HARİÇ</text>'
    description = f"{len(repositories)} herkese açık özgün repo, {sum(repo['stargazers_count'] for repo in repositories)} yıldız, {len(languages)} kod dili. Güncelleme: {date}. En büyük dört dil: " + ", ".join(f"{language} %{size / total_bytes * 100:.1f}" for language, size in top)
    return svg(1200, 250, p, "Yusuf Duman — GitHub istatistikleri", description, body)


def main():
    # Fetch everything before writing: an API failure keeps the last good cards.
    repositories, languages = collect()
    date = datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%d.%m.%Y")
    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)
    for mode, palette in PALETTES.items():
        (assets / f"header-{mode}.svg").write_text(header(palette), encoding="utf-8")
        (assets / f"github-stats-{mode}.svg").write_text(statistics(palette, repositories, languages, date), encoding="utf-8")
    print(f"Updated profile cards: {len(repositories)} public owned repos, {len(languages)} languages")


if __name__ == "__main__":
    main()
