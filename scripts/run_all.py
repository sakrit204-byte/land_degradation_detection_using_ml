"""End-to-end pipeline after downloads: dataset -> train -> predict -> corroborate -> figures -> export.
Each stage logs to logs/<stage>.log. Usage: python scripts/run_all.py [stage ...]"""
import subprocess, sys, time
PY = sys.executable
STAGES = [("dataset", [PY, "-u", "-m", "care_ew.dataset"]),
          ("train", [PY, "-u", "-m", "care_ew.train"]),
          ("predict", [PY, "-u", "-m", "care_ew.predict"]),
          ("corroborate", [PY, "-u", "-m", "care_ew.corroborate"]),
          ("figures", [PY, "-u", "-m", "care_ew.figures"]),
          ("export", [PY, "-u", "-m", "care_ew.export"])]
want = sys.argv[1:]
for name, cmd in STAGES:
    if want and name not in want:
        continue
    t = time.time()
    with open(f"logs/{name}.log", "w") as f:
        r = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)
    print(f"{name}: exit {r.returncode} in {time.time() - t:.0f}s", flush=True)
    if r.returncode:
        sys.exit(r.returncode)
