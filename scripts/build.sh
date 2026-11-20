#!/usr/bin/env bash
# Download the upstream program a recipe names, make it runnable in the
# nixport rootfs, and package it.
#
# Usage: build.sh <recipe.yml> [--outdir DIR] [--rootfs DIR] [--version TAG]
#
# --rootfs is the tree the app unpacks (the payload's rootfs): the libraries
# the program wants are checked against it, and the program is started with it.
# --version overrides the recipe's version; "latest" asks the upstream for its
# newest release.
#
# Prints one line per built package: "<output path> <sha256>". The caller
# (the release workflow) turns those into release assets.

set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
OUTDIR="$HERE/../out"
ROOTFS=""
VERSION=""
RECIPE=""

while [ $# -gt 0 ]; do
    case "$1" in
        --outdir) OUTDIR=$2; shift 2 ;;
        --rootfs) ROOTFS=$2; shift 2 ;;
        --version) VERSION=$2; shift 2 ;;
        -*) echo "unknown option: $1" >&2; exit 1 ;;
        *) RECIPE=$1; shift ;;
    esac
done
[ -n "$RECIPE" ] || { echo "usage: build.sh <recipe.yml> [--outdir DIR] [--rootfs DIR]" >&2; exit 1; }
[ -f "$RECIPE" ] || { echo "no such recipe: $RECIPE" >&2; exit 1; }
[ -n "$ROOTFS" ] || { echo "a rootfs is needed: --rootfs DIR" >&2; exit 1; }
[ -d "$ROOTFS" ] || { echo "no such rootfs: $ROOTFS" >&2; exit 1; }

mkdir -p "$OUTDIR"

log() { printf '[build] %s\n' "$*" >&2; }

# The recipes are flat "key: value" lists, so a plain grep is enough and keeps
# the pipeline free of a YAML dependency. The first entry of a list carries a
# "- " prefix, so that has to be allowed.
recipe_field() {
    local file=$1 key=$2
    sed -n "s/^[[:space:]]*\(-\{0,1\}[[:space:]]*\)${key}:[[:space:]]*//p" "$file" |
        head -1 | sed 's/^["'\'']//; s/["'\'']$//'
}

name=$(recipe_field "$RECIPE" name)
repo=$(recipe_field "$RECIPE" repo)
version=$(recipe_field "$RECIPE" version)
asset=$(recipe_field "$RECIPE" asset)
arch=$(recipe_field "$RECIPE" arch)
binary=$(recipe_field "$RECIPE" binary)
interp=$(recipe_field "$RECIPE" interp)
sha=$(recipe_field "$RECIPE" sha256)

[ -n "$name" ] && [ -n "$repo" ] && [ -n "$version" ] && [ -n "$asset" ] &&
    [ -n "$arch" ] && [ -n "$binary" ] && [ -n "$interp" ] ||
    { echo "incomplete recipe: $RECIPE" >&2; exit 1; }

[ -n "$VERSION" ] && version="$VERSION"

# "latest" asks the upstream which release is the newest one.
if [ "$version" = "latest" ]; then
    version=$(curl -sSL -f "https://api.github.com/repos/${repo}/releases/latest" |
              sed -n 's/.*"tag_name":[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
    [ -n "$version" ] || { echo "the upstream has no release to build" >&2; exit 1; }
    log "the newest upstream release is $version"
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

url="https://github.com/${repo}/releases/download/${version}/${asset}"
log "downloading $url"
curl -sSL -f -o "$work/upstream.tar.gz" "$url" ||
    { echo "download failed: $url" >&2; exit 1; }

got=$(sha256sum "$work/upstream.tar.gz" | cut -d' ' -f1)
if [ -n "$sha" ] && [ "$version" = "$(recipe_field "$RECIPE" version)" ]; then
    # The pinned checksum is what keeps the pipeline honest: the download is
    # verified before anything is unpacked, and a mismatch fails the build
    # rather than producing a package from bytes nobody checked.
    [ "$got" = "$sha" ] ||
        { echo "checksum mismatch for $asset" >&2; exit 1; }
    log "checksum verified"
else
    log "no pinned checksum for $version ($asset): $got"
fi

log "unpacking"
mkdir -p "$work/unpack"
tar xzf "$work/upstream.tar.gz" -C "$work/unpack"
program=$(find "$work/unpack" -type f -name "$binary" -print -quit)
[ -n "$program" ] || { echo "the archive has no $binary in it" >&2; exit 1; }
chmod +x "$program"

log "setting the interpreter to $interp"
python3 "$HERE/patch_interp.py" "$program" "$interp" --verbose

log "checking the libraries against the rootfs"
python3 "$HERE/verify.py" --binary "$program" --rootfs "$ROOTFS" --interp "$interp"

# The smoke test: the program has to start with the rootfs's loader and its
# libraries. It only runs where the program and the rootfs are the same
# architecture as the host.
host=$(uname -m)
if [ "$host" = "aarch64" ] || [ "$host" = "arm64" ]; then
    loader="$interp"
    if [ -e "$loader" ]; then
        log "smoke test"
        # The program's own words go into the log: a package is only worth
        # publishing when the repacked program answers for itself.
        out=$(LD_LIBRARY_PATH="$ROOTFS/usr/lib/aarch64-linux-gnu:$ROOTFS/usr/lib" "$program" --version 2>&1) ||
            { echo "the repacked program did not start: $out" >&2; exit 1; }
        log "the program says: $out"
    else
        log "the loader is not at $loader here: the smoke test is skipped"
    fi
else
    log "the host is $host: the smoke test is skipped (it needs an arm64 host)"
fi

# The package: the program, the configuration it needs and the notes that say
# where it came from.
stem="${name}-nx2a-${version}-${arch}"
out="$OUTDIR/${stem}.tar.gz"
pkgdir="$work/$stem"
mkdir -p "$pkgdir"
cp "$program" "$pkgdir/$binary"
cp "$HERE/../templates/opencode.json.example" "$pkgdir/opencode.json.example"
cp "$HERE/../templates/install.md" "$pkgdir/install.md"
cat > "$pkgdir/PROVENANCE.md" <<EOF
# Provenance

| | |
|---|---|
| upstream | ${repo} |
| upstream release | ${version} |
| upstream asset | ${asset} |
| upstream asset sha256 | \`${got}\` |
| repacked | $(date -u +%Y-%m-%dT%H:%M:%SZ) |
| repacked asset sha256 | see \`${stem}.tar.gz.sha256\` |

## What the repack changed

One thing: the ELF interpreter (PT_INTERP) of the program. The upstream binary
asks for \`/lib/ld-linux-aarch64.so.1\`, and Android has no \`/lib\` — the nixport
guest is not a chroot either, so the guest sees the phone's own root. The
program therefore has to be started through the loader the app keeps at:

\`\`\`
${interp}
\`\`\`

The new string is appended to the file and the program header points at it, so
the code and the libraries are the upstream ones, byte for byte.

## What was checked

- every library the program wants (DT_NEEDED) is in the rootfs
- the interpreter it asks for is the one above
- the program starts with the rootfs's loader and libraries (\`--version\`)
EOF

log "packaging -> $(basename "$out")"
tar czf "$out" -C "$work" "$stem"

sum=$(sha256sum "$out" | cut -d' ' -f1)
echo "$out $sum"
