"""Create a tiny standard-library zipapp and a self-installing Windows command."""

import base64
import hashlib
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def build():
    version = re.search(r'__version__ = "([^"]+)"', (ROOT / "anviroute/__init__.py").read_text()).group(1)
    output = ROOT / 'dist'
    output.mkdir(exist_ok=True)
    app = output / 'anviroute.pyz'
    with zipfile.ZipFile(app, 'w', zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr('__main__.py', 'from anviroute.cli import main\nraise SystemExit(main())\n')
        for source in sorted((ROOT / 'anviroute').glob('*.py')):
            bundle.write(source, 'anviroute/' + source.name)
    payload = app.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    installer = (ROOT / 'install.ps1').read_text(encoding='utf-8')
    bootstrap = r'''@echo off
setlocal
set "ANVIROUTE_BOOTSTRAP=%~f0"
if not defined ANVIROUTE_INSTALL_ROOT set "ANVIROUTE_INSTALL_ROOT=%LOCALAPPDATA%\AnviRoute"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$s=[IO.File]::ReadAllText($env:ANVIROUTE_BOOTSTRAP); $p=[regex]::Match($s,'(?ms)^#BEGIN_POWERSHELL\r?\n(.*?)^#END_POWERSHELL'); $b=[regex]::Match($s,'(?ms)^#BEGIN_PAYLOAD\r?\n(.*?)^#END_PAYLOAD'); & ([scriptblock]::Create($p.Groups[1].Value)) -PayloadBase64 $b.Groups[1].Value -PayloadHash '__DIGEST__'"
if errorlevel 1 goto failed
call "%ANVIROUTE_INSTALL_ROOT%\bin\anviroute.cmd" %*
exit /b %ERRORLEVEL%
:failed
if "%~1"=="" pause
exit /b 1
#BEGIN_POWERSHELL
__INSTALLER__
#END_POWERSHELL
#BEGIN_PAYLOAD
__PAYLOAD__
#END_PAYLOAD
'''
    encoded = base64.b64encode(payload).decode()
    encoded = '\n'.join(encoded[i:i + 100] for i in range(0, len(encoded), 100))
    bootstrap = bootstrap.replace('__DIGEST__', digest).replace('__INSTALLER__', installer.rstrip()).replace('__PAYLOAD__', encoded)
    command = output / 'AnviRoute.cmd'
    command.write_bytes(bootstrap.replace('\n', '\r\n').encode('utf-8'))
    # The optional ZIP has only the app, installer, and license, not developer files.
    archive = output / 'AnviRoute-Windows.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
        for path, name in ((command, 'AnviRoute.cmd'), (ROOT / 'LICENSE', 'LICENSE')):
            bundle.write(path, 'AnviRoute/' + name)
    checksums = output / 'SHA256SUMS.txt'
    checksums.write_text(''.join(f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n'
                                 for path in (command, app, archive)), encoding='utf-8')
    print(f'AnviRoute {version}: single download {command.stat().st_size:,} bytes; installed app {app.stat().st_size:,} bytes')


if __name__ == '__main__':
    build()
