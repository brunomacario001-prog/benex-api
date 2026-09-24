"""Small, read-only BeneX commands available in the interactive terminal."""

import sys
import urllib.error
import urllib.request


SITE_URL = "https://benex.net.br"
REPOSITORY_URL = "https://api.github.com/repos/brunomacario001-prog/benex-site/commits/main"


def check_site():
    request = urllib.request.Request(SITE_URL, headers={"User-Agent": "BeneX-Terminal/1.4"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            print(f"Site: online (HTTP {response.status}) — {SITE_URL}")
            return True
    except urllib.error.HTTPError as error:
        print(f"Site: indisponível (HTTP {error.code}) — {SITE_URL}")
    except (OSError, TimeoutError) as error:
        print(f"Site: não foi possível consultar ({type(error).__name__})")
    return False


def check_source():
    request = urllib.request.Request(
        REPOSITORY_URL,
        headers={"User-Agent": "BeneX-Terminal/1.4", "Accept": "application/vnd.github+json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            import json

            data = json.load(response)
            commit = data["sha"]
            print(f"Código no GitHub (main): {commit[:12]}")
            return True
    except (urllib.error.HTTPError, OSError, TimeoutError, ValueError, KeyError, TypeError) as error:
        print(f"GitHub: não foi possível consultar ({type(error).__name__})")
    return False


def main(argv):
    if argv == ["site", "status"]:
        site_ok = check_site()
        source_ok = check_source()
        print("O commit do GitHub indica a origem do código; a publicação depende da Vercel.")
        return 0 if site_ok and source_ok else 1
    if not argv or argv in (["help"], ["--help"], ["site"], ["site", "help"]):
        print("BeneX Terminal — comandos disponíveis: benex site status, benex version, benex help")
        return 0
    if argv == ["version"]:
        print("BeneX Terminal 1.4")
        return 0
    print("Comando desconhecido. Use: benex help", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
