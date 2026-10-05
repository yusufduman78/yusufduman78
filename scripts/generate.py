#!/usr/bin/env python3
"""Generates the animated SVGs for the GitHub profile README.

Reads curated content from profile.json and live data from the GitHub GraphQL
API (token from GITHUB_TOKEN / GH_TOKEN), then writes everything into assets/.
Standard library only, so it runs on a bare GitHub Actions runner.
"""

import datetime as dt
import hashlib
import json
import math
import os
import random
import sys
import textwrap
import urllib.request
from collections import Counter
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
CONFIG = json.loads((ROOT / "profile.json").read_text(encoding="utf-8"))

# ── palette ──────────────────────────────────────────────────────────────────
BG0, BG1 = "#070b16", "#0f1530"
CYAN, VIOLET, PINK = "#22d3ee", "#a78bfa", "#f472b6"
TEXT, MUTED, DIM, LINE = "#e2e8f0", "#7c8aa5", "#475569", "#1e293b"
GREEN = "#4ade80"

MONO = "'JetBrains Mono','Fira Code','SFMono-Regular',Menlo,Consolas,monospace"
SANS = "'Segoe UI',-apple-system,'Helvetica Neue',Helvetica,Arial,sans-serif"

BASE_CSS = f"""
.mono{{font-family:{MONO}}} .sans{{font-family:{SANS}}}
.tw{{animation:tw 3s ease-in-out infinite}}
@keyframes tw{{0%,100%{{opacity:.15}}50%{{opacity:1}}}}
.blink{{animation:blink 1s steps(1) infinite}}
@keyframes blink{{50%{{opacity:0}}}}
.orbit{{animation:orbit 6s linear infinite}}
@keyframes orbit{{from{{stroke-dashoffset:100}}to{{stroke-dashoffset:0}}}}
.fade{{opacity:0;animation:fade .5s ease-out forwards}}
@keyframes fade{{to{{opacity:1}}}}
"""


def rng_for(*parts):
    seed = hashlib.md5("|".join(map(str, parts)).encode()).hexdigest()
    return random.Random(int(seed[:8], 16))


def esc(s):
    return escape(str(s), quote=True)


def svg(w, h, body, css="", defs="", label=""):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" role="img" aria-label="{esc(label)}">'
        f"<style>{BASE_CSS}{css}</style>"
        f"<defs>{GLOW_DEFS}{defs}</defs>{body}</svg>"
    )


GLOW_DEFS = f"""
<filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
  <feGaussianBlur stdDeviation="3" result="b"/>
  <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
</filter>
<filter id="softglow" x="-50%" y="-50%" width="200%" height="200%">
  <feGaussianBlur stdDeviation="1.6" result="b"/>
  <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
</filter>
<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
  <stop offset="0" stop-color="{BG0}"/><stop offset="1" stop-color="{BG1}"/>
</linearGradient>
<linearGradient id="neon" x1="0" y1="0" x2="1" y2="0">
  <stop offset="0" stop-color="{CYAN}"/><stop offset=".55" stop-color="{VIOLET}"/>
  <stop offset="1" stop-color="{PINK}"/>
</linearGradient>
<radialGradient id="nebV"><stop offset="0" stop-color="{VIOLET}" stop-opacity=".35"/>
  <stop offset="1" stop-color="{VIOLET}" stop-opacity="0"/></radialGradient>
<radialGradient id="nebC"><stop offset="0" stop-color="{CYAN}" stop-opacity=".22"/>
  <stop offset="1" stop-color="{CYAN}" stop-opacity="0"/></radialGradient>
"""


def stars(r, w, h, n, x0=0, y0=0):
    out = []
    for _ in range(n):
        x, y = x0 + r.uniform(0, w), y0 + r.uniform(0, h)
        rad = r.choice([0.5, 0.6, 0.8, 1.0, 1.2, 1.6])
        col = r.choice([TEXT, TEXT, TEXT, CYAN, VIOLET])
        out.append(
            f'<circle class="tw" cx="{x:.1f}" cy="{y:.1f}" r="{rad}" fill="{col}" '
            f'style="animation-duration:{r.uniform(2, 5.5):.1f}s;'
            f'animation-delay:-{r.uniform(0, 5):.1f}s"/>'
        )
    return "".join(out)


def frame(w, h, rx=16, light=CYAN, dur=8):
    """Card background plus a light that travels around the border."""
    return (
        f'<rect x="1" y="1" width="{w-2}" height="{h-2}" rx="{rx}" fill="url(#bg)" '
        f'stroke="{LINE}" stroke-width="1.5"/>'
        f'<rect class="orbit" x="1" y="1" width="{w-2}" height="{h-2}" rx="{rx}" fill="none" '
        f'stroke="{light}" stroke-width="2" pathLength="100" stroke-dasharray="10 90" '
        f'stroke-linecap="round" filter="url(#softglow)" style="animation-duration:{dur}s"/>'
    )


def scanlines(w, h, rx=16):
    return (
        f'<pattern id="scan" width="4" height="4" patternUnits="userSpaceOnUse">'
        f'<rect width="4" height="1" fill="#fff" opacity=".025"/></pattern>'
        f'<linearGradient id="sweep" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{CYAN}" stop-opacity="0"/>'
        f'<stop offset=".5" stop-color="{CYAN}" stop-opacity=".07"/>'
        f'<stop offset="1" stop-color="{CYAN}" stop-opacity="0"/></linearGradient>',
        f'<rect x="1" y="1" width="{w-2}" height="{h-2}" rx="{rx}" fill="url(#scan)"/>'
        f'<rect class="sweep" x="2" y="-60" width="{w-4}" height="60" fill="url(#sweep)"/>',
        f".sweep{{animation:sweep 7s linear infinite}}"
        f"@keyframes sweep{{from{{transform:translateY(0)}}to{{transform:translateY({h+60}px)}}}}",
    )


# ── GitHub data ──────────────────────────────────────────────────────────────
QUERY = """
query($login:String!){ user(login:$login){
  pinnedItems(first:6, types:REPOSITORY){ nodes{ ... on Repository{
    name description url stargazerCount primaryLanguage{name color} } } }
  repositories(first:100, ownerAffiliations:OWNER, isFork:false, privacy:PUBLIC){
    totalCount nodes{ stargazerCount
      languages(first:10, orderBy:{field:SIZE,direction:DESC}){ edges{ size node{name color} } } } }
  contributionsCollection{ totalCommitContributions totalPullRequestContributions
    contributionCalendar{ totalContributions weeks{ contributionDays{ date contributionCount } } } }
} }"""


def fetch():
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN (or GH_TOKEN) is required")
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": CONFIG["username"]}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    if "errors" in payload:
        sys.exit(f"GraphQL error: {payload['errors']}")
    u = payload["data"]["user"]

    langs, colors = Counter(), {}
    for repo in u["repositories"]["nodes"]:
        for e in repo["languages"]["edges"]:
            name = e["node"]["name"]
            if name not in CONFIG["ignore_languages"]:
                langs[name] += e["size"]
                colors[name] = e["node"]["color"] or MUTED

    cc = u["contributionsCollection"]
    days = [d for w in cc["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
    return {
        "pinned": u["pinnedItems"]["nodes"],
        "repos": u["repositories"]["totalCount"],
        "stars": sum(r["stargazerCount"] for r in u["repositories"]["nodes"]),
        "langs": langs.most_common(),
        "lang_colors": colors,
        "commits": cc["totalCommitContributions"],
        "prs": cc["totalPullRequestContributions"],
        "total": cc["contributionCalendar"]["totalContributions"],
        "weeks": [sum(d["contributionCount"] for d in w["contributionDays"])
                  for w in cc["contributionCalendar"]["weeks"]],
        "week_starts": [w["contributionDays"][0]["date"] for w in cc["contributionCalendar"]["weeks"]],
        "days": [d["contributionCount"] for d in days],
    }


def longest_streak(days):
    best = cur = 0
    for c in days:
        cur = cur + 1 if c else 0
        best = max(best, cur)
    return best


# ── hero ─────────────────────────────────────────────────────────────────────
def hero():
    W, H = 900, 300
    r = rng_for("hero")
    body = [frame(W, H, light=VIOLET, dur=10)]
    body.append(f'<ellipse class="drift" cx="700" cy="140" rx="260" ry="150" fill="url(#nebV)"/>')
    body.append(f'<ellipse class="drift2" cx="200" cy="230" rx="260" ry="120" fill="url(#nebC)"/>')
    body.append(stars(r, W - 20, H - 20, 120, 10, 10))

    # shooting star
    body.append(
        f'<g class="shoot"><line x1="0" y1="0" x2="70" y2="22" stroke="url(#neon)" '
        f'stroke-width="1.6" stroke-linecap="round"/><circle cx="70" cy="22" r="1.8" fill="#fff"/></g>'
    )

    # neural network
    layers_x = [575, 665, 755, 845]
    counts = [4, 6, 6, 3]
    nodes = []
    for x, n in zip(layers_x, counts):
        gap = 36
        top = 150 - gap * (n - 1) / 2
        nodes.append([(x, top + i * gap) for i in range(n)])
    edges = []
    for a, b in zip(nodes, nodes[1:]):
        for p in a:
            for q in b:
                edges.append((p, q))
                body.append(
                    f'<line x1="{p[0]}" y1="{p[1]:.1f}" x2="{q[0]}" y2="{q[1]:.1f}" '
                    f'stroke="{CYAN}" stroke-opacity=".10" stroke-width="1"/>'
                )
    for p, q in r.sample(edges, 34):
        col = r.choice([CYAN, CYAN, VIOLET, PINK])
        body.append(
            f'<path class="pulse" d="M{p[0]} {p[1]:.1f}L{q[0]} {q[1]:.1f}" pathLength="100" '
            f'stroke="{col}" style="animation-duration:{r.uniform(1.4, 2.8):.1f}s;'
            f'animation-delay:-{r.uniform(0, 3):.1f}s"/>'
        )
    for li, layer in enumerate(nodes):
        for x, y in layer:
            col = [CYAN, VIOLET, VIOLET, PINK][li]
            body.append(
                f'<circle cx="{x}" cy="{y:.1f}" r="7" fill="{BG0}" stroke="{col}" '
                f'stroke-width="1.6" filter="url(#softglow)"/>'
                f'<circle class="fire" cx="{x}" cy="{y:.1f}" r="3" fill="{col}" '
                f'style="animation-delay:-{r.uniform(0, 2.4):.1f}s"/>'
            )
    for (x, y), label in zip(nodes[0], CONFIG["input_labels"]):
        body.append(f'<text class="mono" x="{x-16}" y="{y+4:.1f}" font-size="11" '
                    f'fill="{MUTED}" text-anchor="end">{esc(label)}</text>')
    for (x, y), label in zip(nodes[-1], CONFIG["output_labels"]):
        body.append(f'<text class="mono" x="{x+14}" y="{y+4:.1f}" font-size="11" '
                    f'fill="{PINK}" font-weight="700">{esc(label)}</text>')

    # text block
    body.append(f'<text class="mono" x="44" y="78" font-size="13" fill="{CYAN}" '
                f'opacity=".8">{esc(CONFIG["tagline"])}</text>')
    body.append(f'<text class="sans" x="42" y="140" font-size="52" font-weight="800" '
                f'letter-spacing="3" fill="url(#neon)" filter="url(#glow)">{esc(CONFIG["name"])}</text>')

    # typing carousel (SMIL so it works inside <img>)
    phrases = CONFIG["typing"]
    n, T = len(phrases), 4.2 * len(phrases)
    cw, x0, y0 = 10.4, 70, 186
    body.append(f'<text class="mono" x="44" y="{y0}" font-size="17" fill="{PINK}">&gt;</text>')
    defs = []
    for i, phrase in enumerate(phrases):
        w = len(phrase) * cw + 4
        a = i / n
        b, c, d = a + 0.40 / n, a + 0.85 / n, a + 0.97 / n
        if i == 0:
            vals, keys = f"0;{w};{w};0;0", f"0;{b:.4f};{c:.4f};{d:.4f};1"
        else:
            vals, keys = f"0;0;{w};{w};0;0", f"0;{a:.4f};{b:.4f};{c:.4f};{d:.4f};1"
        anim = (f'dur="{T}s" repeatCount="indefinite" values="{{v}}" keyTimes="{keys}"')
        defs.append(
            f'<clipPath id="type{i}"><rect x="{x0}" y="{y0-20}" height="28" width="0">'
            f'<animate attributeName="width" {anim.format(v=vals)}/></rect></clipPath>'
        )
        xs = ";".join(str(x0 + float(v)) for v in vals.split(";"))
        body.append(f'<text class="mono" x="{x0}" y="{y0}" font-size="17" fill="{TEXT}" '
                    f'clip-path="url(#type{i})">{esc(phrase)}</text>')
        body.append(f'<rect class="blink" x="{x0}" y="{y0-15}" width="9" height="19" fill="{CYAN}">'
                    f'<animate attributeName="x" {anim.format(v=xs)}/></rect>')

    # status pill
    status = CONFIG["status"]
    pw = 112 + len(status) * 7.3
    body.append(
        f'<rect x="44" y="222" width="{pw:.0f}" height="30" rx="15" fill="{BG0}" '
        f'stroke="{LINE}"/><circle class="blink" cx="62" cy="237" r="4.5" fill="{GREEN}" '
        f'filter="url(#softglow)" style="animation-duration:1.6s"/>'
        f'<text class="mono" x="74" y="241.5" font-size="12" fill="{GREEN}" '
        f'font-weight="700">ONLINE</text>'
        f'<text class="mono" x="130" y="241.5" font-size="12" fill="{MUTED}">│ {esc(status)}</text>'
    )

    sdefs, sbody, scss = scanlines(W, H)
    body.append(sbody)
    css = f"""
.pulse{{fill:none;stroke-width:2.4;stroke-linecap:round;stroke-dasharray:5 100;
  animation:pulse 2s linear infinite;filter:url(#softglow)}}
@keyframes pulse{{from{{stroke-dashoffset:5}}to{{stroke-dashoffset:-100}}}}
.fire{{animation:fire 2.4s ease-in-out infinite}}
@keyframes fire{{0%,100%{{opacity:.25}}45%{{opacity:1}}}}
.drift{{animation:drift 14s ease-in-out infinite alternate}}
.drift2{{animation:drift 18s ease-in-out infinite alternate-reverse}}
@keyframes drift{{from{{transform:translate(-20px,8px)}}to{{transform:translate(20px,-8px)}}}}
.shoot{{animation:shoot 9s ease-in infinite;opacity:0}}
@keyframes shoot{{0%,80%{{opacity:0;transform:translate(120px,-30px)}}
  83%{{opacity:1}}92%,100%{{opacity:0;transform:translate(520px,100px)}}}}
{scss}"""
    return svg(W, H, "".join(body), css, "".join(defs) + sdefs, "Yusuf Duman — AI/ML")


# ── terminal ─────────────────────────────────────────────────────────────────
def terminal(data):
    W, LH = 900, 25
    epochs = CONFIG["training"]
    fetch_rows = CONFIG["neofetch"] + [
        ("Commits", f"{data['commits']}  ·  PRs {data['prs']}  ·  Repos {data['repos']}  ·  ★ {data['stars']}   (son 1 yıl)"),
        ("Langs", "  ·  ".join(name for name, _ in data["langs"][:5])),
    ]
    H = 58 + LH * (len(epochs) + 3) + 26 + LH * (len(fetch_rows) + 3) + 18
    body = [frame(W, H, rx=14, light=CYAN, dur=9)]
    body.append(f'<path d="M1 44 V15 a14 14 0 0 1 14 -14 H{W-15} a14 14 0 0 1 14 14 V44 Z" fill="#0a0f1f"/>')
    body.append(f'<line x1="1" y1="44" x2="{W-1}" y2="44" stroke="{LINE}"/>')
    for i, c in enumerate(["#ff5f57", "#febc2e", "#28c840"]):
        body.append(f'<circle cx="{24+i*20}" cy="22" r="6" fill="{c}"/>')
    body.append(f'<text class="mono" x="{W/2}" y="27" font-size="12" fill="{MUTED}" '
                f'text-anchor="middle">yusuf@gazi-ceng: ~/neural-profile</text>')

    defs, t, y = [], 0.4, 76

    def prompt(cmd, y, start):
        w = len(cmd) * 8.45 + 4
        dur = max(0.6, len(cmd) * 0.035)
        cid = f"cmd{len(defs)}"
        defs.append(f'<clipPath id="{cid}"><rect x="46" y="{y-16}" height="22" width="0">'
                    f'<animate attributeName="width" from="0" to="{w}" begin="{start}s" '
                    f'dur="{dur:.2f}s" fill="freeze"/></rect></clipPath>')
        body.append(f'<text class="mono" x="26" y="{y}" font-size="14" fill="{PINK}">$</text>'
                    f'<text class="mono" x="46" y="{y}" font-size="14" fill="{TEXT}" '
                    f'clip-path="url(#{cid})">{esc(cmd)}</text>')
        return start + dur + 0.25

    def line(x, y, start, inner, size=14):
        body.append(f'<g class="fade" style="animation-delay:{start:.2f}s">'
                    f'<text class="mono" x="{x}" y="{y}" font-size="{size}">{inner}</text></g>')

    t = prompt(f"python train.py --model yusuf_duman --epochs {len(epochs)}", y, t)
    y += LH
    line(26, y, t, f'<tspan fill="{MUTED}">loading dataset: </tspan><tspan fill="{TEXT}">'
                   f'{data["total"]} contributions · {data["repos"]} repos</tspan>'
                   f'<tspan fill="{GREEN}">  ✓</tspan>')
    t += 0.35
    for i, ep in enumerate(epochs, 1):
        y += LH
        last = i == len(epochs)
        body.append(f'<g class="fade" style="animation-delay:{t:.2f}s">'
                    f'<text class="mono" x="26" y="{y}" font-size="14" fill="{TEXT}">'
                    f'Epoch {i}/{len(epochs)}</text>'
                    f'<rect x="132" y="{y-11}" width="150" height="10" rx="3" fill="{LINE}"/>'
                    f'<rect x="132" y="{y-11}" width="0" height="10" rx="3" fill="url(#neon)">'
                    f'<animate attributeName="width" from="0" to="{105 if last else 150}" '
                    f'begin="{t:.2f}s" dur="0.7s" fill="freeze"/></rect>'
                    + (f'<rect class="shimmer" x="132" y="{y-11}" width="105" height="10" rx="3" '
                       f'fill="#fff"/>' if last else "")
                    + f'<text class="mono" x="296" y="{y}" font-size="13" fill="{MUTED}">loss '
                    f'<tspan fill="{CYAN}">{ep["loss"]:.3f}</tspan> · acc '
                    f'<tspan fill="{CYAN}">{ep["acc"]:.2f}</tspan></text>'
                    f'<text class="mono" x="500" y="{y}" font-size="13" fill="{VIOLET}"># {esc(ep["note"])}</text>'
                    + (f'<text class="mono blink" x="{500 + (len(ep["note"]) + 2) * 7.9:.0f}" y="{y}" '
                       f'font-size="13" fill="{PINK}" style="animation-duration:1.4s"> ◀ training</text>'
                       if last else "")
                    + "</g>")
        t += 0.75
    y += LH
    line(26, y, t, f'<tspan fill="{GREEN}">✓ checkpoint saved</tspan><tspan fill="{MUTED}"> → </tspan>'
                   f'<tspan fill="{TEXT}">yusuf_duman.pt</tspan><tspan fill="{MUTED}">  (still learning…)</tspan>')
    t += 0.6

    # neofetch block
    y += LH + 26
    body.append(f'<line x1="26" y1="{y-30}" x2="{W-26}" y2="{y-30}" stroke="{LINE}" stroke-dasharray="3 5"/>')
    t = prompt("neofetch", y, t)
    top = y + 14
    cx, cy = 120, top + (len(fetch_rows) + 1) * LH / 2 + 4
    orb = [f'<g class="fade" style="animation-delay:{t:.2f}s">',
           f'<circle cx="{cx}" cy="{cy}" r="58" fill="url(#nebV)"/>']
    for k, (rx, ry, ang, dur, col) in enumerate([(70, 22, 0, 9, CYAN), (70, 22, 60, 12, VIOLET),
                                                 (70, 22, 120, 15, PINK)]):
        orb.append(f'<g transform="rotate({ang} {cx} {cy})"><ellipse cx="{cx}" cy="{cy}" rx="{rx}" '
                   f'ry="{ry}" fill="none" stroke="{col}" stroke-opacity=".45"/>'
                   f'<circle r="3.5" fill="{col}" filter="url(#softglow)">'
                   f'<animateMotion dur="{dur}s" repeatCount="indefinite" '
                   f'path="M{cx-rx} {cy} a{rx} {ry} 0 1 0 {2*rx} 0 a{rx} {ry} 0 1 0 -{2*rx} 0"/>'
                   f'</circle></g>')
    orb.append(f'<circle class="fire" cx="{cx}" cy="{cy}" r="13" fill="url(#neon)" filter="url(#glow)"/>'
               f'<text class="mono" x="{cx}" y="{cy+4}" font-size="11" font-weight="800" fill="{BG0}" '
               f'text-anchor="middle">AI</text></g>')
    body.append("".join(orb))

    kx, vx = 236, 336
    yy = top + 8
    line(kx, yy, t, f'<tspan fill="{CYAN}" font-weight="700">yusuf</tspan><tspan fill="{MUTED}">@</tspan>'
                    f'<tspan fill="{CYAN}" font-weight="700">gazi-ceng</tspan>')
    yy += 14
    body.append(f'<line class="fade" style="animation-delay:{t:.2f}s" x1="{kx}" y1="{yy-2}" '
                f'x2="{kx+170}" y2="{yy-2}" stroke="{DIM}"/>')
    for k, v in fetch_rows:
        yy += LH - 2
        t += 0.12
        line(kx, yy, t, f'<tspan fill="{VIOLET}" font-weight="700">{esc(k)}</tspan>', 13.5)
        line(vx, yy, t, f'<tspan fill="{TEXT}">{esc(v)}</tspan>', 13.5)
    yy += 18
    t += 0.12
    sw = "".join(f'<rect x="{kx + i*26}" y="{yy}" width="22" height="12" rx="2" fill="{c}"/>'
                 for i, c in enumerate([BG0, "#1e3a8a", CYAN, VIOLET, PINK, "#fb923c", GREEN, TEXT]))
    body.append(f'<g class="fade" style="animation-delay:{t:.2f}s">{sw}</g>')
    body.append(f'<rect class="blink" x="46" y="{H-30}" width="9" height="17" fill="{CYAN}"/>'
                f'<text class="mono" x="26" y="{H-17}" font-size="14" fill="{PINK}">$</text>')

    sdefs, sbody, scss = scanlines(W, H, 14)
    body.append(sbody)
    css = f"""
.fire{{animation:fire 2.4s ease-in-out infinite}}
@keyframes fire{{0%,100%{{opacity:.55}}50%{{opacity:1}}}}
.shimmer{{opacity:0;animation:shim 1.6s ease-in-out infinite}}
@keyframes shim{{50%{{opacity:.25}}}}
{scss}"""
    return svg(W, H, "".join(body), css, "".join(defs) + sdefs, "Terminal: training yusuf_duman")


# ── section titles ───────────────────────────────────────────────────────────
def title(text, sub, color=CYAN):
    W, H = 900, 56
    tw = len(text) * 16.2
    sx = 52 + tw + 18
    lx = sx + len(sub) * 7.6 + 20
    body = (
        f'<g transform="translate(24 28) rotate(45)"><rect class="spin" x="-8" y="-8" width="16" '
        f'height="16" fill="none" stroke="{color}" stroke-width="2" filter="url(#softglow)"/>'
        f'<rect x="-3" y="-3" width="6" height="6" fill="{color}"/></g>'
        f'<text class="mono" x="52" y="36" font-size="22" font-weight="800" letter-spacing="4" '
        f'fill="{color}" filter="url(#softglow)">{esc(text)}</text>'
        f'<text class="mono" x="{sx:.0f}" y="35" font-size="13" fill="{MUTED}">{esc(sub)}</text>'
        f'<line x1="{lx:.0f}" y1="30" x2="{W-10}" y2="30" stroke="{LINE}" stroke-width="1.5"/>'
        f'<circle r="3" cy="30" fill="{color}" filter="url(#glow)">'
        f'<animate attributeName="cx" values="{lx:.0f};{W-10};{lx:.0f}" dur="6s" repeatCount="indefinite"/>'
        f'<animate attributeName="opacity" values="0;1;1;0" dur="3s" repeatCount="indefinite"/></circle>'
    )
    css = (".spin{animation:spin 8s linear infinite;transform-box:fill-box;transform-origin:center}"
           "@keyframes spin{to{transform:rotate(360deg)}}")
    return svg(W, H, body, css, label=text)


# ── project cards ────────────────────────────────────────────────────────────
def card(repo, idx, total):
    W, H = 440, 200
    name = repo["name"]
    cfg = CONFIG["projects"].get(name, {})
    desc = cfg.get("desc") or repo.get("description") or "—"
    tags = cfg.get("tags", [])
    lang = repo.get("primaryLanguage") or {"name": "—", "color": MUTED}
    lc = lang["color"] or MUTED
    r = rng_for(name)

    body = [frame(W, H, rx=14, light=lc, dur=r.uniform(6, 10))]
    body.append(f'<ellipse cx="370" cy="40" rx="140" ry="90" fill="url(#nebV)" opacity=".7"/>')
    body.append(stars(r, W - 20, H - 20, 26, 10, 10))

    # constellation
    pts = [(r.uniform(318, 420), r.uniform(22, 92)) for _ in range(6)]
    pts.sort()
    path = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f} {y:.1f}" for i, (x, y) in enumerate(pts))
    body.append(f'<path class="draw" d="{path}" pathLength="100" fill="none" stroke="{lc}" '
                f'stroke-opacity=".7" stroke-width="1.2"/>')
    for i, (x, y) in enumerate(pts):
        body.append(f'<circle class="tw" cx="{x:.1f}" cy="{y:.1f}" r="{2.6 if i % 2 else 1.8}" '
                    f'fill="#fff" filter="url(#softglow)" style="animation-delay:-{r.uniform(0, 3):.1f}s"/>')

    body.append(f'<text class="mono" x="24" y="34" font-size="11" fill="{MUTED}" letter-spacing="2">'
                f'{idx:02d} / {total:02d}  ·  REPO</text>')
    fs = min(22, 285 / (len(name) * 0.6))
    body.append(f'<text class="sans" x="24" y="66" font-size="{fs:.1f}" font-weight="800" fill="{TEXT}">'
                f'{esc(name)}</text>')
    for i, ln in enumerate(textwrap.wrap(desc, 56)[:3]):
        body.append(f'<text class="sans" x="24" y="{96 + i*19}" font-size="13.2" fill="#aab6cc">{esc(ln)}</text>')

    # footer: language, tags, stars
    fy = 172
    body.append(f'<line x1="24" y1="148" x2="{W-24}" y2="148" stroke="{LINE}"/>')
    body.append(f'<circle cx="30" cy="{fy-4}" r="5" fill="{lc}" filter="url(#softglow)"/>'
                f'<text class="mono" x="42" y="{fy}" font-size="12" fill="{TEXT}">{esc(lang["name"])}</text>')
    x = 50 + len(lang["name"]) * 7.3 + 10
    for tag in tags:
        tw_ = len(tag) * 6.7 + 16
        if x + tw_ > W - 70:
            break
        body.append(f'<rect x="{x:.0f}" y="{fy-15}" width="{tw_:.0f}" height="21" rx="10.5" '
                    f'fill="{lc}" fill-opacity=".12" stroke="{lc}" stroke-opacity=".5"/>'
                    f'<text class="mono" x="{x + tw_/2:.0f}" y="{fy-1}" font-size="11" fill="{TEXT}" '
                    f'text-anchor="middle">{esc(tag)}</text>')
        x += tw_ + 6
    body.append(f'<text class="mono" x="{W-24}" y="{fy}" font-size="13" fill="#fbbf24" '
                f'text-anchor="end">★ {repo["stargazerCount"]}</text>')
    css = (".draw{stroke-dasharray:100;stroke-dashoffset:100;animation:draw 2.2s ease-out .3s forwards}"
           "@keyframes draw{to{stroke-dashoffset:0}}")
    return svg(W, H, "".join(body), css, label=name)


# ── signal: contributions light curve + language spectrum ────────────────────
def smooth(points):
    d = f"M{points[0][0]:.1f} {points[0][1]:.1f}"
    for i in range(len(points) - 1):
        p0 = points[max(i - 1, 0)]
        p1, p2 = points[i], points[i + 1]
        p3 = points[min(i + 2, len(points) - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d += f" C{c1[0]:.1f} {c1[1]:.1f} {c2[0]:.1f} {c2[1]:.1f} {p2[0]:.1f} {p2[1]:.1f}"
    return d


def signal(data):
    W, H = 900, 330
    r = rng_for("signal")
    body = [frame(W, H, light=PINK, dur=11), stars(r, W - 20, H - 20, 60, 10, 10)]
    body.append(f'<text class="mono" x="32" y="42" font-size="13" fill="{MUTED}">'
                f'// light curve — haftalık katkılar, son 12 ay</text>')
    body.append(f'<text class="sans" x="{W-32}" y="46" font-size="30" font-weight="800" '
                f'fill="url(#neon)" text-anchor="end" filter="url(#softglow)">{data["total"]}</text>')
    body.append(f'<text class="mono" x="{W-32}" y="64" font-size="11.5" fill="{MUTED}" text-anchor="end">'
                f'katkı · en uzun seri {longest_streak(data["days"])} gün</text>')

    x0, x1, y0, y1 = 40, W - 40, 100, 214
    weeks = data["weeks"]
    peak = max(max(weeks), 1)
    pts = [(x0 + (x1 - x0) * i / (len(weeks) - 1), y1 - (y1 - y0) * (v / peak) ** 0.75)
           for i, v in enumerate(weeks)]
    for gy in (y0, (y0 + y1) / 2, y1):
        body.append(f'<line x1="{x0}" y1="{gy}" x2="{x1}" y2="{gy}" stroke="{LINE}" stroke-dasharray="2 6"/>')
    d = smooth(pts)
    body.append(f'<path class="area" d="{d} L{x1} {y1} L{x0} {y1} Z" fill="url(#areaG)"/>')
    body.append(f'<path class="draw" d="{d}" pathLength="100" fill="none" stroke="url(#neon)" '
                f'stroke-width="2.5" filter="url(#softglow)"/>')
    for i in sorted(range(len(weeks)), key=lambda i: -weeks[i])[:4]:
        if not weeks[i]:
            continue
        x, y = pts[i]
        body.append(f'<g class="fade" style="animation-delay:2.4s">'
                    f'<circle class="tw" cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#fff" filter="url(#glow)"/>'
                    f'<text class="mono" x="{x:.1f}" y="{y-11:.1f}" font-size="10.5" fill="{TEXT}" '
                    f'text-anchor="middle">{weeks[i]}</text></g>')
    months = "Oca Şub Mar Nis May Haz Tem Ağu Eyl Eki Kas Ara".split()
    last = None
    for i, ws in enumerate(data["week_starts"]):
        m = int(ws[5:7])
        if m != last and i < len(weeks) - 2:
            body.append(f'<text class="mono" x="{pts[i][0]:.1f}" y="{y1+18}" font-size="10.5" '
                        f'fill="{DIM}">{months[m-1]}</text>')
            last = m

    # language spectrum
    sy = 262
    body.append(f'<text class="mono" x="32" y="{sy-12}" font-size="11.5" fill="{MUTED}">'
                f'// spectrum — dil dağılımı (bayt)</text>')
    total = sum(s for _, s in data["langs"]) or 1
    langs = [(n, s) for n, s in data["langs"][:6] if s / total >= 0.01]
    total = sum(s for _, s in langs) or 1
    x = 32
    span = W - 64
    legend_x = 32
    for i, (name, size) in enumerate(langs):
        w = span * size / total
        col = data["lang_colors"].get(name, MUTED)
        body.append(f'<rect x="{x:.1f}" y="{sy}" width="0" height="10" fill="{col}">'
                    f'<animate attributeName="width" from="0" to="{max(w-2, 1):.1f}" '
                    f'begin="{0.4 + i*0.15:.2f}s" dur="0.6s" fill="freeze"/></rect>')
        pct = 100 * size / total
        label = f"{name} {pct:.1f}%"
        body.append(f'<circle cx="{legend_x+5}" cy="{sy+31}" r="4.5" fill="{col}"/>'
                    f'<text class="mono" x="{legend_x+15}" y="{sy+35}" font-size="11.5" fill="{TEXT}">'
                    f'{esc(label)}</text>')
        legend_x += 15 + len(label) * 7 + 22
        x += w
    defs = (f'<linearGradient id="areaG" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="{VIOLET}" stop-opacity=".35"/>'
            f'<stop offset="1" stop-color="{CYAN}" stop-opacity="0"/></linearGradient>')
    css = (".draw{stroke-dasharray:100;stroke-dashoffset:100;animation:draw 2.4s ease-out forwards}"
           "@keyframes draw{to{stroke-dashoffset:0}}"
           ".area{opacity:0;animation:fade 1s ease-out 1.8s forwards}")
    return svg(W, H, "".join(body), css, defs, "Contribution light curve")


# ── footer ───────────────────────────────────────────────────────────────────
def footer():
    W, H = 900, 90
    r = rng_for("footer")
    pts = [(10 + i * 8, 45 + 14 * math.sin(i / 5.0) * math.sin(i / 17.0)) for i in range(111)]
    wave = smooth(pts)
    body = (stars(r, W, H, 40)
            + f'<path class="wave" d="{wave}" pathLength="100" fill="none" stroke="url(#neon)" '
              f'stroke-width="1.6" stroke-opacity=".8"/>'
            + f'<rect x="{W/2-215}" y="30" width="430" height="30" rx="15" fill="{BG0}" stroke="{LINE}"/>'
            + f'<text class="mono" x="{W/2}" y="50" font-size="12.5" fill="{MUTED}" text-anchor="middle">'
              f'end of transmission · <tspan fill="{PINK}">★</tspan> beğendiysen yıldız bırak</text>')
    css = (".wave{stroke-dasharray:30 70;animation:wave 6s linear infinite}"
           "@keyframes wave{from{stroke-dashoffset:100}to{stroke-dashoffset:0}}")
    return svg(W, H, body, css, label="footer")


def main():
    data = fetch()
    (ASSETS / "projects").mkdir(parents=True, exist_ok=True)
    out = {
        "hero.svg": hero(),
        "terminal.svg": terminal(data),
        "signal.svg": signal(data),
        "footer.svg": footer(),
        "title-projects.svg": title("PROJECTS", "// sabitlenmiş projeler", CYAN),
        "title-stack.svg": title("TECH STACK", "// kullandığım araçlar", VIOLET),
        "title-signal.svg": title("SIGNAL", "// katkı aktivitesi", PINK),
    }
    pinned = data["pinned"]
    for old in (ASSETS / "projects").glob("*.svg"):
        old.unlink()
    for i, repo in enumerate(pinned, 1):
        out[f"projects/{repo['name']}.svg"] = card(repo, i, len(pinned))
    for path, content in out.items():
        (ASSETS / path).write_text(content, encoding="utf-8")

    # project grid in README, between markers
    cells = [f'<a href="{repo["url"]}"><img src="assets/projects/{repo["name"]}.svg" '
             f'width="49%" alt="{esc(repo["name"])}"/></a>' for repo in pinned]
    grid = "\n".join(" ".join(cells[i:i + 2]) + "<br/>" for i in range(0, len(cells), 2))
    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    start, end = "<!-- projects:start -->", "<!-- projects:end -->"
    if start in text and end in text:
        head, rest = text.split(start, 1)
        _, tail = rest.split(end, 1)
        readme.write_text(f"{head}{start}\n<p align=\"center\">\n{grid}\n</p>\n{end}{tail}", encoding="utf-8")
    print(f"wrote {len(out)} svgs at {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC")


if __name__ == "__main__":
    main()
