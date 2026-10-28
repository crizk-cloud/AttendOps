#!/usr/bin/env bash
# Prepare a fresh Ubuntu Server VM (e.g. VirtualBox, bridged to the LAN) and install AttendOps on it.
# Run from the AttendOps folder, as your normal user (it uses sudo when needed):
#
#   ./deploy/setup-ubuntu-vm.sh
#   ./deploy/setup-ubuntu-vm.sh --check 172.22.76.12 --check 172.23.5.202 --admin-email you@example.com
#
# What it does:
#   1. checks this is Ubuntu/Debian and that the VM can reach the devices (TCP port 80)
#   2. installs Docker Engine from Docker's official apt repository (free; not Docker Desktop)
#   3. enables Docker and time sync at boot
#   4. opens the app port in ufw, if ufw is active
#   5. runs ./install.sh --lan, so other computers (your PC) can open the app
# Safe to run again.
set -euo pipefail
cd "$(dirname "$0")/.."

CHECKS=()
INSTALL_ARGS=(--lan)
while [ $# -gt 0 ]; do
  case "$1" in
    --check) CHECKS+=("$2"); shift 2 ;;
    --admin-email|--port) INSTALL_ARGS+=("$1" "$2"); shift 2 ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done
[ ${#CHECKS[@]} -gt 0 ] || CHECKS=(172.22.76.12 172.23.5.202)

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -ne 0 ] || die "Run this as your normal user, not root (it calls sudo itself)."
. /etc/os-release 2>/dev/null || die "Cannot read /etc/os-release."
case "${ID:-}" in
  ubuntu|debian) ;;
  *) die "This script supports Ubuntu/Debian (found '${ID:-unknown}'). Install Docker Engine manually, then run ./install.sh --lan" ;;
esac

say "1/5 Network"
IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo "This VM's address: ${IP:-unknown}"
case "$IP" in
  10.0.2.*) echo "WARNING: 10.0.2.x looks like VirtualBox NAT, not a bridged adapter. Other computers will not reach the app." ;;
esac
for ip in "${CHECKS[@]}"; do
  if timeout 3 bash -c "exec 3<>/dev/tcp/$ip/80" 2>/dev/null; then
    echo "  OK       $ip:80 reachable"
  else
    echo "  WARNING  $ip:80 not reachable from this VM (check the bridged adapter, VLAN/routing, firewall)"
  fi
done

say "2/5 Docker Engine"
if command -v docker >/dev/null && docker compose version >/dev/null 2>&1; then
  echo "Docker already installed: $(docker --version)"
else
  sudo apt-get update -y
  sudo apt-get install -y ca-certificates curl
  sudo install -m 0755 -d /etc/apt/keyrings
  sudo curl -fsSL "https://download.docker.com/linux/${ID}/gpg" -o /etc/apt/keyrings/docker.asc
  sudo chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/${ID} ${VERSION_CODENAME} stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update -y
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

say "3/5 Start at boot"
sudo systemctl enable --now docker containerd >/dev/null
sudo timedatectl set-ntp true 2>/dev/null || true
if ! id -nG "$USER" | grep -qw docker; then
  sudo usermod -aG docker "$USER"
  echo "Added $USER to the 'docker' group (takes effect at your next login)."
fi

say "4/5 Firewall"
PORT=8080
for ((i = 0; i < ${#INSTALL_ARGS[@]}; i++)); do [ "${INSTALL_ARGS[$i]}" = "--port" ] && PORT="${INSTALL_ARGS[$((i + 1))]}"; done
[ -f .env ] && PORT=$(grep -E '^APP_PORT=' .env | cut -d= -f2 || echo "$PORT")
if command -v ufw >/dev/null && sudo ufw status | grep -q "Status: active"; then
  sudo ufw allow "${PORT}/tcp" >/dev/null && echo "ufw: allowed TCP ${PORT}"
else
  echo "ufw not active; nothing to do."
fi

say "5/5 AttendOps"
if [ -f .env ] && ! grep -q '^APP_BIND=0.0.0.0' .env; then
  echo "NOTE: .env already exists with APP_BIND other than 0.0.0.0; set APP_BIND=0.0.0.0 in .env so your PC can connect."
fi
# Run with the docker group active now, without needing to log out first.
sg docker -c "$(printf '%q ' ./install.sh "${INSTALL_ARGS[@]}")"

say "Open AttendOps from your computer: http://${IP:-<this-VM-IP>}:${PORT}"
echo "Tip: ask IT for a DHCP reservation for this VM so the address stays the same."
