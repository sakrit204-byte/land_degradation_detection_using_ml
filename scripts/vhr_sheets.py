"""Blind review pass helpers (D-029). Never reads key.json.

  python scripts/vhr_sheets.py sheets [WHO]       -> data/vhr/sheets/sheet_NNN.png for pairs WHO has not answered yet
  python scripts/vhr_sheets.py answer WHO id=a ... -> record answers (a in yes/no/unsure/nodata) in data/vhr/answers.json

Pairs come from data/vhr/pairs.json, or, while the fetch is still running, from its log (logs/vhr_fetch.log).
Sheets show 3 before|after pairs each, labelled only by pair id and acquisition dates."""
import sys, json, re
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
VHR = ROOT / "data" / "vhr"; OUT = VHR / "sheets"; ANS = VHR / "answers.json"
PER, W = 3, 384


def pairs():
    f = VHR / "pairs.json"
    if f.exists():
        return [(p["id"], p["before"]["date"], p["after"]["date"]) for p in json.load(open(f))["pairs"]]
    out = []
    for line in open(ROOT / "logs" / "vhr_fetch.log"):
        m = re.search(r"\] ([0-9a-f]{8}) before (\d+) after (\d+)", line)
        if m and (VHR / "chips" / f"{m.group(1)}_b.png").exists():
            out.append(m.groups())
    return out


def answers():
    return json.load(open(ANS)) if ANS.exists() else {}


def sheets(who="AI-pilot"):
    done = answers().get(who, {})
    todo = [p for p in pairs() if p[0] not in done]
    OUT.mkdir(exist_ok=True)
    for f in OUT.glob("*.png"):
        f.unlink()
    for s in range(0, len(todo), PER):
        grp = todo[s:s + PER]
        sheet = Image.new("RGB", (2 * W + 8, len(grp) * (W + 22)), (20, 20, 20))
        d = ImageDraw.Draw(sheet)
        for k, (pid, b, a) in enumerate(grp):
            y = k * (W + 22)
            d.text((4, y + 4), f"{pid}   before {b}   |   after {a}", fill=(255, 255, 255))
            for j, side in enumerate("ab"):
                sheet.paste(Image.open(VHR / "chips" / f"{pid}_{side}.png").resize((W, W)), (j * (W + 8), y + 20))
        sheet.save(OUT / f"sheet_{s // PER + 1:03d}.png")
    print(len(todo), "unanswered pairs ->", (len(todo) + PER - 1) // PER, "sheets")


def answer(who, *kv):
    d = answers()
    for x in kv:
        pid, a = x.split("=")
        assert a in ("yes", "no", "unsure", "nodata"), x
        d.setdefault(who, {})[pid] = a
    ANS.write_text(json.dumps(d, indent=1), encoding="utf-8")
    print(who, len(d[who]), "answers")


if __name__ == "__main__":
    {"sheets": sheets, "answer": answer}[sys.argv[1]](*sys.argv[2:])
