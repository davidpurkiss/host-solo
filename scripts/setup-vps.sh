#!/usr/bin/env bash
# =============================================================================
# Host Solo — VPS Setup Script
# =============================================================================
# A single command to set up a fresh Ubuntu VPS with:
#   - Non-root user with sudo + SSH access
#   - SSH hardening (key-only, no root login)
#   - UFW firewall
#   - Automatic security updates
#   - Docker (rootless mode)
#   - Python 3 + pip
#   - Host Solo
#
# Usage (run as root on a fresh Ubuntu 22.04/24.04 VPS):
#
#   curl -fsSL https://raw.githubusercontent.com/davidpurkiss/host-solo/main/scripts/setup-vps.sh | bash -s -- \
#     --user dpurkiss \
#     --ssh-key "ssh-ed25519 AAAA... you@host"
#
# Or download and run:
#
#   wget -O setup-vps.sh https://raw.githubusercontent.com/davidpurkiss/host-solo/main/scripts/setup-vps.sh
#   chmod +x setup-vps.sh
#   ./setup-vps.sh --user dpurkiss --ssh-key "$(cat ~/.ssh/id_ed25519.pub)"
#
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Colours & helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No colour

info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fail()  { echo -e "${RED}[FAIL]${NC}  $*"; exit 1; }

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
USERNAME=""
SSH_PUBLIC_KEY=""
DOCKER_MODE="rootless"   # rootless | group
INSTALL_HOSTSOLO="yes"
PYTHON_VERSION="3"       # system python3
EXTRA_PORTS=""            # comma-separated, e.g. "8080,3000"

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
usage() {
    cat <<EOF
Usage: $0 --user <username> --ssh-key "<public key string>"

Required:
  --user        Username for the non-root account
  --ssh-key     SSH public key (the full string, e.g. "ssh-ed25519 AAAA...")

Optional:
  --docker-mode   "rootless" (default) or "group"
  --extra-ports   Additional UFW ports to open, comma-separated (e.g. "8080,3000")
  --skip-hostsolo Skip Host Solo installation
  --help          Show this help message
EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --user)         USERNAME="$2";        shift 2 ;;
        --ssh-key)      SSH_PUBLIC_KEY="$2";  shift 2 ;;
        --docker-mode)  DOCKER_MODE="$2";     shift 2 ;;
        --extra-ports)  EXTRA_PORTS="$2";     shift 2 ;;
        --skip-hostsolo) INSTALL_HOSTSOLO="no"; shift ;;
        --help|-h)      usage ;;
        *) fail "Unknown option: $1. Use --help for usage." ;;
    esac
done

# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------
[[ $(id -u) -ne 0 ]] && fail "This script must be run as root."
[[ -z "$USERNAME" ]]  && fail "Missing --user. Use --help for usage."
[[ -z "$SSH_PUBLIC_KEY" ]] && fail "Missing --ssh-key. Use --help for usage."
[[ "$DOCKER_MODE" != "rootless" && "$DOCKER_MODE" != "group" ]] && \
    fail "--docker-mode must be 'rootless' or 'group'."

# Check we're on Ubuntu
if ! grep -qi ubuntu /etc/os-release 2>/dev/null; then
    warn "This script is designed for Ubuntu. Proceed with caution on other distros."
fi

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║          Host Solo — VPS Setup                   ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"
echo ""
info "User:         $USERNAME"
info "Docker mode:  $DOCKER_MODE"
info "Host Solo:    $INSTALL_HOSTSOLO"
echo ""

# ============================= PHASE 1: SYSTEM =============================
info "──── Phase 1: System updates ────"

export DEBIAN_FRONTEND=noninteractive

apt-get update -qq
apt-get upgrade -y -qq
ok "System packages updated."

# ---------------------------------------------------------------------------
# Automatic security updates
# ---------------------------------------------------------------------------
apt-get install -y -qq unattended-upgrades > /dev/null 2>&1
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF
ok "Automatic security updates enabled."

# ============================= PHASE 2: USER ===============================
info "──── Phase 2: Non-root user ────"

if id "$USERNAME" &>/dev/null; then
    warn "User '$USERNAME' already exists. Skipping creation."
else
    adduser --disabled-password --gecos "" "$USERNAME"
    ok "User '$USERNAME' created."
fi

# Add to sudo group
usermod -aG sudo "$USERNAME"

# Allow passwordless sudo (optional but useful for automation)
echo "$USERNAME ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/$USERNAME"
chmod 440 "/etc/sudoers.d/$USERNAME"
ok "Sudo access configured."

# Set up SSH key
USER_HOME="/home/$USERNAME"
SSH_DIR="$USER_HOME/.ssh"
mkdir -p "$SSH_DIR"

# Append key if not already present
if ! grep -qF "$SSH_PUBLIC_KEY" "$SSH_DIR/authorized_keys" 2>/dev/null; then
    echo "$SSH_PUBLIC_KEY" >> "$SSH_DIR/authorized_keys"
fi

chown -R "$USERNAME:$USERNAME" "$SSH_DIR"
chmod 700 "$SSH_DIR"
chmod 600 "$SSH_DIR/authorized_keys"
ok "SSH key installed for '$USERNAME'."

# ============================= PHASE 3: SSH ================================
info "──── Phase 3: SSH hardening ────"

SSHD_CONFIG="/etc/ssh/sshd_config"

# Helper: set or add an sshd_config directive
sshd_set() {
    local key="$1" value="$2"
    if grep -qE "^#?${key}\s" "$SSHD_CONFIG"; then
        sed -i "s|^#*${key}\s.*|${key} ${value}|" "$SSHD_CONFIG"
    else
        echo "${key} ${value}" >> "$SSHD_CONFIG"
    fi
}

sshd_set "PermitRootLogin"        "no"
sshd_set "PasswordAuthentication" "no"
sshd_set "PubkeyAuthentication"   "yes"
sshd_set "MaxAuthTries"           "3"
sshd_set "X11Forwarding"          "no"
sshd_set "AllowTcpForwarding"     "no"

systemctl restart sshd
ok "SSH hardened (root login disabled, password auth disabled)."

# ============================= PHASE 4: FIREWALL ===========================
info "──── Phase 4: Firewall (UFW) ────"

apt-get install -y -qq ufw > /dev/null 2>&1

ufw default deny incoming > /dev/null 2>&1
ufw default allow outgoing > /dev/null 2>&1
ufw allow ssh > /dev/null 2>&1
ufw allow 80/tcp > /dev/null 2>&1
ufw allow 443/tcp > /dev/null 2>&1

# Open extra ports if specified
if [[ -n "$EXTRA_PORTS" ]]; then
    IFS=',' read -ra PORTS <<< "$EXTRA_PORTS"
    for port in "${PORTS[@]}"; do
        ufw allow "$port/tcp" > /dev/null 2>&1
        info "Opened port $port/tcp."
    done
fi

echo "y" | ufw enable > /dev/null 2>&1
ok "Firewall enabled (SSH, 80, 443$([ -n "$EXTRA_PORTS" ] && echo ", $EXTRA_PORTS"))."

# ============================= PHASE 5: DOCKER =============================
info "──── Phase 5: Docker ────"

if command -v docker &>/dev/null; then
    warn "Docker already installed. Skipping installation."
else
    # Install prerequisites
    apt-get install -y -qq \
        ca-certificates curl gnupg lsb-release \
        uidmap dbus-user-session > /dev/null 2>&1

    # Add Docker's official GPG key and repo
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
        gpg --dearmor -o /etc/apt/keyrings/docker.gpg 2>/dev/null
    chmod a+r /etc/apt/keyrings/docker.gpg

    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update -qq
    apt-get install -y -qq \
        docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin > /dev/null 2>&1

    ok "Docker installed."
fi

# Configure log rotation
mkdir -p /etc/docker
cat > /etc/docker/daemon.json <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
EOF

systemctl restart docker 2>/dev/null || true
ok "Docker log rotation configured."

# ---------------------------------------------------------------------------
# Docker access mode
# ---------------------------------------------------------------------------
if [[ "$DOCKER_MODE" == "rootless" ]]; then
    info "Setting up Docker rootless mode for '$USERNAME'..."

    # Rootless needs systemd user session — enable lingering
    loginctl enable-linger "$USERNAME"

    # Run the rootless setup as the target user
    su - "$USERNAME" -c '
        # Disable system docker for this user to avoid conflicts
        # Install rootless docker
        dockerd-rootless-setuptool.sh install 2>&1 | tail -5

        # Enable on boot
        systemctl --user enable docker 2>/dev/null || true
    '

    # Add env vars to bashrc
    BASHRC="$USER_HOME/.bashrc"
    if ! grep -q "DOCKER_HOST.*rootless" "$BASHRC" 2>/dev/null; then
        cat >> "$BASHRC" <<'ENVEOF'

# Docker rootless mode
export PATH=/usr/bin:$PATH
export DOCKER_HOST=unix://${XDG_RUNTIME_DIR}/docker.sock
ENVEOF
    fi

    ok "Docker rootless mode configured."
    warn "Note: Rootless Docker cannot bind to ports below 1024."
    info "Traefik (via Host Solo) handles ports 80/443 — this is fine."

else
    # Docker group mode
    usermod -aG docker "$USERNAME"
    ok "User '$USERNAME' added to docker group."
    warn "Docker group access is equivalent to root. Be cautious."
fi

# ============================= PHASE 6: PYTHON =============================
info "──── Phase 6: Python ────"

apt-get install -y -qq \
    python3 python3-pip python3-venv python3-full > /dev/null 2>&1

PYTHON_VER=$(python3 --version 2>&1)
ok "Python installed ($PYTHON_VER)."

# ============================= PHASE 7: HOST SOLO =========================
if [[ "$INSTALL_HOSTSOLO" == "yes" ]]; then
    info "──── Phase 7: Host Solo ────"

    # Install host-solo in a dedicated venv to avoid system package conflicts
    HOSTSOLO_VENV="$USER_HOME/.hostsolo-venv"

    su - "$USERNAME" -c "
        python3 -m venv '$HOSTSOLO_VENV'
        source '$HOSTSOLO_VENV/bin/activate'
        pip install --upgrade pip -q
        pip install hostsolo -q 2>/dev/null || {
            # If not on PyPI yet, install from source
            cd /tmp
            git clone https://github.com/davidpurkiss/host-solo.git hostsolo-src 2>/dev/null
            cd hostsolo-src
            pip install -e . -q
            cd /
            rm -rf /tmp/hostsolo-src
        }
    "

    # Add venv bin to PATH so `hostsolo` is always available
    BASHRC="$USER_HOME/.bashrc"
    if ! grep -q "hostsolo-venv" "$BASHRC" 2>/dev/null; then
        cat >> "$BASHRC" <<PATHEOF

# Host Solo
export PATH="$HOSTSOLO_VENV/bin:\$PATH"
PATHEOF
    fi

    chown -R "$USERNAME:$USERNAME" "$HOSTSOLO_VENV"

    ok "Host Solo installed."
    info "Run 'hostsolo init' in your project directory to get started."
fi

# ============================= PHASE 8: HARDENING ==========================
info "──── Phase 8: Final hardening ────"

# Disable root password login entirely
passwd -l root > /dev/null 2>&1
ok "Root password login disabled."

# Set kernel hardening parameters
cat > /etc/sysctl.d/99-hostsolo-hardening.conf <<'EOF'
# Prevent IP spoofing
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1

# Ignore ICMP redirects
net.ipv4.conf.all.accept_redirects = 0
net.ipv6.conf.all.accept_redirects = 0

# Disable source routing
net.ipv4.conf.all.accept_source_route = 0
net.ipv6.conf.all.accept_source_route = 0

# Log suspicious packets
net.ipv4.conf.all.log_martians = 1

# Ignore broadcast pings
net.ipv4.icmp_echo_ignore_broadcasts = 1

# SYN flood protection
net.ipv4.tcp_syncookies = 1
EOF

sysctl --system > /dev/null 2>&1
ok "Kernel hardening parameters applied."

# Install fail2ban for SSH brute-force protection
apt-get install -y -qq fail2ban > /dev/null 2>&1

cat > /etc/fail2ban/jail.local <<'EOF'
[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 3600
findtime = 600
EOF

systemctl enable fail2ban > /dev/null 2>&1
systemctl restart fail2ban > /dev/null 2>&1
ok "fail2ban installed (SSH brute-force protection)."

# ============================= DONE ========================================
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║          Setup complete!                         ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BLUE}What was done:${NC}"
echo -e "    ✓ System updated + automatic security updates"
echo -e "    ✓ User '${USERNAME}' created with sudo + SSH key"
echo -e "    ✓ SSH hardened (key-only, no root, max 3 attempts)"
echo -e "    ✓ UFW firewall enabled (SSH, 80, 443)"
echo -e "    ✓ Docker installed (${DOCKER_MODE} mode)"
echo -e "    ✓ Docker log rotation configured"
echo -e "    ✓ Python 3 installed"
if [[ "$INSTALL_HOSTSOLO" == "yes" ]]; then
echo -e "    ✓ Host Solo installed"
fi
echo -e "    ✓ fail2ban SSH protection enabled"
echo -e "    ✓ Kernel hardening applied"
echo -e "    ✓ Root password login disabled"
echo ""
echo -e "  ${YELLOW}Next steps:${NC}"
echo -e "    1. Open a NEW terminal and test SSH access:"
echo -e "       ${GREEN}ssh ${USERNAME}@$(curl -s -4 ifconfig.me 2>/dev/null || echo '<server-ip>')${NC}"
echo ""
echo -e "    2. Initialise your first project:"
echo -e "       ${GREEN}mkdir ~/myapp && cd ~/myapp${NC}"
echo -e "       ${GREEN}hostsolo init${NC}"
echo ""
echo -e "    3. Start the reverse proxy:"
echo -e "       ${GREEN}hostsolo proxy up${NC}"
echo ""
echo -e "    4. Deploy your first app:"
echo -e "       ${GREEN}hostsolo deploy up <app> --env prod${NC}"
echo ""
echo -e "  ${RED}⚠  Do NOT close this session until you've confirmed${NC}"
echo -e "  ${RED}   SSH access works in a separate terminal!${NC}"
echo ""