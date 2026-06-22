#!/usr/bin/env python3
"""devdash - an ASCII developer-profile dashboard for your terminal.

Pulls public profile stats from multiple coding platforms and renders them as
tidy ASCII widgets with switchable color themes. Pure Python 3, standard
library only - no pip install required.

Supported providers:
  - GitHub      (--github USER)
  - GitLab      (--gitlab USER)
  - Codeforces  (--codeforces HANDLE)

Examples:
  python3 devdash.py --github torvalds
  python3 devdash.py --github wetair1 --gitlab gitlab-org --theme matrix
  python3 devdash.py --github octocat --json

GitHub allows ~60 unauthenticated requests/hour per IP. Set GITHUB_TOKEN in
your environment to raise the limit (the token is only used for the API call).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timezone

__version__ = "0.2.0"
USER_AGENT = "devdash/" + __version__ + " (+https://github.com/wetair1/devdash)"

API_GITHUB = "https://api.github.com"
API_GITLAB = "https://gitlab.com/api/v4"
API_CODEFORCES = "https://codeforces.com/api"


# --------------------------------------------------------------------------- #
# Themes & colors
# --------------------------------------------------------------------------- #
THEMES = {
    "arch":   {"border": "\033[38;5;33m",  "title": "\033[1;38;5;39m",  "accent": "\033[38;5;51m",  "text": "\033[38;5;253m", "dim": "\033[38;5;245m"},
    "matrix": {"border": "\033[38;5;28m",  "title": "\033[1;38;5;46m",  "accent": "\033[38;5;82m",  "text": "\033[38;5;40m",  "dim": "\033[38;5;28m"},
    "amber":  {"border": "\033[38;5;130m", "title": "\033[1;38;5;214m", "accent": "\033[38;5;220m", "text": "\033[38;5;215m", "dim": "\033[38;5;136m"},
    "nord":   {"border": "\033[38;5;110m", "title": "\033[1;38;5;81m",  "accent": "\033[38;5;116m", "text": "\033[38;5;253m", "dim": "\033[38;5;109m"},
    "mono":   {"border": "\033[38;5;245m", "title": "\033[1;38;5;255m", "accent": "\033[38;5;250m", "text": "\033[38;5;252m", "dim": "\033[38;5;243m"},
}
RESET = "\033[0m"


class Palette:
    """Resolves theme color codes, honoring a global no-color switch."""

    def __init__(self, theme, enabled):
        self.codes = THEMES.get(theme, THEMES["arch"])
        self.enabled = enabled

    def paint(self, role, text):
        if not self.enabled:
            return text
        return self.codes.get(role, "") + text + RESET

    def width(self, text):
        return _display_width(_strip_ansi(text))


def _display_width(text):
    """Visible column width, counting wide/full-width glyphs (emoji) as 2."""
    total = 0
    for ch in text:
        if unicodedata.east_asian_width(ch) in ("W", "F"):
            total += 2
        else:
            total += 1
    return total


def _strip_ansi(text):
    out, i = [], 0
    while i < len(text):
        if text[i] == "\033":
            j = text.find("m", i)
            if j == -1:
                break
            i = j + 1
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #
class FetchError(Exception):
    pass


def http_json(url, headers=None, timeout=10.0):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Accept", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise FetchError("HTTP " + str(exc.code) + " for " + url) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise FetchError("network error: " + str(exc)) from exc
    except json.JSONDecodeError as exc:
        raise FetchError("bad JSON from " + url) from exc


# --------------------------------------------------------------------------- #
# Providers - each returns a normalized dict (or raises FetchError)
# --------------------------------------------------------------------------- #
def fetch_github(user):
    headers = {}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    profile = http_json(API_GITHUB + "/users/" + user, headers)
    repos, page = [], 1
    while page <= 4:  # up to 400 repos
        chunk = http_json(
            API_GITHUB + "/users/" + user + "/repos"
            + "?per_page=100&page=" + str(page) + "&sort=updated",
            headers,
        )
        if not chunk:
            break
        repos.extend(chunk)
        if len(chunk) < 100:
            break
        page += 1

    stars = sum(r.get("stargazers_count", 0) for r in repos)
    forks = sum(r.get("forks_count", 0) for r in repos)
    langs = {}
    for r in repos:
        lang = r.get("language")
        if lang:
            langs[lang] = langs.get(lang, 0) + 1
    top = sorted(repos, key=lambda r: r.get("stargazers_count", 0), reverse=True)[:5]
    return {
        "provider": "GitHub",
        "handle": profile.get("login", user),
        "name": profile.get("name") or profile.get("login", user),
        "bio": profile.get("bio") or "",
        "location": profile.get("location") or "",
        "created": profile.get("created_at", ""),
        "stats": {
            "public repos": profile.get("public_repos", len(repos)),
            "followers": profile.get("followers", 0),
            "following": profile.get("following", 0),
            "total stars": stars,
            "total forks": forks,
            "gists": profile.get("public_gists", 0),
        },
        "languages": langs,
        "top_repos": [
            {"name": r.get("name", ""), "stars": r.get("stargazers_count", 0),
             "lang": r.get("language") or ""}
            for r in top
        ],
        "url": profile.get("html_url", "https://github.com/" + user),
    }


def fetch_gitlab(user):
    found = http_json(API_GITLAB + "/users?username=" + user)
    if not found:
        raise FetchError("GitLab user '" + user + "' not found")
    profile = found[0]
    uid = profile["id"]
    projects, page = [], 1
    while page <= 4:
        chunk = http_json(
            API_GITLAB + "/users/" + str(uid) + "/projects"
            + "?per_page=100&page=" + str(page) + "&order_by=updated_at"
        )
        if not chunk:
            break
        projects.extend(chunk)
        if len(chunk) < 100:
            break
        page += 1

    stars = sum(p.get("star_count", 0) for p in projects)
    forks = sum(p.get("forks_count", 0) for p in projects)
    top = sorted(projects, key=lambda p: p.get("star_count", 0), reverse=True)[:5]
    return {
        "provider": "GitLab",
        "handle": profile.get("username", user),
        "name": profile.get("name") or user,
        "bio": profile.get("bio") or "",
        "location": profile.get("location") or "",
        "created": profile.get("created_at", ""),
        "stats": {
            "public projects": len(projects),
            "total stars": stars,
            "total forks": forks,
        },
        "languages": {},
        "top_repos": [
            {"name": p.get("name", ""), "stars": p.get("star_count", 0), "lang": ""}
            for p in top
        ],
        "url": profile.get("web_url", "https://gitlab.com/" + user),
    }


def fetch_codeforces(handle):
    data = http_json(API_CODEFORCES + "/user.info?handles=" + handle)
    if data.get("status") != "OK" or not data.get("result"):
        raise FetchError("Codeforces handle '" + handle + "' not found")
    u = data["result"][0]
    full = " ".join(x for x in [u.get("firstName"), u.get("lastName")] if x)
    return {
        "provider": "Codeforces",
        "handle": u.get("handle", handle),
        "name": full or u.get("handle", handle),
        "bio": u.get("rank", "") or "",
        "location": " ".join(x for x in [u.get("city"), u.get("country")] if x),
        "created": "",
        "stats": {
            "rating": u.get("rating", 0),
            "max rating": u.get("maxRating", 0),
            "rank": u.get("rank", "unrated"),
            "max rank": u.get("maxRank", "unrated"),
            "contribution": u.get("contribution", 0),
            "friends": u.get("friendOfCount", 0),
        },
        "languages": {},
        "top_repos": [],
        "url": "https://codeforces.com/profile/" + handle,
    }


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def bar(value, total, width=16):
    if total <= 0:
        return " " * width
    filled = max(0, min(width, round(width * value / total)))
    return "█" * filled + "░" * (width - filled)


def _fmt_date(iso):
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return iso[:10]


def box(title, lines, pal, width=52):
    inner = width - 2
    top = pal.paint("border", "╭─ ") + pal.paint("title", title) + " " \
        + pal.paint("border", "─" * max(0, inner - 3 - pal.width(title)) + "╮")
    out = [top]
    for ln in lines:
        pad = inner - 1 - pal.width(ln)
        out.append(pal.paint("border", "│") + " " + ln + " " * max(0, pad)
                   + pal.paint("border", "│"))
    out.append(pal.paint("border", "╰" + "─" * inner + "╯"))
    return out


def render_profile(data, pal, width=52):
    lines = []

    header = []
    name = pal.paint("accent", data["name"])
    handle = pal.paint("dim", "@" + data["handle"])
    header.append(name + "  " + handle)
    if data.get("bio"):
        header.append(pal.paint("text", data["bio"][: width - 4]))
    meta = []
    if data.get("location"):
        meta.append("📍 " + data["location"])
    if data.get("created"):
        meta.append("📅 joined " + _fmt_date(data["created"]))
    if meta:
        header.append(pal.paint("dim", "  ".join(meta)))
    lines += box(data["provider"] + " · profile", header, pal, width)

    stat_lines = []
    for key, val in data["stats"].items():
        label = pal.paint("dim", key.ljust(16))
        stat_lines.append(label + " " + pal.paint("accent", str(val)))
    if stat_lines:
        lines += box("stats", stat_lines, pal, width)

    if data.get("languages"):
        total = sum(data["languages"].values())
        ranked = sorted(data["languages"].items(), key=lambda kv: kv[1], reverse=True)[:6]
        lang_lines = []
        for lang, count in ranked:
            label = pal.paint("text", lang.ljust(12))
            graph = pal.paint("accent", bar(count, ranked[0][1], 16))
            pct = pal.paint("dim", ("%4.0f%%" % (100 * count / total)))
            lang_lines.append(label + " " + graph + " " + pct)
        lines += box("top languages", lang_lines, pal, width)

    if data.get("top_repos"):
        repo_lines = []
        for r in data["top_repos"]:
            star = pal.paint("accent", ("★ " + str(r["stars"])).ljust(8))
            lang = pal.paint("dim", ("[" + r["lang"] + "]") if r["lang"] else "")
            repo_lines.append(star + " " + pal.paint("text", r["name"]) + " " + lang)
        lines += box("top repositories", repo_lines, pal, width)

    if data.get("url"):
        lines.append(pal.paint("dim", "  ↗ " + data["url"]))
    return lines


def render_all(results, pal, width=52):
    stamp = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    head = pal.paint("title", "  devdash") + pal.paint("dim", "  -  dev profile dashboard  ·  " + stamp)
    blocks = [head, ""]
    for data in results:
        blocks += render_profile(data, pal, width)
        blocks.append("")
    return "\n".join(blocks)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
PROVIDERS = {
    "github": fetch_github,
    "gitlab": fetch_gitlab,
    "codeforces": fetch_codeforces,
}

TUI_PROVIDER_ORDER = ["github", "gitlab", "codeforces"]
TUI_THEME_ORDER = ["arch", "matrix", "amber", "nord", "mono"]


def run_tui(args):
    try:
        import curses
    except Exception:  # noqa: BLE001
        print("Interactive TUI needs the 'curses' module (not available here).")
        return 1
    try:
        return curses.wrapper(_tui_main, args)
    except curses.error as exc:
        print("TUI could not start: " + str(exc))
        return 1


def _tui_main(stdscr, args):
    import curses

    curses.curs_set(1)
    stdscr.keypad(True)
    has_color = False
    try:
        if curses.has_colors():
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_CYAN, -1)
            has_color = True
    except curses.error:
        has_color = False
    accent = (curses.color_pair(1) | curses.A_BOLD) if has_color else curses.A_BOLD

    def put(y, x, text, attr=0):
        try:
            mh, mw = stdscr.getmaxyx()
            if y < 0 or y >= mh or x < 0:
                return
            stdscr.addnstr(y, x, text, max(0, mw - x - 1), attr)
        except curses.error:
            pass

    handle = args.github or args.gitlab or args.codeforces or ""
    prov_idx = 0
    if args.gitlab and not args.github:
        prov_idx = 1
    elif args.codeforces and not (args.github or args.gitlab):
        prov_idx = 2
    theme_idx = TUI_THEME_ORDER.index(args.theme) if args.theme in TUI_THEME_ORDER else 0
    body = []
    scroll = 0

    def rebuild():
        if not handle.strip():
            return [
                "",
                "  Type a handle above and press Enter.",
                "  Tab = switch provider    Ctrl-T = switch theme",
            ]
        pal = Palette(TUI_THEME_ORDER[theme_idx], False)
        provider = TUI_PROVIDER_ORDER[prov_idx]
        try:
            data = PROVIDERS[provider](handle.strip())
            return render_profile(data, pal, args.width)
        except Exception as exc:  # noqa: BLE001
            return ["error: " + str(exc)]

    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        title = " devdash tui   provider: %s   theme: %s" % (
            TUI_PROVIDER_ORDER[prov_idx], TUI_THEME_ORDER[theme_idx])
        put(0, 0, title.ljust(w), accent)
        put(1, 0, ("handle> " + handle).ljust(w), curses.A_BOLD)
        put(2, 0, "\u2500" * w)
        area = max(0, h - 4)
        for i, line in enumerate(body[scroll:scroll + area]):
            put(3 + i, 0, line)
        footer = " Enter=fetch  Tab=provider  ^T=theme  Up/Down=scroll  ESC=quit "
        put(h - 1, 0, footer.ljust(w), curses.A_REVERSE)
        try:
            stdscr.move(1, min(len("handle> ") + len(handle), max(0, w - 1)))
        except curses.error:
            pass
        stdscr.refresh()

        ch = stdscr.getch()
        if ch in (27,):
            return 0
        elif ch in (curses.KEY_ENTER, 10, 13):
            if handle.strip():
                put(h - 1, 0, (" fetching " + handle.strip() + " ... ").ljust(w), curses.A_REVERSE)
                stdscr.refresh()
                body = rebuild()
                scroll = 0
        elif ch in (curses.KEY_BACKSPACE, 127, 8):
            handle = handle[:-1]
        elif ch == curses.KEY_UP:
            scroll = max(0, scroll - 1)
        elif ch == curses.KEY_DOWN:
            scroll = min(max(0, len(body) - 1), scroll + 1)
        elif ch == curses.KEY_PPAGE:
            scroll = max(0, scroll - area)
        elif ch == curses.KEY_NPAGE:
            scroll = min(max(0, len(body) - 1), scroll + area)
        elif ch == 9:  # Tab cycles provider
            prov_idx = (prov_idx + 1) % len(TUI_PROVIDER_ORDER)
            if body and handle.strip():
                body = rebuild()
        elif ch == 20:  # Ctrl-T cycles theme
            theme_idx = (theme_idx + 1) % len(TUI_THEME_ORDER)
            if body and handle.strip():
                body = rebuild()
        elif 32 <= ch < 127:
            handle += chr(ch)


def build_parser():
    p = argparse.ArgumentParser(
        prog="devdash",
        description="ASCII developer-profile dashboard for your terminal.",
    )
    p.add_argument("--github", metavar="USER", help="GitHub username")
    p.add_argument("--gitlab", metavar="USER", help="GitLab username")
    p.add_argument("--codeforces", metavar="HANDLE", help="Codeforces handle")
    p.add_argument("--theme", default="arch", choices=sorted(THEMES),
                   help="color theme (default: arch)")
    p.add_argument("--width", type=int, default=52, help="widget width")
    p.add_argument("--no-color", action="store_true", help="disable colors")
    p.add_argument("--json", action="store_true", help="print raw JSON instead of ASCII")
    p.add_argument("--watch", type=float, metavar="SEC",
                   help="refresh every SEC seconds (live mode)")
    p.add_argument("--list-themes", action="store_true", help="list themes and exit")
    p.add_argument("--tui", action="store_true", help="launch interactive TUI")
    p.add_argument("--version", action="version", version="devdash " + __version__)
    return p


def collect(args):
    requested = [
        ("github", args.github),
        ("gitlab", args.gitlab),
        ("codeforces", args.codeforces),
    ]
    results = []
    for name, value in requested:
        if not value:
            continue
        try:
            results.append(PROVIDERS[name](value))
        except FetchError as exc:
            results.append({
                "provider": name.capitalize(),
                "handle": value,
                "name": value,
                "bio": "⚠ could not load: " + str(exc),
                "location": "",
                "created": "",
                "stats": {},
                "languages": {},
                "top_repos": [],
                "url": "",
            })
    return results


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.list_themes:
        for name in sorted(THEMES):
            print(name)
        return 0

    if args.tui or (not (args.github or args.gitlab or args.codeforces)
                    and sys.stdin.isatty() and sys.stdout.isatty()):
        try:
            return run_tui(args)
        except KeyboardInterrupt:
            return 0

    if not (args.github or args.gitlab or args.codeforces):
        build_parser().print_help()
        print("\nTip: try  python3 devdash.py --github torvalds")
        return 1

    color = sys.stdout.isatty() and not args.no_color
    pal = Palette(args.theme, color)

    def one_pass():
        results = collect(args)
        if not results:
            print("No data could be fetched.")
            return 1
        if args.json:
            print(json.dumps(results, indent=2, ensure_ascii=False))
        else:
            print(render_all(results, pal, args.width))
        return 0

    if args.watch:
        try:
            while True:
                print("\033[2J\033[H", end="")  # clear screen
                one_pass()
                time.sleep(max(1.0, args.watch))
        except KeyboardInterrupt:
            return 0
    return one_pass()


if __name__ == "__main__":
    raise SystemExit(main())
