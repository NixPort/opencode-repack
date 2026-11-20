# Installing the package on a phone

The program in this package is a Linux aarch64 binary with its interpreter
pointed at the rootfs the app unpacks. It runs **inside** the app's folder:
the app is what gives it the rootfs, the libraries and the loader.

## What you need

- the app installed, with its environment unpacked (the first start does it)
- a debug build for the `run-as` steps below (a release build cannot be
  `run-as`'d)
- `adb` on the computer, the phone connected

## 1. Push the program into the app's folder

```bash
tar xzf opencode-nx2a-<version>-arm64.tar.gz
adb push opencode-nx2a-<version>-arm64/opencode /data/local/tmp/opencode
adb shell run-as com.nx.android mkdir -p files/agent
adb shell run-as com.nx.android sh -c 'cat > files/agent/opencode' < /data/local/tmp/opencode
adb shell run-as com.nx.android chmod 755 files/agent/opencode
```

`cp` does not work here: the file in `/data/local/tmp` cannot be read by the
app's user, so it goes in through standard input.

## 2. Give it a configuration

```bash
adb shell run-as com.nx.android mkdir -p files/home/.config/opencode
adb shell run-as com.nx.android sh -c 'cat > files/home/.config/opencode/opencode.json' \
    < opencode.json.example
```

The example points at a Volcengine Ark endpoint. Put your own key in the
environment (`ARK_API_KEY`) or in the file — a key is a secret, so keep it out
of the repository and out of chats.

## 3. Run it

The guest environment the app sets up for its own programs is what the agent
needs as well:

```bash
adb shell "run-as com.nx.android sh -c '
  export HOME=/data/data/com.nx.android/files/home
  export TMPDIR=/data/data/com.nx.android/files/tmp
  export PATH=/data/data/com.nx.android/files/rootfs/usr/bin:/usr/bin:/bin
  export LD_LIBRARY_PATH=/data/data/com.nx.android/files/rootfs/usr/lib/aarch64-linux-gnu:/data/data/com.nx.android/files/rootfs/usr/lib
  export PYTHONHOME=/data/data/com.nx.android/files/rootfs/usr
  cd /data/data/com.nx.android/files/tool
  files/agent/opencode --version
'"
```

`LD_LIBRARY_PATH` is not optional: without it the loader looks for libc in the
phone's own `/lib`, which has none, and the program dies with
`libc.so.6: cannot open shared object file: Permission denied`.

For a real turn, the agent needs a model endpoint. Point the configuration at
one and run it headless:

```bash
files/agent/opencode run --model ark/doubao-seed "what can you do?"
```

## 4. Take it away again

```bash
adb shell run-as com.nx.android rm -rf files/agent
```
