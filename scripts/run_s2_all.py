"""Build S2 monthly cubes for all AOIs, 2 AOIs in parallel (memory)."""
import sys, logging
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0, ".")
from care_ew.config import AOIS
from care_ew import s2
if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    keys = sys.argv[1:] or [a.key for a in AOIS]
    with ProcessPoolExecutor(2) as ex:
        for r in ex.map(s2.build, keys): print("DONE", r, flush=True)
