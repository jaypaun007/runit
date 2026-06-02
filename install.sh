#!/usr/bin/env bash
set -euo pipefail

# ╔═══════════════════════════════════════════╗
# ║   Runit - One-Click Installer            ║
# ║   macOS / Linux                          ║
# ╚═══════════════════════════════════════════╝

BOLD='\033[1m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color
CHECK="\xE2\x9C\x85"

echo ""
echo -e "${BOLD}${CYAN}  ╔══════════════════════════════════════╗${NC}"
echo -e "${BOLD}${CYAN}  ║       ⚡ Runit Installer             ║${NC}"
echo -e "${BOLD}${CYAN}  ║  AI-Powered Repo Execution Agent     ║${NC}"
echo -e "${BOLD}${CYAN}  ╚══════════════════════════════════════╝${NC}"
echo ""

# ── Check Python ──
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        VER=$("$cmd" --version 2>&1 | grep -oP '\d+\.\d+' | head -1)
        MAJOR=${VER%%.*}
        if [ "$MAJOR" -ge 3 ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo -e "  ${RED}✗ Python 3 not found.${NC}"
    echo "  Install it: https://python.org/downloads/"
    exit 1
fi
echo -e "  ${CHECK} Python: $($PYTHON --version)"

# ── Check pip ──
if ! $PYTHON -m pip --version &>/dev/null; then
    echo -e "  ${YELLOW}⚠ pip not found, installing...${NC}"
    if command -v curl &>/dev/null; then
        curl -sS https://bootstrap.pypa.io/get-pip.py | $PYTHON
    elif command -v wget &>/dev/null; then
        wget -qO- https://bootstrap.pypa.io/get-pip.py | $PYTHON
    else
        $PYTHON -c "import urllib.request; exec(urllib.request.urlopen('https://bootstrap.pypa.io/get-pip.py').read())"
    fi
fi
echo -e "  ${CHECK} pip: $($PYTHON -m pip --version | head -1)"

# ── Install via pip ──
echo ""
echo -e "  ${BOLD}Installing Runit...${NC}"
$PYTHON -m pip install --upgrade pip -q
$PYTHON -m pip install rich requests -q

# Install runit
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
$PYTHON -m pip install "$SCRIPT_DIR" -q

echo -e "  ${CHECK} Runit installed successfully!"

# ── Verify ──
if command -v runit &>/dev/null; then
    echo -e "  ${CHECK} runit command available"
fi

# ── Setup prompt ──
echo ""
echo -e "  ${BOLD}${GREEN}✔ Installation complete!${NC}"
echo ""
echo -e "  ${BOLD}Quick Start:${NC}"
echo -e "    runit --setup         ${YELLOW}# Configure your API key${NC}"
echo -e "    runit --skills        ${YELLOW}# View agent skills${NC}"
echo -e "    runit <repo-url>      ${YELLOW}# Run a GitHub repo${NC}"
echo -e "    runit .               ${YELLOW}# Run current folder${NC}"
echo ""
echo -e "  ${BOLD}Need help?${NC}  runit --help"
echo ""

# ── Setup wizard ──
echo -e "  ${BOLD}${CYAN}🔑 Would you like to configure your AI provider now?${NC} (Y/n)"
read -r -n1 choice
echo ""
if [[ "$choice" =~ ^[Yy]$ ]] || [[ -z "$choice" ]]; then
    runit --setup
fi
