"""Erzeugt die Sprachaufnahmen der App mit Kokoro (britisch und amerikanisch).
Laeuft in GitHub Actions. Bereits vorhandene Dateien werden uebersprungen."""
import json, os, re, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
src = open("content.js", encoding="utf-8").read()
C = json.loads(src[src.index("=") + 1:].strip().rstrip(";"))


def norm(t):
    return re.sub(r"\s+", " ", t.replace("_", " ")).strip()


def fnv(t):  # identisch zur Funktion fnv() in index.html
    h = 0x811C9DC5
    for b in t.encode("utf-8"):
        h ^= b
        h = (h * 0x01000193) & 0xFFFFFFFF
    return "%08x" % h


texts = set()


def add(t):
    if t and norm(t):
        texts.add(norm(t))


for tp in C["topics"]:
    for w in tp["w"]:
        add(w[0]); add(w[2])
for r in C["texts"]:
    for s in r["s"]:
        add(s[0])
core = re.compile(r"^([^A-Za-z0-9'_\-é]*)(.*?)([^A-Za-z0-9'_\-é]*)$")
for r in C.get("wtexts", []):
    for s in r["s"]:
        add(s[0])
        for tok in s[0].split(" "):
            m = core.match(tok)
            if m and m.group(2):
                add(m.group(2))
for d in C["dialogs"]:
    for st in d["st"]:
        add(st[0])
        for o in st[2]:
            add(o[0])
for g in C.get("grammar", []):
    for e in g["eg"]:
        add(e[0])
    for q in g["q"]:
        add(q[0].replace("___", q[1]))
for t in ["Hello! How are you today?", "Hello! This is a test."]:
    add(t)

keys = {}
for t in texts:
    k = fnv(t)
    if k in keys and keys[k] != t:
        sys.exit(f"Hash-Kollision: {t!r} / {keys[k]!r}")
    keys[k] = t
print(f"{len(texts)} Texte", flush=True)
if "--count" in sys.argv:
    sys.exit(0)

import numpy as np
import soundfile as sf
from kokoro import KPipeline

VOICES = {"gb": ("b", "bf_emma"), "us": ("a", "af_heart")}
manifest = {}
for acc, (lang, voice) in VOICES.items():
    os.makedirs(f"audio/{acc}", exist_ok=True)
    todo = [t for t in sorted(texts) if not os.path.exists(f"audio/{acc}/{fnv(t)}.mp3")]
    print(f"{acc}: {len(todo)} neue Aufnahmen", flush=True)
    pipe = KPipeline(lang_code=lang) if todo else None
    t0 = time.time()
    for i, t in enumerate(todo):
        try:
            chunks = []
            for _, _, a in pipe(t, voice=voice, speed=0.9):
                if a is not None:
                    chunks.append(a.numpy() if hasattr(a, "numpy") else np.asarray(a))
            if not chunks:
                print("  leer:", t, flush=True)
                continue
            audio = np.concatenate(chunks).astype(np.float32)
            audio = np.concatenate([np.zeros(2400, np.float32), audio, np.zeros(3600, np.float32)])
            sf.write("/tmp/clip.wav", audio, 24000)
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", "/tmp/clip.wav", "-ac", "1",
                            "-ar", "24000", "-b:a", "40k", f"audio/{acc}/{fnv(t)}.mp3"], check=True)
        except Exception as e:
            print("  Fehler bei", repr(t), e, flush=True)
        if i % 100 == 0:
            print(f"  {acc} {i}/{len(todo)}  {time.time() - t0:.0f}s", flush=True)
    manifest[acc] = sorted(k for k in keys if os.path.exists(f"audio/{acc}/{k}.mp3"))

with open("audio/index.json", "w") as f:
    json.dump(manifest, f, separators=(",", ":"))
print({a: len(v) for a, v in manifest.items()}, flush=True)
