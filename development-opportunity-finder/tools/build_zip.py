"""Build development-opportunity-finder.zip from this kit folder.

  python tools/build_zip.py [<kit_dir>] <out.zip>

- Keeps Unix permissions: start-mac.command and *.sh are stored executable (0755), everything else 0644.
- Line endings are forced: .bat -> CRLF (cmd.exe misreads labels in LF batch files), .command and .sh -> LF
  (bash fails on CRLF with "$'\\r': command not found").
- Skips .venv, out, out_demo, __pycache__, .git, .github, setup_check.txt, .DS_Store, *.pyc,
  and development-opportunity-finder.zip (the live download; it must not be nested inside the kit zip).
- Entries are sorted by name and every timestamp is 1980-01-01, so rebuilding one commit
  produces the same bytes and the same SHA-256.
tests/test_pipeline.py opens the built zip and checks the line endings and exec bits."""
import os
import stat
import sys
import zipfile

SKIP_DIRS = {".venv", "out", "out_demo", "__pycache__", ".git", ".github"}
SKIP_FILES = {"setup_check.txt", ".DS_Store", "development-opportunity-finder.zip"}
CRLF = (".bat", ".cmd")
LF_EXEC = (".command", ".sh")
# ZIP stores DOS dates and cannot go earlier than this. Pinning it keeps the archive reproducible.
FIXED_DATE = (1980, 1, 1, 0, 0, 0)


def fix_eol(name, data):
    if name.lower().endswith(CRLF):
        return data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    if name.lower().endswith(LF_EXEC):
        return data.replace(b"\r\n", b"\n")
    return data


def _info(name, mode, compress_type):
    zi = zipfile.ZipInfo(name, FIXED_DATE)
    zi.create_system = 3  # Unix, so the mode above is honored on extract
    zi.external_attr = mode
    zi.compress_type = compress_type
    zi.flag_bits = 0
    zi.extra = b""
    return zi


def build(root, out):
    root = os.path.abspath(root)
    base = os.path.dirname(root)
    dirs = []
    files = []
    for d, sub, fnames in os.walk(root):
        sub[:] = [x for x in sub if x not in SKIP_DIRS]
        dirs.append(os.path.relpath(d, base).replace(os.sep, "/"))
        for fn in fnames:
            if fn in SKIP_FILES or fn.endswith(".pyc"):
                continue
            files.append(os.path.join(d, fn))
    n = 0
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for rel_d in sorted(set(dirs)):
            zi = _info(rel_d + "/", (0o40755 << 16) | 0x10, zipfile.ZIP_STORED)
            z.writestr(zi, b"")
        for p in sorted(files, key=lambda p: os.path.relpath(p, base).replace(os.sep, "/")):
            fn = os.path.basename(p)
            rel = os.path.relpath(p, base).replace(os.sep, "/")
            execb = fn.lower().endswith(LF_EXEC) or bool(os.stat(p).st_mode & stat.S_IXUSR)
            mode = (stat.S_IFREG | (0o755 if execb else 0o644)) << 16
            zi = _info(rel, mode, zipfile.ZIP_DEFLATED)
            with open(p, "rb") as f:
                z.writestr(zi, fix_eol(fn, f.read()), compresslevel=6)
            n += 1
    return n


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) == 1:
        args = [os.path.dirname(os.path.dirname(os.path.abspath(__file__)))] + args
    if len(args) != 2:
        raise SystemExit(__doc__)
    print("wrote", args[1], "(%d files)" % build(*args))
