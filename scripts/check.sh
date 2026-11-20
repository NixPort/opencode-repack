#!/usr/bin/env bash
# Check a built package before it is published.
#
# Usage: check.sh <package.tar.gz> [--rootfs DIR]
#
# The package is unpacked into a scratch folder and the program inside it is
# held against the rules that make it usable on a phone: it asks for the
# loader of the app's rootfs, and every library it wants is in that rootfs.

set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOTFS=""
PKG=""
while [ $# -gt 0 ]; do
    case "$1" in
        --rootfs) ROOTFS=$2; shift 2 ;;
        -*) echo "unknown option: $1" >&2; exit 1 ;;
        *) PKG=$1; shift ;;
    esac
done
[ -n "$PKG" ] || { echo "usage: check.sh <package.tar.gz> [--rootfs DIR]" >&2; exit 1; }
[ -f "$PKG" ] || { echo "no such package: $PKG" >&2; exit 1; }

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
tar xzf "$PKG" -C "$work"

dir=$(find "$work" -mindepth 1 -maxdepth 1 -type d -print -quit)
[ -n "$dir" ] || { echo "the package has no folder in it" >&2; exit 1; }

for f in opencode opencode.json.example install.md PROVENANCE.md; do
    [ -f "$dir/$f" ] || { echo "the package has no $f in it" >&2; exit 1; }
done
[ -x "$dir/opencode" ] || { echo "the program in the package is not executable" >&2; exit 1; }

echo ">> the package: $(basename "$PKG")"
ls -la "$dir" | sed 's/^/   /'

if [ -n "$ROOTFS" ]; then
    [ -d "$ROOTFS" ] || { echo "no such rootfs: $ROOTFS" >&2; exit 1; }
    python3 "$HERE/verify.py" --binary "$dir/opencode" --rootfs "$ROOTFS"
fi
echo ">> the package is sound"
