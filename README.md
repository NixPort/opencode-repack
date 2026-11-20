# opencode-repack

Turns the upstream [opencode](https://github.com/anomalyco/opencode) CLI into a
package that runs in the nixport rootfs on a phone.

## The problem

The upstream binary is a plain Linux aarch64 program, and it asks for the
loader of a Linux system:

```
$ readelf -l opencode | grep interpreter
      [Requesting program interpreter: /lib/ld-linux-aarch64.so.1]
```

Android has no `/lib`, and the nixport guest is not a chroot: the guest sees
the phone's own root, where that loader is not. A program like that cannot be
started on the phone — the kernel looks for the interpreter, does not find it,
and the exec fails before the program itself ever runs:

```
sh: files/agent/opencode: inaccessible or not found
```

The libraries are the second half of the same story: the program wants libc,
libm and friends, and they live in the rootfs the app unpacks. A program that
wants a library the rootfs does not have dies with a message that looks like a
permission problem:

```
error while loading shared libraries: libc.so.6: cannot open shared object file: Permission denied
```

## The fix

The repack points the interpreter at the loader the app actually keeps, and
checks that every library the program wants is in the rootfs:

```
upstream opencode ──set PT_INTERP──▶ loader at the app's rootfs
                ──check DT_NEEDED──▶ every library is in the rootfs
                ──start it────────▶ on an arm64 runner, with the rootfs
```

The program itself is not touched: the new interpreter string is appended to
the file and the program header points at it, so the code and the libraries
are the upstream ones, byte for byte.

The build runs on an arm64 runner with the real rootfs, so a package is only
published after the repacked program has started with the rootfs's loader and
answered `--version`.

## Download

```bash
gh release download agent-latest -R NixPort/opencode-repack -p 'opencode-nx2a-*-arm64.tar.gz*'
sha256sum -c opencode-nx2a-*-arm64.tar.gz.sha256
```

The releases:

| release | what it is |
|---|---|
| `agent-latest` | the newest repacked package (the rolling one) |
| `repack-opencode-v<version>` | a pinned upstream version |

## Install

The package holds the program, a configuration example and the steps that put
it on a phone:

```
opencode-nx2a-v1.19.6-arm64/
├── opencode            the program, with its interpreter set
├── opencode.json.example   a provider configuration (an Ark endpoint, to edit)
├── install.md          how to put it on the phone and run it
└── PROVENANCE.md       where it came from and what was changed
```

The short version: push `opencode` into the app's own folder with `adb
run-as`, point a configuration at a model endpoint, and run it inside the guest
environment the app sets up. `install.md` has the commands.

## How the build works

`scripts/build.sh` does the work, and a recipe says where the upstream comes
from (`recipes/opencode.yml`):

1. download the upstream asset, and verify its checksum when the recipe pins
   one
2. unpack it and point the interpreter at the app's loader
3. check every library the program wants against the rootfs
4. start the program with the rootfs's loader and libraries (`--version`)
5. pack it with the configuration example, the install steps and the
   provenance

The workflow runs it every day and whenever it is triggered by hand, so a new
upstream release is picked up within a day. The daily run asks the upstream
for its newest release; the pinned version in the recipe is the one that was
tested on a phone.

## Provenance

Every package carries `PROVENANCE.md`: the upstream repository, the release,
the asset, the checksum of the downloaded bytes, and the one thing the repack
changed.

## Related

- [NixPort/nixport-rootfs](https://github.com/NixPort/nixport-rootfs) — the rootfs
  the payload carries (the libraries and the loader the program needs)
- [NixPort/appimage-repack](https://github.com/NixPort/appimage-repack) — the
  same idea for upstream AppImages
