"""
E7b — Is local/global disagreement Monte Carlo noise of the global criterion?

For states reached by the c-optimal policy (stages 0 and 3) in every E7 cell, the global
EVSI criterion is computed twice with K = 16 (independent seeds) and once with K = 64
(reference). Compares self-disagreement of the K = 16 global choice with its disagreement
with the local c-optimal choice.

전제:
  config.yaml (e7 section)
출력:
  results/e7b_noise.csv
  reports/e7b_noise.md
"""

from __future__ import annotations

import os

os.environ.setdefault("OMP_NUM_THREADS", "1")

import sys  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import e7_adaptive as e7  # noqa: E402

from decision_id import adaptive as ad  # noqa: E402

SEED = 9300
REPS = 3


def main() -> None:
    t0 = time.time()
    print("=== E7b global-criterion noise ===")
    rows = []
    for k, (mname, truth, target) in enumerate(tuple(c) for c in e7.E7["cells"]):
        model = e7.make_model(mname)
        for r in range(REPS):
            seed = int(np.random.SeedSequence([SEED, k, r]).generate_state(1)[0])
            s = model.init_state(np.random.default_rng(seed), truth, stages=e7.E7["stages"])
            for stage in range(4):
                if stage in (0, 3):
                    post = model.fit(s)
                    loc = ad.local_criteria(model, target, post, s, np.random.default_rng(seed + 1))
                    cl = max(model.sources, key=lambda e: loc["copt"][e])
                    ch = []
                    for kk, K in enumerate((16, 16, 64)):
                        g = ad.global_criteria(
                            model, target, post, s, np.random.default_rng([seed, stage, kk]), K
                        )
                        ch.append(max(model.sources, key=lambda e: g["evsi"][e]))
                    rows.append(
                        {
                            "model": mname,
                            "truth": truth,
                            "target": target,
                            "rep": r,
                            "stage": stage,
                            "local": cl,
                            "g16a": ch[0],
                            "g16b": ch[1],
                            "g64": ch[2],
                            "margin": loc["margin"],
                            "kappa": loc["kappa"],
                        }
                    )
                    print(
                        f"  {mname}/{truth}/{target} r{r} s{stage}: local={cl} g16={ch[0]},"
                        f"{ch[1]} g64={ch[2]} ({time.time() - t0:.0f}s)"
                    )
                post = model.fit(s)
                loc = ad.local_criteria(model, target, post, s, np.random.default_rng(seed + 2))
                s = model.consume(s, max(model.sources, key=lambda e: loc["copt"][e]))
    df = pd.DataFrame(rows)
    cfg = e7.CFG
    df.to_csv(cfg["paths"]["results"] / "e7b_noise.csv", index=False)
    summ = (
        df.groupby("model")
        .apply(
            lambda d: pd.Series(
                {
                    "states": len(d),
                    "global16_self_disagree": float((d.g16a != d.g16b).mean()),
                    "global16_vs_global64": float(
                        ((d.g16a != d.g64).mean() + (d.g16b != d.g64).mean()) / 2
                    ),
                    "local_vs_global64": float((d.local != d.g64).mean()),
                    "local_vs_global16": float(
                        ((d.local != d.g16a).mean() + (d.local != d.g16b).mean()) / 2
                    ),
                }
            ),
            include_groups=False,
        )
        .reset_index()
    )
    md = [
        "# E7b — Monte Carlo noise of the global criterion",
        "",
        f"{REPS} replications x 11 cells x stages (0, 3); states reached by c-optimal policy.",
        "",
        summ.to_markdown(index=False, floatfmt=".3f"),
    ]
    out = cfg["paths"]["reports"] / "e7b_noise.md"
    out.write_text("\n".join(md), encoding="utf-8")
    print(summ.to_string(index=False))
    print(f"RESULT_PATHS: {out}")
    print(f"[DONE] {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
