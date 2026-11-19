"""Render a month-to-date card from the public GitHub contribution calendar."""

import argparse
from datetime import date, datetime, timedelta
from html import escape
from html.parser import HTMLParser
from math import ceil
from pathlib import Path
import re
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


class ContributionCalendar(HTMLParser):
    def __init__(self):
        super().__init__()
        self.days = {}
        self.labels = {}
        self.label = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "td" and "data-date" in attributes and "id" in attributes:
            self.days[attributes["data-date"]] = attributes["id"]
        elif tag == "tool-tip" and "for" in attributes:
            self.label = attributes["for"]
            self.labels[self.label] = ""

    def handle_data(self, data):
        if self.label is not None:
            self.labels[self.label] += data

    def handle_endtag(self, tag):
        if tag == "tool-tip":
            self.label = None

    def count(self, day):
        label = self.labels.get(self.days.get(day.isoformat()), "").strip()
        match = re.match(r"(No|[0-9,]+) contributions? on\b", label)
        if not match:
            raise ValueError(f"GitHub did not return a contribution count for {day}.")
        value = match.group(1)
        return 0 if value == "No" else int(value.replace(",", ""))


def fetch_counts(profile, end):
    start = end.replace(day=1)
    query = urlencode({"from": start.isoformat(), "to": end.isoformat()})
    url = f"https://github.com/users/{quote(profile, safe='')}/contributions?{query}"
    request = Request(url, headers={"User-Agent": "GitHub profile activity card"})
    with urlopen(request, timeout=20) as response:
        calendar = ContributionCalendar()
        calendar.feed(response.read().decode("utf-8"))
    return [calendar.count(start + timedelta(days=index)) for index in range(end.day)]


def render(end, counts):
    width, height = 840, 204
    left, right, top, bottom = 46, 552, 69, 158
    peak = max(counts)
    tick = max(1, ceil(peak / 3))
    ceiling = tick * 3
    points = [
        (left + (right - left) * i / max(1, len(counts) - 1),
         bottom - count * (bottom - top) / ceiling)
        for i, count in enumerate(counts)
    ]
    line = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
    total = sum(counts)
    active_days = sum(count > 0 for count in counts)
    month = end.strftime("%B %Y")
    description = (
        f"GitHub contributions for {month}, days 1 to {end.day}. "
        f"Daily counts: {', '.join(map(str, counts))}. "
        f"{total} contributions across {active_days} active days."
    )
    svg = [f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-labelledby="title description">
  <title id="title">GitHub contributions for {month}</title>
  <desc id="description">{escape(description)}</desc>
  <style>
    text {{ font-family: ui-monospace, Consolas, 'Liberation Mono', monospace; fill: #24374d }}
    .panel {{ fill: #f6f8fa; stroke: #c9d4e1 }}
    .stat-panel {{ fill: #edf2f8 }}
    .muted {{ fill: #49617a }}
    .grid {{ stroke: #ced9e5 }}
    .line {{ stroke: #356ba6; fill: none }}
    .point {{ fill: #356ba6 }}
    @media (prefers-color-scheme: dark) {{
      text {{ fill: #d5e5fa }}
      .panel {{ fill: #151b23; stroke: #414b5b }}
      .stat-panel {{ fill: #1c2632 }}
      .muted {{ fill: #a1b4ce }}
      .grid {{ stroke: #354456 }}
      .line {{ stroke: #85baf0 }}
      .point {{ fill: #85baf0 }}
    }}
  </style>
  <rect class="panel" x=".5" y=".5" width="839" height="203" rx="6"/>
  <rect class="stat-panel" x="578" y="20" width="242" height="164" rx="6"/>
  <text x="22" y="30" font-size="15" font-weight="700">GitHub activity</text>
  <text class="muted" x="22" y="50" font-size="12">{month} / daily contributions</text>
  <text x="596" y="47" font-size="14" font-weight="700">Month to date</text>"""]
    for i in range(4):
        y = bottom - i * (bottom - top) / 3
        svg.append(f'  <path class="grid" d="M{left} {y:.2f}H{right}"/>')
        svg.append(f'  <text class="muted" x="{left - 8}" y="{y + 4:.2f}" font-size="11" text-anchor="end">{i * tick}</text>')
    svg.append(f'  <polyline class="line" points="{line}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>')
    x, y = points[-1]
    svg.append(f'  <circle class="point" cx="{x:.2f}" cy="{y:.2f}" r="3.5"/>')
    for day in sorted({1, (end.day + 1) // 2, end.day}):
        x, _ = points[day - 1]
        anchor = "start" if day == 1 else "end" if day == end.day else "middle"
        svg.append(f'  <text class="muted" x="{x:.2f}" y="179" font-size="11" text-anchor="{anchor}">{end.strftime("%b")} {day}</text>')
    stats = (
        ("Contributions", total),
        ("Active days", f"{active_days} / {end.day}"),
        ("Peak day", peak),
        ("Today", counts[-1]),
    )
    for i, (label, value) in enumerate(stats):
        y = 73 + i * 27
        svg.append(f'  <text class="muted" x="596" y="{y}" font-size="13">{label}</text>')
        svg.append(f'  <text x="802" y="{y}" font-size="13" font-weight="700" text-anchor="end">{value}</text>')
    return "\n".join([*svg, "</svg>", ""])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="miilxxwizi")
    parser.add_argument("--date", type=date.fromisoformat)
    parser.add_argument("--output", type=Path, default=Path("assets/activity.svg"))
    args = parser.parse_args()
    end = args.date or datetime.now(ZoneInfo("Asia/Qyzylorda")).date()
    counts = fetch_counts(args.profile, end)
    args.output.write_text(render(end, counts), encoding="utf-8", newline="\n")
    print(f"{end:%Y-%m}: {sum(counts)} contributions over {len(counts)} calendar days.")


if __name__ == "__main__":
    main()
