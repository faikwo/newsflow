#!/usr/bin/env bash
# =============================================================================
#  NewsFlow — Install Script
#  Supports: Debian, Ubuntu, and most Linux distros
# =============================================================================

set -e

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ── Helpers ───────────────────────────────────────────────────────────────────
info()    { echo -e "${BLUE}${BOLD}[INFO]${NC}  $*"; }
ok()      { echo -e "${GREEN}${BOLD}[ OK ]${NC}  $*"; }
warn()    { echo -e "${YELLOW}${BOLD}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}${BOLD}[ERR ]${NC}  $*"; exit 1; }
section() { echo -e "\n${CYAN}${BOLD}━━━  $*  ━━━${NC}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_MODE="fresh"

# =============================================================================
section "NewsFlow Installer"
# =============================================================================
echo -e "${BOLD}Welcome to NewsFlow — AI-powered personal news aggregator${NC}"
echo -e "This script will check dependencies, configure your environment,"
echo -e "create the data directory, and launch the application.\n"

# =============================================================================
section "1 / 7 — Detecting Previous Installation"
# =============================================================================

cd "$SCRIPT_DIR"

PREV_CONTAINERS=$(docker ps -a --format '{{.Names}}' 2>/dev/null | grep -E '^newsflow-(backend|frontend)$' || true)
PREV_IMAGES=$(docker images --format '{{.Repository}}' 2>/dev/null | grep -E 'newsflow' || true)
HAS_PREVIOUS=false

if [[ -n "$PREV_CONTAINERS" ]] || [[ -n "$PREV_IMAGES" ]] || \
   [[ -f "$SCRIPT_DIR/data/newsflow.db" ]] || [[ -f "$SCRIPT_DIR/.env" ]]; then
  HAS_PREVIOUS=true
fi

if $HAS_PREVIOUS; then
  echo -e "${YELLOW}${BOLD}A previous NewsFlow installation was detected:${NC}"
  echo ""
  [[ -n "$PREV_CONTAINERS" ]] && echo -e "  🐳 Containers: ${PREV_CONTAINERS//$'\n'/, }"
  [[ -n "$PREV_IMAGES" ]]     && echo -e "  📦 Images:     $(echo "$PREV_IMAGES" | tr '\n' ' ')"
  [[ -f "$SCRIPT_DIR/.env" ]] && echo -e "  ⚙️  Config:     .env found"
  if [[ -f "$SCRIPT_DIR/data/newsflow.db" ]]; then
    DB_SIZE=$(du -sh "$SCRIPT_DIR/data/newsflow.db" 2>/dev/null | cut -f1 || echo "?")
    echo -e "  💾 Database:   data/newsflow.db ($DB_SIZE)"
  fi
  echo ""
  echo -e "  ${BOLD}What would you like to do?${NC}"
  echo ""
  echo -e "  ${GREEN}${BOLD}[1] Upgrade${NC}        — Keep all data, accounts & settings. Rebuild with latest code."
  echo -e "  ${RED}${BOLD}[2] Fresh install${NC}  — Wipe everything (containers, images, data, .env). Start clean."
  echo -e "  ${BOLD}[3] Abort${NC}          — Exit without making any changes."
  echo ""

  while true; do
    read -rp "  Enter choice [1/2/3]: " CHOICE
    case "$CHOICE" in
      1)
        INSTALL_MODE="upgrade"
        ok "Upgrade selected — your data is safe"
        break
        ;;
      2)
        INSTALL_MODE="fresh"
        echo ""
        echo -e "  ${RED}${BOLD}⚠️  WARNING: This will permanently delete:${NC}"
        echo -e "  ${RED}  • All NewsFlow Docker containers and images${NC}"
        echo -e "  ${RED}  • Your database (articles, likes, users, settings)${NC}"
        echo -e "  ${RED}  • Your .env file (secret key, port config)${NC}"
        echo ""
        read -rp "  Type YES to confirm complete wipe: " CONFIRM
        if [[ "$CONFIRM" == "YES" ]]; then
          ok "Fresh install confirmed — wiping previous installation"
        else
          info "Aborted — nothing was changed"
          exit 0
        fi
        break
        ;;
      3)
        info "Aborted — nothing was changed"
        exit 0
        ;;
      *)
        warn "Please enter 1, 2, or 3"
        ;;
    esac
  done
else
  ok "No previous installation detected — proceeding with fresh install"
fi

# =============================================================================
#  FRESH INSTALL — Wipe everything
# =============================================================================
if [[ "$INSTALL_MODE" == "fresh" ]] && $HAS_PREVIOUS; then
  section "Wiping Previous Installation"

  info "Stopping and removing containers..."
  docker rm -f newsflow-backend newsflow-frontend 2>/dev/null && ok "Containers removed" || ok "No containers to remove"

  info "Removing Docker images..."
  NEWSFLOW_IMAGES=$(docker images --format '{{.Repository}}:{{.Tag}}' 2>/dev/null | grep newsflow || true)
  if [[ -n "$NEWSFLOW_IMAGES" ]]; then
    echo "$NEWSFLOW_IMAGES" | xargs docker rmi -f 2>/dev/null
    ok "Images removed"
  else
    ok "No images to remove"
  fi

  info "Pruning all Docker build cache..."
  docker builder prune -af 2>/dev/null || true
  ok "Build cache fully pruned"

  # Remove old named volume if it exists from very old installs
  docker volume rm newsflow_newsflow-data 2>/dev/null && ok "Old named volume removed" || true

  info "Removing data directory..."
  if [[ -d "$SCRIPT_DIR/data" ]]; then
    rm -rf "$SCRIPT_DIR/data" 2>/dev/null || sudo rm -rf "$SCRIPT_DIR/data"
    ok "Data directory removed"
  else
    ok "No data directory to remove"
  fi

  info "Removing .env..."
  rm -f "$SCRIPT_DIR/.env" && ok ".env removed" || ok "No .env to remove"

  ok "Previous installation completely removed — starting fresh"
fi

# =============================================================================
#  UPGRADE — Stop containers, back up DB, remove old images for clean rebuild
# =============================================================================
if [[ "$INSTALL_MODE" == "upgrade" ]]; then
  section "Preparing Upgrade"

  if [[ -f "$SCRIPT_DIR/data/newsflow.db" ]]; then
    BACKUP_PATH="$SCRIPT_DIR/data/newsflow.db.backup-$(date +%Y%m%d-%H%M%S)"
    cp "$SCRIPT_DIR/data/newsflow.db" "$BACKUP_PATH" 2>/dev/null || \
      sudo cp "$SCRIPT_DIR/data/newsflow.db" "$BACKUP_PATH" 2>/dev/null || true
    ok "Database backed up → $BACKUP_PATH"
  fi

  info "Stopping running containers..."
  docker rm -f newsflow-backend newsflow-frontend 2>/dev/null && ok "Containers stopped" || ok "No containers running"

  info "Removing old images so they rebuild with latest code..."
  NEWSFLOW_IMAGES=$(docker images --format '{{.Repository}}:{{.Tag}}' 2>/dev/null | grep newsflow || true)
  if [[ -n "$NEWSFLOW_IMAGES" ]]; then
    echo "$NEWSFLOW_IMAGES" | xargs docker rmi -f 2>/dev/null
    ok "Old images removed"
  else
    ok "No old images found"
  fi
fi

# =============================================================================
section "2 / 7 — Checking System"
# =============================================================================

if [[ "$EUID" -eq 0 ]]; then
  warn "Running as root is not recommended. Docker volumes may have permission issues."
  read -rp "Continue anyway? [y/N] " ans
  [[ "$ans" =~ ^[Yy]$ ]] || exit 1
fi

if [[ -f /etc/os-release ]]; then
  . /etc/os-release
  OS_NAME="${PRETTY_NAME:-$ID}"
else
  OS_NAME="Unknown"
fi
info "OS: $OS_NAME"

ARCH=$(uname -m)
info "Architecture: $ARCH"
if [[ "$ARCH" == "armv7l" ]]; then
  warn "32-bit ARM detected. Docker builds may be slow — consider a 64-bit OS."
fi

# =============================================================================
section "3 / 7 — Checking Dependencies"
# =============================================================================

MISSING=()

if command -v docker &>/dev/null; then
  DOCKER_VER=$(docker --version | grep -oP '\d+\.\d+\.\d+' | head -1)
  ok "Docker $DOCKER_VER found"
else
  MISSING+=("docker")
  warn "Docker not found"
fi

if docker compose version &>/dev/null 2>&1; then
  COMPOSE_VER=$(docker compose version --short 2>/dev/null || echo "v2")
  ok "Docker Compose v2 ($COMPOSE_VER) found"
  COMPOSE_CMD="docker compose"
elif command -v docker-compose &>/dev/null; then
  COMPOSE_VER=$(docker-compose --version | grep -oP '\d+\.\d+\.\d+' | head -1)
  ok "Docker Compose v1 ($COMPOSE_VER) found"
  COMPOSE_CMD="docker-compose"
else
  MISSING+=("docker-compose")
  warn "Docker Compose not found"
  COMPOSE_CMD="docker compose"
fi

if command -v curl &>/dev/null; then
  ok "curl found"
else
  MISSING+=("curl")
  warn "curl not found"
fi

if command -v openssl &>/dev/null; then
  ok "openssl found (will use for secret key)"
  KEYGEN_CMD="openssl rand -hex 32"
elif command -v python3 &>/dev/null; then
  ok "python3 found (will use for secret key)"
  KEYGEN_CMD="python3 -c \"import secrets; print(secrets.token_hex(32))\""
else
  KEYGEN_CMD=""
  warn "Neither openssl nor python3 found — SECRET_KEY will use fallback"
fi

if [[ ${#MISSING[@]} -gt 0 ]]; then
  echo ""
  warn "Missing dependencies: ${MISSING[*]}"
  if [[ "${MISSING[*]}" == *"docker"* ]]; then
    echo ""
    info "To install Docker on Debian / Ubuntu:"
    echo -e "  ${BOLD}curl -fsSL https://get.docker.com | sh${NC}"
    echo -e "  ${BOLD}sudo usermod -aG docker \$USER${NC}"
    echo ""
  fi
  read -rp "Attempt to install missing dependencies now? [y/N] " ans
  if [[ "$ans" =~ ^[Yy]$ ]]; then
    if command -v apt-get &>/dev/null; then
      sudo apt-get update -qq
      if [[ "${MISSING[*]}" == *"docker"* ]]; then
        info "Installing Docker..."
        curl -fsSL https://get.docker.com | sudo sh
        sudo usermod -aG docker "$USER"
        warn "Docker installed. Log out and back in, or run: newgrp docker"
      fi
      [[ "${MISSING[*]}" == *"curl"* ]] && sudo apt-get install -y -qq curl
    else
      error "Cannot auto-install on this OS. Please install: ${MISSING[*]}"
    fi
  else
    error "Please install the missing dependencies and re-run install.sh"
  fi
fi

# =============================================================================
section "4 / 7 — Creating Directory Structure"
# =============================================================================

cd "$SCRIPT_DIR"

if [[ ! -d "data" ]]; then
  mkdir -p data
  ok "Created ./data  (SQLite database will live here)"
else
  ok "./data already exists — leaving it untouched"
fi

if chmod 755 data 2>/dev/null; then
  ok "Permissions set on ./data"
else
  if sudo chmod 755 data 2>/dev/null; then
    ok "Permissions set on ./data (via sudo)"
  else
    warn "Could not chmod ./data — should still work if previously created"
  fi
fi

# =============================================================================
section "5 / 7 — Configuring Environment"
# =============================================================================

ENV_FILE="$SCRIPT_DIR/.env"

if [[ -f "$ENV_FILE" ]]; then
  ok ".env already exists — keeping your existing config"
  info "Current settings (secrets hidden):"
  grep -v 'PASSWORD\|SECRET' "$ENV_FILE" | grep -v '^#' | grep -v '^$' || true
else
  info "Generating .env file..."

  if [[ -n "$KEYGEN_CMD" ]]; then
    SECRET=$(eval "$KEYGEN_CMD")
    ok "Generated cryptographically random SECRET_KEY"
  else
    SECRET=$(head -c 32 /dev/urandom | base64 | tr -d '=+/' | head -c 48)
    warn "Using /dev/urandom fallback for SECRET_KEY"
  fi

  echo ""
  read -rp "Which port should NewsFlow run on? [default: 3000] " PORT_INPUT
  PORT="${PORT_INPUT:-3000}"

  cat > "$ENV_FILE" << EOF
# NewsFlow Environment — generated by install.sh on $(date)

# ── Security ──────────────────────────────────────────────────────────────────
# This key signs all login tokens. Keep it secret. Change it if compromised.
SECRET_KEY=${SECRET}

# ── Network ───────────────────────────────────────────────────────────────────
# Port to expose the app on (access via http://YOUR_PI_IP:${PORT})
PORT=${PORT}
EOF

  ok ".env created with auto-generated SECRET_KEY on port $PORT"
fi

# =============================================================================
section "6 / 7 — Building and Starting NewsFlow"
# =============================================================================

echo ""
if [[ "$INSTALL_MODE" == "upgrade" ]]; then
  info "Rebuilding images with latest code and restarting containers."
else
  info "Building Docker images and starting containers."
  info "First build takes 5–10 minutes (compiles React app). Subsequent starts are fast."
fi
echo ""
read -rp "Build and start now? [Y/n] " ans
ans="${ans:-Y}"

if [[ "$ans" =~ ^[Yy]$ ]]; then
  if [[ "$INSTALL_MODE" == "fresh" ]]; then
    info "Fresh install — building with --no-cache to ensure clean images"
    echo ""
    # Also prune all build cache so nothing stale sneaks in
    docker builder prune -af 2>/dev/null || true
    $COMPOSE_CMD build --no-cache
    $COMPOSE_CMD up -d
  else
    info "Running: $COMPOSE_CMD up -d --build"
    echo ""
    $COMPOSE_CMD up -d --build
  fi
  echo ""
  ok "Containers started!"
else
  info "Skipping build. When ready, run:"
  echo -e "  ${BOLD}cd $SCRIPT_DIR && $COMPOSE_CMD up -d --build${NC}"
fi

# =============================================================================
section "7 / 7 — Done"
# =============================================================================

LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "YOUR_PI_IP")
PORT_USED=$(grep '^PORT=' "$ENV_FILE" | cut -d= -f2 || echo "3000")

echo ""
if [[ "$INSTALL_MODE" == "upgrade" ]]; then
  echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════════════╗${NC}"
  echo -e "${GREEN}${BOLD}║         NewsFlow upgraded successfully! 🎉                ║${NC}"
  echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════════════════╝${NC}"
  echo ""
  echo -e "  ✅ All your data, accounts, and settings have been preserved."
  echo -e "  ✅ A database backup was saved to ${BOLD}./data/${NC} before upgrading."
else
  echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════════════╗${NC}"
  echo -e "${GREEN}${BOLD}║              NewsFlow is ready! 📰                       ║${NC}"
  echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════════════════╝${NC}"
  echo ""
  echo -e "  ${BOLD}First steps:${NC}"
  echo -e "  1. Register an account — ${BOLD}first user becomes admin${NC}"
  echo -e "  2. Go to ${BOLD}Settings${NC} → set your Ollama server URL"
  echo -e "  3. Click ${BOLD}Test${NC} and pick your model"
  echo -e "  4. Go to ${BOLD}Topics${NC} → subscribe to what interests you"
  echo -e "  5. Click ${BOLD}Refresh${NC} in the feed to fetch your first articles"
fi

echo ""
echo -e "  ${BOLD}Open in browser:${NC}  http://${LOCAL_IP}:${PORT_USED}"
echo -e "  ${BOLD}Also try:${NC}         http://$(hostname).local:${PORT_USED}"
echo ""
echo -e "  ${BOLD}Your data folder:${NC}  $SCRIPT_DIR/data/"
echo -e "  ${BOLD}Backup command:${NC}"
echo -e "    cp -r $SCRIPT_DIR/data ~/newsflow-backup-\$(date +%Y%m%d)"
echo ""
echo -e "  ${BOLD}Useful commands:${NC}"
echo -e "    ${CYAN}$COMPOSE_CMD logs -f${NC}          # live logs"
echo -e "    ${CYAN}$COMPOSE_CMD restart${NC}          # restart services"
echo -e "    ${CYAN}$COMPOSE_CMD down${NC}             # stop"
echo -e "    ${CYAN}./install.sh${NC}                  # upgrade or reinstall"
echo ""
