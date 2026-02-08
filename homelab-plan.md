# Homelab Plan

## Hardware

- **NUC7i5BNK**: Intel i5-7260U, 16GB RAM, 1TB NVMe
- **External USB drive**: Backup storage

## Shopping List

| Item | Purpose | Est. Price |
|------|---------|------------|
| Sonoff Zigbee 3.0 Dongle Plus (CC2652P) | Zigbee coordinator | €15 |
| TaHoma Switch (or used TaHoma v2) | Somfy io-homecontrol | €80-180 |
| USB extension cable (50cm) | Reduce Zigbee interference from NUC | €5 |

## Architecture

```
Proxmox VE 8.x (bare metal)
│
├── VM: Home Assistant OS (vm-100)
│   ├── 2 vCPU, 4GB RAM, 32GB disk
│   ├── USB passthrough: Zigbee dongle
│   └── Add-ons: Zigbee2MQTT, Mosquitto, File Editor, Terminal
│
├── LXC: Docker Host (ct-101, Debian 12)
│   ├── 2 vCPU, 4GB RAM, 100GB disk
│   ├── Unprivileged, nesting enabled
│   └── Containers:
│       └── Pi-hole
│
├── LXC: Media Server (ct-102, future)
│   └── Jellyfin, *arr stack
│
└── Remaining: ~8GB RAM, ~800GB disk
```

## Disk Layout

```
1TB NVMe (/dev/nvme0n1)
├── Proxmox OS (20GB)
└── local-lvm (remaining ~980GB)
    ├── vm-100-disk (HAOS) - 32GB
    ├── ct-101-disk (Docker) - 100GB
    └── ~850GB free for future VMs/LXCs

External USB (/dev/sdX)
└── /mnt/backup - Proxmox Backup Storage
```

## Network

| Host | IP | Notes |
|------|----|-------|
| Router | 192.168.1.1 | DHCP range: .2-.249 |
| Proxmox (nuc.local) | 192.168.1.250 | Static |
| Home Assistant | 192.168.1.251 | Assign static in HAOS |
| Docker LXC (Pi-hole) | 192.168.1.252 | Assign static in Proxmox |

- Router DHCP: 192.168.1.2 - 192.168.1.249
- Static range: 192.168.1.250 - 192.168.1.254
- Pi-hole: Once stable, configure router to use 192.168.1.252 as DNS

## Installation Steps

### 1. Prepare Installation Media

```bash
# Download Proxmox VE 8.x ISO
# https://www.proxmox.com/en/downloads

# Write to USB (macOS example)
diskutil list  # find USB disk
diskutil unmountDisk /dev/diskX
sudo dd if=proxmox-ve_8.x.iso of=/dev/rdiskX bs=4M
```

### 2. Install Proxmox VE

1. Boot NUC from USB
2. Select "Install Proxmox VE"
3. Target disk: NVMe drive
4. Country/timezone/keyboard
5. Password + email for root
6. Network: DHCP (or static if preferred)
7. Install and reboot

### 3. Post-Install Configuration

Access web UI at `https://192.168.1.250:8006`

```bash
# SSH into Proxmox host

# Remove subscription nag (optional)
sed -Ezi.bak "s/(Ext\.Msg\.show\(\{[^}]+\.teledata[^}]+\})/void\(0\)/g" /usr/share/javascript/proxmox-widget-toolkit/proxmoxlib.js

# Add no-subscription repo
echo "deb http://download.proxmox.com/debian/pve bookworm pve-no-subscription" > /etc/apt/sources.list.d/pve-no-subscription.list

# Comment out enterprise repo
sed -i 's/^deb/#deb/' /etc/apt/sources.list.d/pve-enterprise.list

# Update
apt update && apt full-upgrade -y
```

### 4. Setup Backup Storage

```bash
# Find external USB drive
lsblk

# Format if needed (WARNING: destroys data)
mkfs.ext4 /dev/sdX1

# Create mount point
mkdir -p /mnt/backup

# Get UUID
blkid /dev/sdX1

# Add to fstab
echo "UUID=<your-uuid> /mnt/backup ext4 defaults 0 2" >> /etc/fstab
mount -a
```

Add as Proxmox storage via UI:
- Datacenter → Storage → Add → Directory
- ID: `backup`
- Directory: `/mnt/backup`
- Content: VZDump backup file

### 5. Create Home Assistant OS VM

Use the community helper script:

```bash
# SSH into Proxmox host
bash -c "$(wget -qLO - https://community-scripts.github.io/ProxmoxVE/scripts/haos-vm.sh)"
```

Follow prompts:
- Use defaults or customize (4GB RAM recommended)
- VM ID: 100

### 6. USB Passthrough for Zigbee Dongle

```bash
# Find Zigbee dongle
lsusb
# Example output: Bus 001 Device 003: ID 10c4:ea60 Silicon Labs CP210x

# Note the vendor:product ID (10c4:ea60 for Sonoff dongle)
```

In Proxmox UI:
1. Select VM 100 (HAOS)
2. Hardware → Add → USB Device
3. Use USB Vendor/Device ID
4. Enter vendor ID and product ID

Or via CLI:
```bash
qm set 100 -usb0 host=10c4:ea60
```

### 7. Create Docker LXC

```bash
# Download Debian 12 template
pveam update
pveam download local debian-12-standard_12.2-1_amd64.tar.zst

# Create LXC
pct create 101 local:vztmpl/debian-12-standard_12.2-1_amd64.tar.zst \
  --hostname docker \
  --cores 2 \
  --memory 4096 \
  --swap 512 \
  --rootfs local-lvm:100 \
  --net0 name=eth0,bridge=vmbr0,ip=192.168.1.252/24,gw=192.168.1.1 \
  --unprivileged 1 \
  --features nesting=1 \
  --onboot 1

# Start container
pct start 101
```

### 8. Install Docker in LXC

```bash
# Enter container
pct enter 101

# Update system
apt update && apt upgrade -y

# Install Docker
apt install -y curl
curl -fsSL https://get.docker.com | sh

# Install docker-compose
apt install -y docker-compose-plugin

# Verify
docker --version
docker compose version
```

### 9. Deploy Pi-hole

```bash
# Create directory structure
mkdir -p /opt/pihole

# Create docker-compose.yml
cat > /opt/pihole/docker-compose.yml << 'EOF'
services:
  pihole:
    container_name: pihole
    image: pihole/pihole:latest
    ports:
      - "53:53/tcp"
      - "53:53/udp"
      - "80:80/tcp"
    environment:
      TZ: 'Europe/Amsterdam'
      WEBPASSWORD: 'changeme'
    volumes:
      - './etc-pihole:/etc/pihole'
      - './etc-dnsmasq.d:/etc/dnsmasq.d'
    restart: unless-stopped
EOF

# Start Pi-hole
cd /opt/pihole
docker compose up -d
```

### 10. Configure Home Assistant

1. Access HAOS at `http://192.168.1.251:8123`
2. Complete onboarding wizard
3. Install add-ons:
   - Settings → Add-ons → Add-on Store
   - Install: Mosquitto broker, Zigbee2MQTT, File editor, Terminal & SSH

4. Configure Zigbee2MQTT:
   - Set serial port to `/dev/ttyUSB0` (or `/dev/ttyACM0`)
   - Start add-on

5. Add TaHoma integration:
   - Settings → Devices & Services → Add Integration
   - Search "Overkiz"
   - Select "Somfy TaHoma"
   - Enable local API (Developer Mode in TaHoma app first)

### 11. Configure Backups

In Proxmox UI:
1. Datacenter → Backup → Add
2. Storage: backup
3. Schedule: daily at 03:00
4. Selection mode: Include selected VMs (100, 101)
5. Compression: ZSTD
6. Mode: Snapshot
7. Retention: keep-last=7, keep-weekly=4

## Future Expansion

### Media Server (when ready)

```bash
# Create dedicated LXC
pct create 102 local:vztmpl/debian-12-standard_12.2-1_amd64.tar.zst \
  --hostname media \
  --cores 2 \
  --memory 4096 \
  --rootfs local-lvm:200 \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp \
  --unprivileged 1 \
  --features nesting=1
```

Services to consider:
- Jellyfin (media streaming)
- Sonarr/Radarr (media management)
- Transmission/qBittorrent (downloads)
- Prowlarr (indexer management)

### Monitoring (when ready)

Add to Docker LXC:
- Grafana
- Prometheus or InfluxDB
- Node exporter on each LXC/VM

### Cameras (when ready)

- Frigate NVR (requires dedicated LXC, possibly with Coral TPU)
- Integration with Home Assistant

## Useful Commands

```bash
# Proxmox
qm list                    # List VMs
pct list                   # List containers
qm start/stop 100          # Start/stop VM
pct start/stop 101         # Start/stop container
vzdump 100 --storage backup --mode snapshot  # Manual backup

# Docker (inside LXC)
docker ps                  # Running containers
docker compose logs -f     # Follow logs
docker system prune -a     # Clean up unused images

# Home Assistant
ha core update             # Update HA Core
ha supervisor update       # Update Supervisor
ha backups new             # Create backup
```

## Current State (2026-02-02)

- Proxmox VE 9.1 running on `nuc` (Debian 13 trixie, kernel 6.17.2).
- Storage: `local-lvm` expanded to ~800 GiB.
- Proxmox repos: enterprise repos disabled; `pve-no-subscription` enabled.
- ISO present: `/var/lib/vz/template/iso/ubuntu-24.04.3-live-server-amd64.iso`.
- VM `openclaw` (VMID 102):
  - 2 vCPU, 4 GB RAM, 32 GB disk on `local-lvm`, bridge `vmbr0`
  - Boot order `ide2;scsi0` (ISO removed after install)
  - Serial console enabled (`serial0: socket`, `vga: serial0`)
- LXC `pihole` (CTID 101):
  - Debian 13; Pi-hole reinstall in progress (user-driven)
  - Current Pi-hole IP (per user): `192.168.1.149`
- DNS clients: using Pi-hole as primary + `8.8.8.8` secondary (allows bypass).
- Planned: Nginx reverse proxy for `*.formsma.nl` internal services.
- TODO: Evaluate moving DNS hosting to Cloudflare (free plan) for automated DNS-01.
- TODO: Set up HTTP-only reverse proxy for `*.formsma.nl` (no TLS for now).
- TODO: Set up Proxmox backups (VZDump schedule + target storage).

## References

- [Proxmox VE Documentation](https://pve.proxmox.com/wiki/Main_Page)
- [Home Assistant OS VM Script](https://community-scripts.github.io/ProxmoxVE/)
- [Zigbee2MQTT Documentation](https://www.zigbee2mqtt.io/)
- [Home Assistant Overkiz Integration](https://www.home-assistant.io/integrations/overkiz/)
- [Pi-hole Docker](https://github.com/pi-hole/docker-pi-hole)
