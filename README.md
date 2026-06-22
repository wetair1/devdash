# devdash

![python](https://img.shields.io/badge/python-3.8%2B-blue) ![deps](https://img.shields.io/badge/dependencies-0-success) ![license](https://img.shields.io/badge/license-MIT-green) ![platform](https://img.shields.io/badge/platform-terminal-lightgrey)

An ASCII **developer-profile dashboard** for your terminal. Pull your public
stats from multiple coding platforms and render them as tidy bordered widgets
with switchable color themes — GitHub, GitLab and Codeforces in one screen.

Pure **Python 3, standard library only** — no `pip install`, no dependencies.
It talks to public JSON APIs over `urllib`, so it runs anywhere Python does.

## Features

- 👤 **Profile card** — name, handle, bio, location, join date
- 📊 **Stats** — repos, followers, total stars & forks (per platform)
- 🧭 **Top languages** with usage bars (GitHub)
- ⭐ **Top repositories** ranked by stars
- 🏆 **Codeforces** rating, max rating and rank
- 🎨 **Themes:** `arch`, `matrix`, `amber`, `nord`, `mono`
- 🖥 **Interactive TUI** (`--tui`) — type a handle live, Tab switches provider, Ctrl-T switches theme
- 📦 **`--json` mode** for piping into other tools
- 🔁 **`--watch` mode** to refresh live
- 🪛 **Graceful fallback** — a provider that fails to load is shown with an
  error line instead of crashing the whole dashboard

## Supported providers

| Provider | Flag | Notes |
| --- | --- | --- |
| GitHub | `--github USER` | public profile + repos; set `GITHUB_TOKEN` to raise rate limits |
| GitLab | `--gitlab USER` | public profile + projects |
| Codeforces | `--codeforces HANDLE` | competitive-programming rating & rank |

## Requirements

- Python 3.8+
- A terminal with 256-color / truecolor support (use `--no-color` otherwise)
- Network access to reach the provider APIs

## Install

```bash
git clone https://github.com/wetair1/devdash.git
cd devdash
python3 devdash.py --github torvalds
```

Optionally make it runnable from anywhere:

```bash
chmod +x devdash.py
ln -s "$PWD/devdash.py" ~/.local/bin/devdash
```

## Usage

```bash
python3 devdash.py --tui                            # interactive TUI
python3 devdash.py --github wetair1
python3 devdash.py --github wetair1 --gitlab gitlab-org --theme matrix
python3 devdash.py --codeforces tourist
python3 devdash.py --github octocat --json
python3 devdash.py --github octocat --watch 60      # refresh every 60s
python3 devdash.py --list-themes
```

### CLI options

| Flag | Description |
| --- | --- |
| `--github USER` | GitHub username |
| `--gitlab USER` | GitLab username |
| `--codeforces HANDLE` | Codeforces handle |
| `--tui` | launch the interactive TUI |
| `--theme NAME` | color theme (default: `arch`) |
| `--width N` | widget width |
| `--no-color` | disable ANSI colors |
| `--json` | print raw JSON instead of ASCII |
| `--watch SEC` | refresh every SEC seconds (live mode) |
| `--list-themes` | list available themes |
| `--version` | print version |

## Example output

```
  devdash  -  dev profile dashboard

+- GitHub . profile ------------------------------+
| Linus Torvalds  @torvalds                       |
| Creator of Linux and Git                        |
| location: Portland, OR   joined 2011-09-03      |
+-------------------------------------------------+
+- stats ------------------------------------------+
| public repos     8                              |
| followers        230000                         |
| total stars      190000                         |
+-------------------------------------------------+
+- top languages ----------------------------------+
| C            ################   56%             |
| Assembly     ######..........   22%             |
+-------------------------------------------------+
```

(Real output uses rounded Unicode borders, block-bar glyphs and ANSI colors.)

## Notes

- GitHub limits unauthenticated API calls to ~60/hour per IP. Export
  `GITHUB_TOKEN` to raise the limit; the token is only sent to GitHub.
- A provider that errors out (typo, rate limit, offline) is rendered with an
  inline warning instead of crashing the whole dashboard.
- `--no-color` is applied automatically when output is not a TTY (e.g. piped).

## License

MIT — see [LICENSE](LICENSE).
