# AIM — Installation Guide

**Artificial Intelligence Mesh** · Free forever · Apache 2.0

---

## Quick Start (Termux / Android)

Run the one-command installer:

```sh
curl -fsSL https://raw.githubusercontent.com/Cbetts1/Aiw/main/install.sh | sh
```

Or clone and install manually:

```sh
pkg update && pkg upgrade -y
pkg install -y python git
git clone https://github.com/Cbetts1/Aiw.git ~/aim
cd ~/aim
pip install -e .
aim --version
```

---

## Requirements

| Requirement | Version |
|-------------|---------|
| Python | 3.11+ |
| pip | 23+ |
| OS | Linux, macOS, Android (Termux), Windows (WSL) |

### Termux-specific notes

- All paths are under `/data/data/com.termux/files/home/`
- No root or sudo required
- No Docker or virtualization required
- ARM64 CPU supported natively
- Privileged ports (< 1024) are unavailable; AIM uses ports ≥ 7700 by default

---

## Installing in Termux

```sh
# 1. Update packages
pkg update && pkg upgrade -y

# 2. Install Python and git
pkg install -y python git

# 3. Clone the repository
git clone https://github.com/Cbetts1/Aiw.git ~/aim

# 4. Install AIM
cd ~/aim
pip install -e .

# 5. Verify installation
aim --version
aim status
```

### Optional: install cryptography for Ed25519 PKI

```sh
pkg install -y libffi openssl
pip install cryptography
```

---

## Installing on Linux / macOS

```sh
git clone https://github.com/Cbetts1/Aiw.git ~/aim
cd ~/aim
pip install -e .
aim --version
```

---

## Installing for development (with tests)

```sh
git clone https://github.com/Cbetts1/Aiw.git ~/aim
cd ~/aim
pip install -e ".[test]"
python -m pytest tests/ -v
```

---

## Upgrading

```sh
cd ~/aim
git pull
pip install -e .
```

---

## Data Directory

AIM stores runtime data (directory listings, posts, content) under:

```
~/.local/share/aim/
```

Override by setting the `AIM_DATA_DIR` environment variable:

```sh
export AIM_DATA_DIR=/data/data/com.termux/files/home/.aim
aim web start
```

---

## Uninstalling

```sh
pip uninstall aim -y
rm -rf ~/aim ~/.local/share/aim
```

---

## Troubleshooting

### `aim: command not found`

Ensure `~/.local/bin` is in your PATH:

```sh
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### Python version too old

```sh
# Termux
pkg install -y python
python --version   # should be 3.11+

# Linux
apt install python3.11 python3.11-pip
```

### Port already in use

AIM default ports: **7700** (node), **7800** (relay), **7900** (gateway), **8080** (web).
Override with `--port`:

```sh
aim node start --port 9000
```

---

## See Also

- [USAGE.md](USAGE.md) — Full usage guide
- [docs/MESH_ARCHITECTURE.md](docs/MESH_ARCHITECTURE.md) — Architecture overview
- [docs/FOUNDATION.md](docs/FOUNDATION.md) — Project charter
