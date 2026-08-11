# Restricted NAS backup export

These assets expose completed encrypted MEDTRACK backup triplets to a NAS without giving the VPS any NAS credentials or write path.

## Trust boundary

- `/srv/medtrack/offsite-backups/local` remains the root-only source.
- `export-encrypted-backups.sh` verifies each completed triplet, then publishes new files into `/srv/medtrack/nas-export/data` without deleting older exports.
- An existing same-name export must be byte-identical; conflicts fail closed.
- `medtrack-nas-pull` is restricted to public-key SFTP inside `/srv/medtrack/nas-export` with no shell, TTY, forwarding, tunnel, or password authentication.
- Only the NAS-generated public key belongs on the VPS. The private SFTP key stays on the NAS, and the private `age` identity stays off both systems.

## Install

Run from the reviewed repository checkout on the VPS:

```bash
sudo ./deploy/nas-export/install-nas-export.sh \
  --public-key-file /absolute/path/to/medtrack-nas-pull.pub
```

The installer validates the key, existing MEDTRACK SSH allowlist, `sshd` configuration, and systemd units before reloading SSH. On failure it restores the affected SSH configuration files.

The recurring export runs hourly with up to five minutes of jitter. After a manual pre-deployment backup, publish it immediately rather than waiting for the timer:

```bash
MEDTRACK_BACKUP_CONFIG=/etc/medtrack-backup/backup.env \
  ./scripts/backup-offsite.sh --tier pre-deployment
systemctl start medtrack-nas-export.service
test "$(systemctl show medtrack-nas-export.service --property=Result --value)" = success
```

This only refreshes the local read-only SFTP export. The NAS still initiates its own six-hour pull.

## Verify

```bash
systemctl is-enabled medtrack-nas-export.timer
systemctl is-active medtrack-nas-export.timer
systemctl show medtrack-nas-export.service --property=Result --value
journalctl -u medtrack-nas-export.service --since '24 hours ago' --no-pager
find /srv/medtrack/nas-export/data -mindepth 2 -maxdepth 2 -type f -printf '%P\t%s\n' | sort
sshd -T -C user=medtrack-nas-pull,host=localhost,addr=127.0.0.1
```

The NAS-side fetcher/promoter stack and its NAS-only secrets are managed from the private NAS operations workspace. They are intentionally not copied into this application repository.
