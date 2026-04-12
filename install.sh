#!/bin/sh
# AIM — One-command Termux / Linux installer
# Usage: curl -fsSL https://raw.githubusercontent.com/Cbetts1/Aiw/main/install.sh | sh
#
# Supports: Termux (Android ARM64), Linux, macOS
# Requires: Python 3.11+, git, pip
# No root. No sudo. No Docker.

set -e

AIM_REPO="https://github.com/Cbetts1/Aiw.git"
AIM_DIR="${HOME}/aim"
AIM_VERSION="0.1.0"

# ── colour helpers ────────────────────────────────────────────────────────────
_green()  { printf '\033[32m%s\033[0m\n' "$*"; }
_yellow() { printf '\033[33m%s\033[0m\n' "$*"; }
_red()    { printf '\033[31m%s\033[0m\n' "$*"; }
_bold()   { printf '\033[1m%s\033[0m\n'  "$*"; }

# ── banner ────────────────────────────────────────────────────────────────────
_bold  "============================================================"
_bold  "  A.I.M. — Artificial Intelligence Mesh  v${AIM_VERSION}"
_bold  "  Founder : Christopher Lee Betts (Cbetts1)"
_bold  "  Free forever. Never for sale. Never for profit."
_bold  "============================================================"
printf '\n'

# ── detect environment ────────────────────────────────────────────────────────
IS_TERMUX=0
if [ -d "/data/data/com.termux" ]; then
    IS_TERMUX=1
    _green "Detected: Termux (Android)"
else
    _green "Detected: standard POSIX environment"
fi

# ── dependency check / install ────────────────────────────────────────────────
_check_cmd() {
    command -v "$1" >/dev/null 2>&1
}

if [ "$IS_TERMUX" -eq 1 ]; then
    _yellow "Updating Termux packages..."
    pkg update -y >/dev/null 2>&1 || true
    pkg upgrade -y >/dev/null 2>&1 || true

    if ! _check_cmd python; then
        _yellow "Installing Python..."
        pkg install -y python
    fi

    if ! _check_cmd git; then
        _yellow "Installing git..."
        pkg install -y git
    fi
else
    if ! _check_cmd python3 && ! _check_cmd python; then
        _red "Python not found. Please install Python 3.11+ and re-run this script."
        exit 1
    fi

    if ! _check_cmd git; then
        _red "git not found. Please install git and re-run this script."
        exit 1
    fi
fi

# ── resolve python / pip ──────────────────────────────────────────────────────
PYTHON=""
if _check_cmd python; then
    PYTHON="python"
elif _check_cmd python3; then
    PYTHON="python3"
else
    _red "Cannot locate python or python3 in PATH."
    exit 1
fi

PY_VERSION=$("$PYTHON" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
PY_MAJOR=$("$PYTHON" -c 'import sys; print(sys.version_info[0])')
PY_MINOR=$("$PYTHON" -c 'import sys; print(sys.version_info[1])')

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 11 ]; }; then
    _red "Python $PY_VERSION detected. AIM requires Python 3.11+."
    _yellow "On Termux, run: pkg install python"
    exit 1
fi

_green "Python $PY_VERSION — OK"

PIP=""
if "$PYTHON" -m pip --version >/dev/null 2>&1; then
    PIP="$PYTHON -m pip"
elif _check_cmd pip; then
    PIP="pip"
elif _check_cmd pip3; then
    PIP="pip3"
else
    _red "pip not found. Please install pip and re-run this script."
    exit 1
fi

# ── clone or update repo ──────────────────────────────────────────────────────
if [ -d "$AIM_DIR/.git" ]; then
    _yellow "Updating existing AIM installation at $AIM_DIR ..."
    cd "$AIM_DIR"
    git pull --ff-only
else
    _yellow "Cloning AIM repository to $AIM_DIR ..."
    git clone "$AIM_REPO" "$AIM_DIR"
    cd "$AIM_DIR"
fi

# ── install AIM ───────────────────────────────────────────────────────────────
_yellow "Installing AIM..."
$PIP install -e . --quiet

# ── PATH fixup ────────────────────────────────────────────────────────────────
LOCAL_BIN="${HOME}/.local/bin"
SHELL_RC=""
if [ -n "$BASH_VERSION" ] || [ "$(basename "$SHELL")" = "bash" ]; then
    SHELL_RC="${HOME}/.bashrc"
elif [ "$(basename "$SHELL")" = "zsh" ]; then
    SHELL_RC="${HOME}/.zshrc"
fi

if ! echo "$PATH" | grep -q "$LOCAL_BIN"; then
    if [ -n "$SHELL_RC" ]; then
        echo "export PATH=\"$LOCAL_BIN:\$PATH\"" >> "$SHELL_RC"
        _yellow "Added $LOCAL_BIN to PATH in $SHELL_RC"
        export PATH="$LOCAL_BIN:$PATH"
    fi
fi

# ── verify ────────────────────────────────────────────────────────────────────
if _check_cmd aim || "$PYTHON" -m aim --version >/dev/null 2>&1; then
    printf '\n'
    _green "============================================================"
    _green "  AIM installed successfully!"
    _green "============================================================"
    printf '\n'
    _bold  "Quick start:"
    printf '  aim --version\n'
    printf '  aim node start\n'
    printf '  aim web start\n'
    printf '  aim health\n'
    printf '\n'
    _bold  "Documentation:"
    printf '  cat %s/INSTALL.md\n' "$AIM_DIR"
    printf '  cat %s/USAGE.md\n'   "$AIM_DIR"
    printf '\n'
    _yellow "Data directory: ~/.local/share/aim/"
    printf '\n'
else
    _red "Installation completed but 'aim' command not found in PATH."
    _yellow "Run: export PATH=\"$LOCAL_BIN:\$PATH\""
    _yellow "Then: aim --version"
fi
