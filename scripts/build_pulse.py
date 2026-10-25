#!/usr/bin/env python3
"""Render assets/pulse.svg — an animated contribution heatmap with live stats.

Data source (in order):
  1. GitHub GraphQL API, when GITHUB_TOKEN is set (used by the daily workflow).
  2. The public contributions page  github.com/users/<user>/contributions.
  3. A local HTML file passed with --html (for offline testing).

Standard library only, so the workflow needs no pip install.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

USER = os.environ.get("PROFILE_USER", "caraxesmsc")

# ---------------------------------------------------------------- data


def from_graphql(user: str, token: str) -> list[tuple[dt.date, int]]:
    query = """
    query($login:String!){ user(login:$login){ contributionsCollection{
      contributionCalendar{ weeks{ contributionDays{ date contributionCount }}}}}}"""
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": {"login": user}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)
    weeks = payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    return [
        (dt.date.fromisoformat(d["date"]), d["contributionCount"])
        for w in weeks
        for d in w["contributionDays"]
    ]


def from_html(html: str) -> list[tuple[dt.date, int]]:
    cells = dict(re.findall(r'data-date="([\d-]+)"\s+id="(contribution-day-component-[\d-]+)"', html))
    by_id = {v: k for k, v in cells.items()}
    tips = re.findall(r'for="(contribution-day-component-[\d-]+)"[^>]*>([^<]*)<', html)
    days = []
    for cid, text in tips:
        if cid not in by_id:
            continue
        m = re.match(r"\s*(\d[\d,]*|No) contribution", text)
        n = 0 if (not m or m.group(1) == "No") else int(m.group(1).replace(",", ""))
        days.append((dt.date.fromisoformat(by_id[cid]), n))
    if not days:
        raise ValueError("no contribution cells found in HTML")
    return sorted(days)


def load(args) -> list[tuple[dt.date, int]]:
    if args.html:
        return from_html(Path(args.html).read_text(encoding="utf-8"))
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        try:
            return from_graphql(USER, token)
        except Exception as e:  # fall through to scraping
            print(f"GraphQL failed ({e}); falling back to HTML", file=sys.stderr)
    url = f"https://github.com/users/{USER}/contributions"
    with urllib.request.urlopen(url, timeout=30) as r:
        return from_html(r.read().decode("utf-8"))


# ---------------------------------------------------------------- stats


def stats(days):
    counts = [c for _, c in days]
    total = sum(counts)
    active = sum(1 for c in counts if c)
    longest = run = 0
    for c in counts:
        run = run + 1 if c else 0
        longest = max(longest, run)
    # current streak: allow today to be empty (day not over yet)
    cur = 0
    seq = counts[:-1] if counts and counts[-1] == 0 else counts
    for c in reversed(seq):
        if not c:
            break
        cur += 1
    best_day, best = max(days, key=lambda d: d[1])
    # busiest 7-day window
    week_best = max((sum(counts[i : i + 7]) for i in range(max(1, len(counts) - 6))), default=0)
    return dict(total=total, active=active, longest=longest, current=cur,
                best=best, best_day=best_day, week_best=week_best, n=len(days))


# ---------------------------------------------------------------- render

BG = "#0b0f14"
LINE = "#232a33"
INK = "#e8edf2"
MUTE = "#7d8794"
EMBER = ["#1a2029", "#4a1f17", "#8a2f1c", "#d24a22", "#ff8a4c"]  # level 0..4
MONO = "'JetBrains Mono','SFMono-Regular',Menlo,Consolas,'Liberation Mono',monospace"
SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI','Helvetica Neue',Arial,sans-serif"


def days_label(n):
    return f"{n} day" if n == 1 else f"{n} days"


def level(c, q):
    if c == 0:
        return 0
    for i, t in enumerate(q, start=1):
        if c <= t:
            return i
    return 4


def odometer(x, y, text, size, color, delay0):
    """Rolling digits. Static state = final value (safe for reduced motion)."""
    h = size * 1.15
    w = size * 0.62
    out = [f'<g transform="translate({x},{y})">']
    cx = 0
    k = 0
    for ch in text:
        if ch.isdigit():
            d = int(ch)
            strip = "".join(
                f'<text x="0" y="{(i + 1) * h - h * 0.22:.1f}">{i % 10}</text>' for i in range(10 + d + 1)
            )
            final = -(10 + d) * h
            out.append(
                f'<svg x="{cx:.1f}" y="0" width="{w:.1f}" height="{h:.1f}" overflow="hidden">'
                f'<g class="roll" style="transform:translateY({final:.1f}px);'
                f'animation-delay:{delay0 + k * 0.12:.2f}s">{strip}</g></svg>'
            )
            k += 1
            cx += w
        else:
            out.append(f'<text x="{cx - w * 0.22:.1f}" y="{h - h * 0.22:.1f}">{ch}</text>')
            cx += w * 0.42
    out.append("</g>")
    return (
        f'<g font-family="{MONO}" font-size="{size}" font-weight="700" fill="{color}">'
        + "".join(out)
        + "</g>",
        cx,
    )


def render(days) -> str:
    s = stats(days)
    W, H = 880, 312
    cell, gap = 11, 3
    step = cell + gap
    # align columns to weeks (Sunday-first like GitHub)
    first = days[0][0]
    offset = (first.weekday() + 1) % 7
    nz = sorted(c for _, c in days if c)
    q = [nz[int(len(nz) * f)] for f in (0.25, 0.5, 0.8)] + [10**9] if nz else [1, 2, 3, 10**9]
    gx, gy = 40, 118
    cols = (len(days) + offset + 6) // 7

    rects = []
    for i, (d, c) in enumerate(days):
        col, row = divmod(i + offset, 7)
        delay = 0.35 + col * 0.028 + row * 0.01
        rects.append(
            f'<rect class="c l{level(c, q)}" x="{gx + col * step}" y="{gy + row * step}" width="{cell}" height="{cell}" '
            f'rx="2.5" style="animation-delay:{delay:.3f}s"><title>{d.isoformat()}: {c}</title></rect>'
        )

    months = []
    last_col = -9
    for i, (d, _) in enumerate(days):
        if d.day == 1:
            col = (i + offset) // 7
            if col - last_col < 3 or col > cols - 2:
                continue
            last_col = col
            months.append(f'<text x="{gx + col * step}" y="{gy - 10}" class="mo">{d.strftime("%b")}</text>')

    grid_w = cols * step - gap
    scan_x0, scan_x1 = gx - 30, gx + grid_w + 10

    bi = next(i for i, (d, _) in enumerate(days) if d == s["best_day"]) + offset
    pc, pr = divmod(bi, 7)
    px, py = gx + pc * step + cell / 2, gy + pr * step + cell / 2

    total_svg, tw = odometer(40, 34, f"{s['total']:,}", 40, INK, 0.2)

    stat_items = [
        ("LONGEST STREAK", days_label(s['longest'])),
        ("CURRENT STREAK", days_label(s['current'])),
        ("ACTIVE DAYS", f"{s['active']} / {s['n']}"),
        ("BUSIEST WEEK", f"{s['week_best']:,}"),
        ("PEAK DAY", f"{s['best']} · {s['best_day'].strftime('%b %d')}"),
    ]
    colw = (W - 80) / len(stat_items)
    stat_svg = [
        f'<g class="st" style="animation-delay:{2.0 + j * 0.12:.2f}s">'
        f'<text x="{40 + j * colw:.0f}" y="268" class="k">{k}</text>'
        f'<text x="{40 + j * colw:.0f}" y="290" class="v">{v}</text></g>'
        for j, (k, v) in enumerate(stat_items)
    ]

    from zoneinfo import ZoneInfo  # stamp the date in local time, not the runner's UTC
    updated = dt.datetime.now(ZoneInfo(os.environ.get("PROFILE_TZ", "Africa/Cairo"))).strftime("%d %b %Y")
    live = f"LIVE · {updated.upper()}"
    dot_x = W - 40 - len(live) * 7.4 - 10
    lg = W - 72  # legend anchor
    ly = gy + 7 * step + 7

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-labelledby="t d">
<title id="t">{s['total']:,} contributions in the last year</title>
<desc id="d">Animated contribution heatmap for {USER}. Longest streak {s['longest']} days, current streak {s['current']} days, {s['active']} active days of {s['n']}. Updated {updated}.</desc>
<style>
  .c{{animation:pop .5s cubic-bezier(.2,.9,.3,1.4) backwards;transform-box:fill-box;transform-origin:center}}
  .l0{{fill:{EMBER[0]}}} .l1{{fill:{EMBER[1]}}} .l2{{fill:{EMBER[2]}}} .l3{{fill:{EMBER[3]}}} .l4{{fill:{EMBER[4]}}}
  @keyframes pop{{from{{opacity:0;transform:scale(.2)}}}}
  .roll{{animation:roll 1.6s cubic-bezier(.15,.8,.2,1) backwards}}
  @keyframes roll{{from{{transform:translateY(0)}}}}
  .mo{{font:500 10px {MONO};fill:{MUTE};letter-spacing:.06em}}
  .k{{font:600 9.5px {MONO};fill:{MUTE};letter-spacing:.14em}}
  .v{{font:600 15px {SANS};fill:{INK}}}
  .st{{animation:rise .6s ease-out backwards}}
  @keyframes rise{{from{{opacity:0;transform:translateY(6px)}}}}
  .scan{{animation:scan 3.2s 1.1s cubic-bezier(.45,0,.2,1) both}}
  @keyframes scan{{from{{transform:translateX(0);opacity:0}}8%{{opacity:1}}92%{{opacity:1}}to{{transform:translateX({scan_x1 - scan_x0}px);opacity:0}}}}
  .ring{{fill:none;stroke:{EMBER[4]};stroke-width:1.5;transform-box:fill-box;transform-origin:center;animation:ring 2.4s 3s ease-out infinite}}
  @keyframes ring{{0%{{transform:scale(.4);opacity:.9}}100%{{transform:scale(2.6);opacity:0}}}}
  .live{{animation:blink 1.6s steps(2,start) infinite}}
  @keyframes blink{{to{{visibility:hidden}}}}
  @media (prefers-reduced-motion:reduce){{*{{animation:none!important}}.scan{{display:none}}}}
</style>
<defs>
  <linearGradient id="sg" x1="0" x2="1"><stop offset="0" stop-color="{EMBER[4]}" stop-opacity="0"/><stop offset=".85" stop-color="{EMBER[4]}" stop-opacity=".22"/><stop offset="1" stop-color="{EMBER[4]}" stop-opacity=".9"/></linearGradient>
  <clipPath id="gc"><rect x="{gx - 4}" y="{gy - 4}" width="{grid_w + 8}" height="{7 * step + 4}"/></clipPath>
</defs>
<rect width="{W}" height="{H}" rx="14" fill="{BG}"/>
<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="13.5" fill="none" stroke="{LINE}"/>
{total_svg}
<text x="{40 + tw + 14:.0f}" y="68" font-family="{SANS}" font-size="15" fill="{MUTE}">contributions in the last year</text>
<g font-family="{MONO}" font-size="10" fill="{MUTE}" letter-spacing=".14em">
  <circle cx="{dot_x:.0f}" cy="44.5" r="3.5" fill="{EMBER[4]}" class="live"/>
  <text x="{W - 40}" y="48" text-anchor="end">{live}</text>
</g>
{''.join(months)}
<g>{''.join(rects)}</g>
<g clip-path="url(#gc)"><rect class="scan" x="{scan_x0}" y="{gy - 4}" width="30" height="{7 * step + 4}" fill="url(#sg)"/></g>
<circle class="ring" cx="{px}" cy="{py}" r="7"/>
<line x1="40" x2="{W - 40}" y1="246" y2="246" stroke="{LINE}"/>
{''.join(stat_svg)}
<g font-family="{MONO}" font-size="9" fill="{MUTE}">
  <text x="{lg - 5 * 14 - 6}" y="{ly + 9}" text-anchor="end">less</text>
  {''.join(f'<rect x="{lg - (5 - i) * 14}" y="{ly}" width="11" height="11" rx="2.5" fill="{EMBER[i]}"/>' for i in range(5))}
  <text x="{lg + 4}" y="{ly + 9}">more</text>
</g>
</svg>
"""


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", help="read contributions from a saved HTML page")
    ap.add_argument("--out", default="assets/pulse.svg")
    args = ap.parse_args()
    days = load(args)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(render(days), encoding="utf-8")
    s = stats(days)
    print(f"wrote {args.out}: {s['total']} contributions, longest streak {s['longest']}, current {s['current']}")
