# Installing AttendOps in a VirtualBox VM (bridged to the LAN)

The VM becomes a small server on your network. It reaches the access-control devices directly, and you open
AttendOps from your own computer's browser at `http://<VM-IP>:8080`.

## 1. Create the VM (on your computer)

1. Download **Ubuntu Server 24.04 LTS** (the `.iso`) from https://ubuntu.com/download/server.
2. In VirtualBox, click **New**:
   - Name `attendops`, ISO = the Ubuntu Server image, Type Linux / Ubuntu (64-bit).
   - Tick *Skip Unattended Installation*, so you choose the options in step 2 yourself.
   - **2 CPUs, 4096 MB RAM, 40 GB disk** (dynamically allocated is fine).
3. Before starting it, open **Settings → Network → Adapter 1**:
   - *Attached to*: **Bridged Adapter**
   - *Name*: the network card your computer uses for the LAN. Wired is best; Wi-Fi works, but some Wi-Fi
     networks don't allow bridging.

## 2. Install Ubuntu (in the VM window)

Start the VM and accept the installer defaults, except:

- **Network**: the VM should get an address from your LAN, *not* `10.0.2.15` (that means the adapter is still
  NAT). Ask IT to **reserve this address** for the VM's MAC address (shown in VirtualBox under
  *Settings → Network → Advanced*), or set a static address here, so the web address never changes.
- **Profile**: your name, server name `attendops`, a username and a strong password.
- **SSH**: tick **Install OpenSSH server**. You can then connect from your computer with `ssh <user>@<VM-IP>` and
  copy/paste the commands below.
- **Snaps**: don't pick any (in particular not the Docker snap; the script installs Docker's official packages).

Reboot when asked, then log in.

## 3. Install AttendOps (in the VM, or over SSH)

```bash
sudo apt update && sudo apt install -y git
git clone -b claude/dahua-access-control-app-zkwoc8 https://github.com/crizk-cloud/AttendOps.git
cd AttendOps
./deploy/setup-ubuntu-vm.sh --check 172.22.76.12 --check 172.23.5.202
```

If the repository is private and `git clone` asks for a login, enter your GitHub username and a
[personal access token](https://github.com/settings/tokens) as the password. Alternatively, download the ZIP on
your computer, copy it over with `scp AttendOps.zip <user>@<VM-IP>:`, and run `unzip` in the VM.

The script:

1. shows the VM's address and checks that the devices answer on port 80 (it only warns if they don't),
2. installs Docker Engine from Docker's official repository (free; not Docker Desktop),
3. enables Docker and time sync at boot,
4. opens port 8080 in the firewall if `ufw` is active,
5. runs `./install.sh --lan`, which asks for the first admin's email and password.

At the end it prints the address to open from your computer, for example `http://172.22.76.40:8080`.

## 4. Keep it running

- AttendOps starts automatically whenever the VM boots.
- The **VM** itself must be running. Start it with right-click → *Start → Headless Start*, which runs it in the
  background with no window. Your computer must stay on and must not go to sleep.
- To shut it down cleanly, run `sudo poweroff` in the VM, or right-click → *Close → ACPI Shutdown*.
- Before an update, take a VirtualBox **snapshot** (*Machine → Take Snapshot*). It gives you an easy undo.

## 5. Update to a new version

```bash
cd ~/AttendOps
git pull
./install.sh
```

## 6. Back up

Copy these off the VM regularly, for example with `scp` to your computer:

- `~/AttendOps/.env`: it holds the key that decrypts the stored device passwords. Without it, every device
  password must be re-entered.
- a database dump: see *Back up* in the main README.

## Troubleshooting

| Symptom | What to check |
|---|---|
| VM address is `10.0.2.15` | Adapter 1 is NAT, not Bridged. Power off the VM, change the adapter, start it again. |
| Devices not reachable from the VM | Run `ping 172.22.76.12` in the VM. If it fails, the switch port, VLAN or Wi-Fi may block bridged VMs; try the wired network card. |
| Your computer can't open `http://<VM-IP>:8080` | In `~/AttendOps` run `docker compose ps` (both containers *healthy*?). `grep APP_BIND .env` must show `0.0.0.0`. Check `sudo ufw status`. |
| `permission denied ... docker.sock` | Log out and back in; membership of the docker group applies from the next login. |
