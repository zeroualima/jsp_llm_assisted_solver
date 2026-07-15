"""
Download and convert JSPLib benchmark instances from the ScheduleOpt repo.

Clones the repo locally (it's small, ~few MB), reads instances and BKS,
converts to internal project format, writes to output directory.

Usage:
    python3 download_benchmarks.py --output-dir ~/jsp_records/benchmarks

Requires: git on PATH.
"""

import json
import os
import argparse
import subprocess
import shutil
import tempfile
from collections import defaultdict

REPO_URL = "https://github.com/ScheduleOpt/benchmarks.git"
TARGET_FAMILIES = {"Taillard", "DemirkolMehtaUzsoy", "StorerWuVaccari"}


def jsplib_to_internal(raw):
    n_jobs = raw["jobs"]
    n_machines = raw["machines"]
    durations = [[0] * n_machines for _ in range(n_jobs)]
    machines  = [[0] * n_machines for _ in range(n_jobs)]
    for entry in raw["data"]:
        j  = entry["job"]
        op = entry["operation"]
        durations[j][op] = entry["duration"]
        machines[j][op]  = entry["machine"]
    return {
        "name":         raw["instance"],
        "family":       raw.get("family_long", ""),
        "num_jobs":     n_jobs,
        "num_machines": n_machines,
        "durations":    durations,
        "machines":     machines,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="./benchmarks")
    parser.add_argument("--families", nargs="+", default=sorted(TARGET_FAMILIES))
    parser.add_argument("--keep-clone", action="store_true",
                        help="Don't delete the cloned repo after conversion")
    args = parser.parse_args()

    instances_dir = os.path.join(args.output_dir, "instances")
    os.makedirs(instances_dir, exist_ok=True)

    clone_dir = tempfile.mkdtemp(prefix="jsplib_clone_")
    try:
        print(f"Cloning {REPO_URL} into {clone_dir} ...")
        subprocess.run(
            ["git", "clone", "--depth=1", REPO_URL, clone_dir],
            check=True
        )
        print("Clone done.\n")

        # ---- BKS ----
        bks_src = os.path.join(clone_dir, "jobshop", "solutions", "bks.json")
        with open(bks_src) as f:
            bks_raw = json.load(f)   # list of dicts

        # Build lookup: instance_name -> upper_bound (best known makespan)
        bks_lookup = {}
        for entry in bks_raw:
            name = entry["instance"]
            ub   = entry.get("upper_bound")
            if ub is not None:
                bks_lookup[name] = int(ub)

        bks_dst = os.path.join(args.output_dir, "bks.json")
        shutil.copy(bks_src, bks_dst)
        print(f"BKS: {len(bks_lookup)} entries -> {bks_dst}")

        # ---- Instances ----
        json_dir = os.path.join(clone_dir, "jobshop", "instances", "json")
        all_files = sorted(os.listdir(json_dir))
        # Filter by reading the "family_long" field from each JSON file rather than
        # matching the filename prefix -- "ta" prefix would also select "tai_*"
        # (Da Col & Teppan 2022 instances), which we don't want.
        target_files = []
        for fname in all_files:
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(json_dir, fname)) as _f:
                    _preview = json.load(_f)
                if _preview.get("family_long", "") in set(args.families):
                    target_files.append(fname)
            except Exception:
                continue
        target_files.sort()
        print(f"Instance files matching families {args.families}: {len(target_files)}\n")

        index = []
        ok = 0
        failed = 0

        for fname in target_files:
            src = os.path.join(json_dir, fname)
            try:
                with open(src) as f:
                    raw = json.load(f)
                internal = jsplib_to_internal(raw)
                name   = internal["name"]
                if internal["family"] == "DemirkolMehtaUzsoy" :
                    family = "dmu"
                elif internal["family"] == "Taillard" :
                    family = "ta"
                else :
                    family = "swv"

                # Attach BKS and difficulty from bks_raw
                bks_entry = next(
                    (e for e in bks_raw if e["instance"] == name), {}
                )
                internal["bks"]        = bks_lookup.get(name, -1)
                internal["difficulty"] = bks_entry.get("status", "unknown")

                dst = os.path.join(instances_dir, f"{name}.json")
                with open(dst, "w") as f:
                    json.dump(internal, f)

                index.append({
                    "name":         name,
                    "family":       family,
                    "num_jobs":     internal["num_jobs"],
                    "num_machines": internal["num_machines"],
                    "difficulty":   internal["difficulty"],
                    "bks":          internal["bks"],
                    "path":         dst,
                })
                ok += 1
            except Exception as e:
                print(f"  FAILED: {fname} -- {e}")
                failed += 1

        index_path = os.path.join(args.output_dir, "index.json")
        with open(index_path, "w") as f:
            json.dump(index, f, indent=2)

        print(f"\nConverted: {ok} | Failed: {failed}")
        print(f"Index -> {index_path}")

        # Summary table
        by_fam  = defaultdict(lambda: defaultdict(int))
        for e in index:
            by_fam[e["family"]][e["difficulty"]] += 1

        print()
        print(f"{'family':<8}{'toy':<6}{'easy':<6}{'medium':<8}"
              f"{'hard':<6}{'open':<6}{'closed':<8}{'total':<6}")
        print("-" * 56)
        for fam in sorted(by_fam):
            d     = by_fam[fam]
            total = sum(d.values())
            print(f"{fam:<8}{d.get('toy',0):<6}{d.get('easy',0):<6}"
                  f"{d.get('medium',0):<8}{d.get('hard',0):<6}"
                  f"{d.get('open',0):<6}{d.get('closed',0):<8}{total:<6}")

        no_bks = sum(1 for e in index if e["bks"] < 0)
        if no_bks:
            print(f"\nWARNING: {no_bks} instance(s) have no BKS entry -- "
                  "gap% will be reported as -1 for those.")

    finally:
        if args.keep_clone:
            print(f"\nClone kept at: {clone_dir}")
        else:
            shutil.rmtree(clone_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
