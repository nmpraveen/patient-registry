#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  echo "Usage: deploy/nas-export/install-nas-export.sh --public-key-file /absolute/path/to/key.pub" >&2
}

if [[ $# -ne 2 || "$1" != "--public-key-file" ]]; then
  usage
  exit 2
fi
public_key_file="$2"
if [[ "$public_key_file" != /* || ! -f "$public_key_file" || -L "$public_key_file" ]]; then
  echo "Public key must be a regular file at an absolute path" >&2
  exit 1
fi
if [[ "$(wc -l < "$public_key_file" | tr -d ' ')" -ne 1 ]]; then
  echo "Public key file must contain exactly one line" >&2
  exit 1
fi
public_key="$(cat "$public_key_file")"
if [[ ! "$public_key" =~ ^ssh-ed25519[[:space:]][A-Za-z0-9+/]+={0,3}([[:space:]].*)?$ ]]; then
  echo "Only one Ed25519 public key is accepted" >&2
  exit 1
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
group_name=medtrack-nas-readers
user_name=medtrack-nas-pull
chroot=/srv/medtrack/nas-export
authorized_keys_dir=/etc/ssh/authorized_keys
sshd_dropin=/etc/ssh/sshd_config.d/90-medtrack-nas-pull.conf
ssh_allowlist=/etc/ssh/sshd_config.d/00-medtrack-hardening.conf

for source_file in \
  "$repo_root/deploy/nas-export/export-encrypted-backups.sh" \
  "$repo_root/deploy/nas-export/medtrack-nas-export.service" \
  "$repo_root/deploy/nas-export/medtrack-nas-export.timer" \
  "$repo_root/deploy/nas-export/sshd-medtrack-nas-pull.conf"; do
  [[ -f "$source_file" ]] || {
    echo "Missing deployment asset: $source_file" >&2
    exit 1
  }
done

if ! getent group "$group_name" >/dev/null; then
  groupadd --system "$group_name"
fi
if ! getent passwd "$user_name" >/dev/null; then
  useradd --system --gid "$group_name" --home-dir / --shell /usr/sbin/nologin "$user_name"
fi
usermod --gid "$group_name" --home / --shell /usr/sbin/nologin "$user_name"

install -d -o root -g root -m 0755 "$chroot"
install -d -o root -g "$group_name" -m 0750 "$chroot/data"
install -d -o root -g root -m 0755 "$authorized_keys_dir"
key_temp="$(mktemp "$authorized_keys_dir/.${user_name}.XXXXXX")"
printf '%s\n' "$public_key" > "$key_temp"
chown root:root "$key_temp"
chmod 0644 "$key_temp"
mv -f -- "$key_temp" "$authorized_keys_dir/$user_name"

install -o root -g root -m 0755 \
  "$repo_root/deploy/nas-export/export-encrypted-backups.sh" \
  /usr/local/sbin/medtrack-export-encrypted-backups
install -o root -g root -m 0644 \
  "$repo_root/deploy/nas-export/medtrack-nas-export.service" \
  /etc/systemd/system/medtrack-nas-export.service
install -o root -g root -m 0644 \
  "$repo_root/deploy/nas-export/medtrack-nas-export.timer" \
  /etc/systemd/system/medtrack-nas-export.timer

had_sshd_dropin=false
sshd_backup="$(mktemp)"
if [[ -f "$sshd_dropin" ]]; then
  had_sshd_dropin=true
  cp -a "$sshd_dropin" "$sshd_backup"
fi
if [[ ! -f "$ssh_allowlist" ]]; then
  echo "Expected MEDTRACK SSH allowlist is missing: $ssh_allowlist" >&2
  exit 1
fi
allowlist_backup="$(mktemp)"
cp -a "$ssh_allowlist" "$allowlist_backup"
rollback_sshd() {
  exit_code=$?
  if (( exit_code != 0 )); then
    if [[ "$had_sshd_dropin" == true ]]; then
      cp -a "$sshd_backup" "$sshd_dropin"
    else
      rm -f -- "$sshd_dropin"
    fi
    cp -a "$allowlist_backup" "$ssh_allowlist"
  fi
  rm -f -- "$sshd_backup" "$allowlist_backup"
  exit "$exit_code"
}
trap rollback_sshd EXIT
if ! awk '$1 == "AllowUsers" { for (i = 2; i <= NF; i++) if ($i == "medtrack-nas-pull") found = 1 } END { exit(found ? 0 : 1) }' "$ssh_allowlist"; then
  allowlist_temp="$(mktemp "${ssh_allowlist}.XXXXXX")"
  awk '
    $1 == "AllowUsers" && !updated { print $0 " medtrack-nas-pull"; updated = 1; next }
    { print }
    END { if (!updated) exit 1 }
  ' "$ssh_allowlist" > "$allowlist_temp"
  chown root:root "$allowlist_temp"
  chmod 0644 "$allowlist_temp"
  mv -f -- "$allowlist_temp" "$ssh_allowlist"
fi
install -o root -g root -m 0644 \
  "$repo_root/deploy/nas-export/sshd-medtrack-nas-pull.conf" \
  "$sshd_dropin"

sshd -t
systemd-analyze verify \
  /etc/systemd/system/medtrack-nas-export.service \
  /etc/systemd/system/medtrack-nas-export.timer
systemctl daemon-reload
systemctl enable --now medtrack-nas-export.timer
systemctl start medtrack-nas-export.service
systemctl reload ssh

trap - EXIT
rm -f -- "$sshd_backup" "$allowlist_backup"

systemctl is-enabled medtrack-nas-export.timer
systemctl is-active medtrack-nas-export.timer
service_result="$(systemctl show medtrack-nas-export.service --property=Result --value)"
if [[ "$service_result" != "success" ]]; then
  echo "Initial MEDTRACK NAS export service result was not successful: $service_result" >&2
  exit 1
fi
systemctl is-active medtrack-nas-export.service || true
find "$chroot/data" -mindepth 2 -maxdepth 2 -type f -printf '%P\t%s\n' | sort
printf 'MEDTRACK_NAS_EXPORT_INSTALL_OK user=%s chroot=%s\n' "$user_name" "$chroot"
