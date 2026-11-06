"""Command line: ``python -m data_generator <command>``.

Commands::

    catalogue                      write data/catalogue/catalogue.csv
    planted                        write data/projects/test/PLANTED.md
    build --set showcase|test|reworded|training|all [--count N] [--workers N] [--root PATH]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from data_generator import sets
from data_generator.catalogue import write_catalogue


def _size_mb(path: Path) -> float:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) / 1_000_000 if path.exists() else 0.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m data_generator", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("catalogue", help="write the parts catalogue CSV")
    sub.add_parser("planted", help="write PLANTED.md for the test set")
    sub.add_parser("diagnose-showcase", help="rebuild the showcase in a temp folder and report pixel differences")
    build = sub.add_parser("build", help="build a data set")
    build.add_argument("--set", required=True, choices=["showcase", "test", "reworded", "training", "all"])
    build.add_argument("--count", type=int, default=None, help="build only the first N items of the set")
    build.add_argument("--workers", type=int, default=2, help="parallel processes (default 2, for 8 GB RAM)")
    build.add_argument("--root", type=Path, default=sets.DATA, help="data folder (default: the repo's data/)")
    args = parser.parse_args(argv)

    if args.command == "catalogue":
        write_catalogue(sets.DATA / "catalogue" / "catalogue.csv")
        print("wrote data/catalogue/catalogue.csv")
        return 0
    if args.command == "planted":
        target = sets.DATA / "projects" / "test" / "PLANTED.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(sets.planted_markdown().encode("utf-8"))
        print(f"wrote {target.relative_to(sets.REPO)}")
        return 0

    if args.command == "diagnose-showcase":
        from data_generator import diagnose

        return diagnose.main()

    root: Path = args.root
    chosen = ["showcase", "test", "training"] if args.set == "all" else [args.set]
    for name in chosen:
        if name == "showcase":
            jobs, folder = [sets.showcase_job(root)], root / "projects" / "showcase"
        elif name == "test":
            jobs, folder = sets.testset_jobs(root, args.count or sets.TEST_COUNT), root / "projects" / "test"
        elif name == "reworded":
            jobs, folder = (sets.reworded_jobs(root, args.count or sets.REWORDED_COUNT),
                            root / "projects" / "reworded")
        else:
            jobs, folder = sets.training_jobs(root, args.count or sets.TRAINING_COUNT), root / "training"
        start = time.perf_counter()
        extra = None
        if name == "showcase":
            from PIL import Image

            from data_generator.diagnose import DEGRADED, clean_render_hashes, pixel_sha256, traced_showcase_build

            # Same build as run_jobs, plus pixel fingerprints after every step, so a
            # build on another CPU can tell which step first gives different pixels.
            steps = traced_showcase_build(folder)
            extra = {"clean_render_sha256": clean_render_hashes(folder),
                     "degraded_pixel_sha256": {n: pixel_sha256(Image.open(folder / n)) for n in DEGRADED},
                     "degraded_step_sha256": steps}
        else:
            sets.run_jobs(jobs, workers=args.workers)
        sets.write_build_info(folder, extra)
        took = time.perf_counter() - start
        print(f"{name}: {len(jobs)} item(s) in {took:.1f} s, {_size_mb(folder):.1f} MB in "
              f"{folder.relative_to(root.parent) if root == sets.DATA else folder}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
