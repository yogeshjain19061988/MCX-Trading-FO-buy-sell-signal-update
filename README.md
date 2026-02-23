# MCX-Trading-buy-sell-signal-update
MCX Trading buy sell signal update: this will you entry and exit signal for NG future trade.

#make the applcation independent
1.  pip install pyinstaller
2.  pyi-makespec MCX_Trade_Signal_Updater.py
3. update MCX_Trade_Signal_Updater.spec file below code

a = Analysis(
    ['MCX_Trade_Signal_Updater.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

from PyInstaller.utils.hooks import collect_all
import pkg_resources

hiddenimports = []
datas = []
binaries = []

for pkg in pkg_resources.working_set:
    try:
        collected = collect_all(pkg.key)
        datas += collected[0]
        binaries += collected[1]
        hiddenimports += collected[2]
    except:
        pass


4.  pyinstaller MCX_Trade_Signal_Updater.spec --clean
