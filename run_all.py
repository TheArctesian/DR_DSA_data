"""run_all.py - run every topic script in sequence.

    python3 run_all.py            # all scripts
    python3 run_all.py money trust  # a subset

Each script is independent; this is only a convenience wrapper.
"""
import importlib
import sys
import time
import traceback

ORDER = ["sources", "geography", "money", "structure", "foreign", "people", "trust", "timeline", "quality"]


def main(names=None):
    names = names or ORDER
    status = []
    for name in names:
        t = time.time()
        print("\n" + "=" * 78 + f"\n# {name}.py\n" + "=" * 78)
        try:
            importlib.import_module(name).main()
            ok = "ok"
        except Exception:
            traceback.print_exc()
            ok = "FAILED"
        status.append((name, ok, time.time() - t))
    print("\n" + "=" * 78)
    for name, ok, secs in status:
        print(f"{name:12s} {ok:7s} {secs:5.1f}s")


if __name__ == "__main__":
    main(sys.argv[1:] or None)
