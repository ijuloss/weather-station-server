#!/usr/bin/env bash
set -euo pipefail

# Attempt to make host-mounted directories writable by the 'weather' user
TARGET_UID=$(id -u weather 2>/dev/null || echo "$(id -u)")
TARGET_GID=$(id -g weather 2>/dev/null || echo "$(id -g)")
DIRS=("/var/lib/weather-station" "/var/log/weather-station" "/etc/weather-station" "/run/weather-station")
for d in "${DIRS[@]}"; do
  if [ -d "$d" ]; then
    # Only attempt chown and suppress noisy errors for read-only mounts
    chown -R ${TARGET_UID}:${TARGET_GID} "$d" 2>/dev/null || true
  else
    mkdir -p "$d" 2>/dev/null || true
    chown -R ${TARGET_UID}:${TARGET_GID} "$d" 2>/dev/null || true
  fi
done

# If the first arg is 'python' (the server), exec as the 'weather' user via gosu
if [ "$1" = "python" ]; then
  exec gosu weather "$@"
fi

# Otherwise just exec the given command
exec "$@"
