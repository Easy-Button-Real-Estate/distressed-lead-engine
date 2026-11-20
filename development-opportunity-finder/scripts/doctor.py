#!/usr/bin/env python3
"""Setup check. The launchers run it; you can too:
  Mac:      .venv/bin/python scripts/doctor.py --online
  Windows:  .venv\\Scripts\\python.exe scripts\\doctor.py --online

Checks Python, the packages, HTTPS certificates, (with --online) one public map server,
and whether the Claude Code command is installed. Prints plain-English fixes and saves
them to setup_check.txt. Standard library only, so it runs even when packages are missing.
"""
import argparse, datetime as dt, importlib, os, platform, shutil, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGES = [("yaml", "PyYAML"), ("pandas", "pandas"), ("numpy", "numpy"), ("openpyxl", "openpyxl"), ("PIL", "Pillow"), ("certifi", "certifi")]


def base_python():
    return os.path.realpath(getattr(sys, "_base_executable", "") or sys.executable)


def folder_problem(path):
    """Paths the kit should not run from: inside a zip preview / Temp copy, or a macOS translocated copy."""
    p = path.replace("\\", "/").lower()
    if ".zip/" in p or "/appdata/local/temp/" in p:
        return "Right-click the zip > Extract All first, to C:\\EBRE-Land, then run the starter from there."
    if "/apptranslocation/" in p:
        return "Move the whole folder to ~/EBRE-Land, then double-click start-mac.command there."
    return ""


def check(online=False):
    res = []  # (ok, label, fix)
    v = sys.version_info
    bp = base_python()
    if "windowsapps" in bp.lower():
        res.append((False, f"Python is the Microsoft Store stub ({bp})",
                    "Install Python from python.org/downloads (tick 'Add python.exe to PATH'), then run the starter again."))
    if bp == "/usr/bin/python3" and platform.system() == "Darwin":
        res.append((False, "Python is Apple's built-in /usr/bin/python3",
                    "Install Python from python.org/downloads (macOS installer), delete the .venv folder, then double-click start-mac.command."))
    fp = folder_problem(ROOT)
    res.append((not fp, f"Kit folder: {ROOT}", fp))
    try:
        t = os.path.join(ROOT, ".write_test")
        open(t, "w").close()
        os.remove(t)
        res.append((True, "Kit folder is writable", ""))
    except OSError:
        res.append((False, "Can't write to the kit folder",
                    "Mac: allow Terminal to access the folder when asked (or move the kit to ~/EBRE-Land). Windows: move it to C:\\EBRE-Land."))
    res.append((v >= (3, 10), f"Python {v.major}.{v.minor}.{v.micro} ({sys.executable})",
                "Install Python 3.10 or newer from python.org/downloads, then double-click the starter again."))
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    res.append((in_venv, "Running inside the kit's private .venv" if in_venv else "Not running inside .venv",
                "Double-click start-mac.command / start-windows.bat so it creates .venv, or use .venv's python."))
    missing = []
    for mod, pip_name in PACKAGES:
        try:
            importlib.import_module(mod)
        except Exception:
            missing.append(pip_name)
    res.append((not missing, "Packages installed" if not missing else "Missing packages: " + ", ".join(missing),
                "Run the starter again (it installs them), or: <python> -m pip install -r requirements.txt"))
    try:
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import _common
        _common.ssl_context()
        cert_ok, cert_msg = True, "HTTPS certificates ready (certifi)"
    except Exception as e:
        cert_ok, cert_msg = False, f"HTTPS certificates problem: {e}"
    res.append((cert_ok, cert_msg, "Run: <python> -m pip install certifi"))
    if online:
        try:
            import urllib.request
            with _common.urlopen(urllib.request.Request("https://imagery.nationalmap.gov/arcgis/rest/services?f=json",
                                                        headers={"User-Agent": "development-opportunity-finder-doctor"}), timeout=15) as r:
                r.read(200)
            res.append((True, "Internet: public map servers reachable", ""))
        except Exception as e:
            res.append((False, "Internet: could not reach the USGS map server (" + _common.friendly_error(e) + ")",
                        "County and map lookups need internet. The demo and scoring your own files still work offline. "
                        "On claude.ai (web) outside sites are blocked: use Claude Code on your computer."))
    if platform.system() == "Windows":
        gb = os.environ.get("CLAUDE_CODE_GIT_BASH_PATH") or next((p for p in (
            os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Git", "bin", "bash.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Git", "bin", "bash.exe")) if os.path.exists(p)), "")
        # informational only: without Git Bash, Claude Code uses PowerShell, which the kit also supports
        res.append((True, ("Git Bash found: " + gb) if gb else
                    "Git Bash not found: Claude Code will run commands in PowerShell (supported). Optional: install Git for Windows", ""))
    claude = shutil.which("claude")
    res.append((bool(claude), "Claude Code command found" if claude else "Claude Code is not installed (the 'claude' command)",
                "Install Claude Code from claude.com/claude-code (needs a paid Claude plan), then double-click the starter again."))
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--online", action="store_true", help="also test the internet connection to a public map server")
    ap.add_argument("--quiet-ok", action="store_true", help="print only problems")
    ap.add_argument("--no-claude-ok", action="store_true", help="a missing Claude Code is reported but does not fail the check (the starter handles it)")
    a = ap.parse_args(argv)
    res = check(a.online)
    if a.no_claude_ok:
        res = [(True, r[1] + " (the starter explains how to install it)", "") if (not r[0] and "Claude Code" in r[1]) else r for r in res]
    lines = [f"Setup check {dt.datetime.now().strftime('%Y-%m-%d %H:%M')} on {platform.system()} {platform.release()}"]
    for ok, label, fix in res:
        lines.append(("  OK   " if ok else "  FIX  ") + label + ("" if ok or not fix else "\n         -> " + fix))
    bad = [r for r in res if not r[0]]
    lines.append("All good. Say: run the demo" if not bad else f"{len(bad)} thing(s) to fix above. The rest of the kit still works where it can.")
    out_path = os.path.join(ROOT, "setup_check.txt")
    lines.append("Saved to: " + out_path)
    text = "\n".join(lines)
    try:
        with open(out_path, "w") as f:
            f.write(text + "\n")
    except OSError:
        pass
    if not (a.quiet_ok and not bad):
        print(text)
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
