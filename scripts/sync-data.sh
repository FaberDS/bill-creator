#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

SOURCE_DATA_DIR="$PROJECT_DIR/data"
BACKUP_DATA_DIR="$HOME/Documents/bill-creator/data"

if [ ! -d "$SOURCE_DATA_DIR" ]; then
  echo "Error: project data folder does not exist:"
  echo "  $SOURCE_DATA_DIR"
  echo
  echo "Nothing was backed up."
  exit 1
fi

mkdir -p "$(dirname "$BACKUP_DATA_DIR")"

if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete "$SOURCE_DATA_DIR/" "$BACKUP_DATA_DIR/"
else
  rm -rf "$BACKUP_DATA_DIR"
  cp -a "$SOURCE_DATA_DIR" "$BACKUP_DATA_DIR"
fi

echo "Data backup updated:"
echo "  from: $SOURCE_DATA_DIR"
echo "  to:   $BACKUP_DATA_DIR"
echo
echo "Source of truth remains:"
echo "  $SOURCE_DATA_DIR"