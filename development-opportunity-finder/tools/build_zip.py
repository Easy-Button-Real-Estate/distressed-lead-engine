"""Build development-opportunity-finder.zip from this kit folder.

  python tools/build_zip.py [<kit_dir>] <out.zip>

- Keeps Unix permissions: start-mac.command and *.sh are stored executable (0755), everything else 0644.
- Line endings are forced: .bat -> CRLF (cmd.exe misreads labels in LF batch files), .command and .sh -> LF
  (bash fails on CRLF with "$'\\r': command not found").
- Skips .venv, out, out_demo, __pycache__, .git, .github, setup_check.txt, .DS_Store and *.pyc.
tests/test_pipeline.py opens the built zip and checks the line endings and exec bits."""
import os
import stat
import sys
import zipfile

SKIP_DIRS = {".venv", "out", "out_demo", "__pycache__", ".git", ".github"}
SKIP_FILES = {"setup_check.txt", ".DS_Store"}
CRLF = (".bat", ".cmd")
LF_EXEC = (".command", ".sh")


def fix_eol(name, data):
    if name.lower().endswith(CRLF):
        return data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    if name.lower().endswith(LF_EXEC):
        return data.replace(b"\r\n", b"\n")
    return data


def build(root, out):
    root = os.path.abspath(root)
    base = os.path.dirname(root)
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for d, dirs, files in os.walk(root):
            dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS)
            rel_d = os.path.relpath(d, base).replace(os.sep, "/")
            zi = zipfile.ZipInfo(rel_d + "/")
            zi.external_attr = (0o40755 << 16) | 0x10
            zi.create_system = 3
            z.writestr(zi, "")
            for fn in sorted(files):
                if fn in SKIP_FILES or fn.endswith(".pyc"):
                    continue
                p = os.path.join(d, fn)
                rel = os.path.relpath(p, base).replace(os.sep, "/")
                mode = os.stat(p).st_mode
                execb = fn.lower().endswith(LF_EXEC) or bool(mode & stat.S_IXUSR)
                zi = zipfile.ZipInfo.from_file(p, rel)
                zi.create_system = 3
                zi.external_attr = (stat.S_IFREG | (0o755 if execb else 0o644)) << 16
                zi.compress_type = zipfile.ZIP_DEFLATED
                with open(p, "rb") as f:
                    z.writestr(zi, fix_eol(fn, f.read()))
                n += 1
    return n


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) == 1:
        args = [os.path.dirname(os.path.dirname(os.path.abspath(__file__)))] + args
    if len(args) != 2:
        raise SystemExit(__doc__)
    print("wrote", args[1], "(%d files)" % build(*args))
