#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
bundle=$(pwd -P)
if [[ ! -f $bundle/bundle.json ]]; then
    printf '%s\n' 'Download and extract the installer archive from GitHub Releases; source checkout has no binary payloads.' >&2
    exit 1
fi
if [[ ${1:-} == --check ]]; then
    exec python3 "$bundle/deploy/bootstrap.py" --root "${XDG_DATA_HOME:-$HOME/.local/share}/stationbot" --bundle "$bundle" "$@"
fi
if ! command -v apt-get >/dev/null; then
    printf '%s\n' 'Supported automatic dependency installation: Debian 12 / Ubuntu 22.04 or newer.' >&2
    exit 1
fi
if [[ $(id -u) == 0 ]]; then
    apt-get update
    apt-get install -y python3 python3-venv python3-pip ffmpeg espeak-ng adb ca-certificates
    id stationbot >/dev/null 2>&1 || useradd --system --create-home --home-dir /var/lib/stationbot --shell /usr/sbin/nologin stationbot
    root=/opt/stationbot-oneclick
    if [[ -d $root && ! -f $root/managed-v1 && -n $(ls -A "$root") ]]; then
        printf '%s\n' 'Existing unmanaged install directory retained.' >&2; exit 1
    fi
    install -d -m 700 -o stationbot -g stationbot "$root"
    # /root or a private downloads directory may not be accessible to the
    # service user. Copy only manifest-verified release files into managed data.
    python3 - "$bundle" "$root" <<'PY'
import importlib.util,os,pwd,shutil,sys
from pathlib import Path
source,root=map(Path,sys.argv[1:])
spec=importlib.util.spec_from_file_location('bootstrap',source/'deploy/bootstrap.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
manifest=module.verify_bundle(source)
account=pwd.getpwnam('stationbot')
(root/'managed-v1').touch(mode=0o600)
for name in [*manifest['files'],'bundle.json']:
    target=root/'bundle'/name
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source/name,target)
os.chown(root/'managed-v1',account.pw_uid,account.pw_gid,follow_symlinks=False)
for base,dirs,files in os.walk(root/'bundle',followlinks=False):
    if not Path(base).resolve().is_relative_to(root.resolve()):raise RuntimeError('Escaping bundle directory')
    os.chown(base,account.pw_uid,account.pw_gid,follow_symlinks=False)
    for name in files:os.chown(Path(base)/name,account.pw_uid,account.pw_gid,follow_symlinks=False)
PY
    runuser -u stationbot -- python3 "$root/bundle/deploy/bootstrap.py" --root "$root" --bundle "$root/bundle" --no-service --no-start "$@"
    if [[ " $* " != *' --prepare-only '* && " $* " != *' --no-service '* ]]; then
        python3 "$root/bundle/deploy/bootstrap.py" --root "$root" --register-system-service "$@"
    fi
else
    sudo apt-get update
    sudo apt-get install -y python3 python3-venv python3-pip ffmpeg espeak-ng adb ca-certificates
    python3 "$bundle/deploy/bootstrap.py" --root "${XDG_DATA_HOME:-$HOME/.local/share}/stationbot" --bundle "$bundle" "$@"
    if [[ " $* " != *' --prepare-only '* && " $* " != *' --no-service '* ]]; then
        sudo loginctl enable-linger "$(id -un)"
    fi
fi
