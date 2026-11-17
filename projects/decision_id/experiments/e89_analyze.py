"""
E8/E9 analysis — confirmatory tests, SV misspecification ablation, learned design policy

전제:
  results/e8_eval.csv, results/e9_eval.csv, results/e9_train_report.json, results/e7_eval.csv
출력:
  results/e89_tests.csv
  figures/e89_ratios.png
  reports/e89_results.md
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from decision_id import plotstyle as ps  # noqa: E402
from decision_id import stats as st  # noqa: E402
from decision_id.utils import load_config  # noqa: E402

SEED = 42


def ratio_test(a, b, rng, name: str, family: str = "") -> dict:
    """Ratio of mean regrets a/b with paired tests and bootstrap CI."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    idx = rng.integers(0, len(a), (4000, len(a)))
    r = a[idx].mean(1) / b[idx].mean(1)
    pt = st.paired_tests(a, b, rng, B=1000)
    return {
        "test": name,
        "family": family,
        "n": len(a),
        "ratio": a.mean() / b.mean(),
        "ci_lo": float(np.quantile(r, 0.025)),
        "ci_hi": float(np.quantile(r, 0.975)),
        "p_t": pt["p_t"],
        "p_wilcoxon": pt["p_wilcoxon"],
        "ties": pt["frac_tie"],
    }


def normalized(df: pd.DataFrame, by: list[str], ref: str = "copt") -> pd.DataFrame:
    """Divide regrets by the mean regret of `ref` within each cell."""
    m = df[df.policy == ref].groupby(by).regret.mean().rename("ref")
    out = df.join(m, on=by)
    out["norm"] = out.regret / out.ref
    return out


def main() -> None:
    t0 = time.time()
    print("=== E8/E9 analysis ===")
    cfg = load_config()
    R = cfg["paths"]["results"]
    for f in ("e8_eval.csv", "e9_eval.csv", "e9_train_report.json", "e7_eval.csv"):
        if not (R / f).exists():
            print(f"[ERR] missing results/{f}")
            sys.exit(1)
    rng = np.random.default_rng(SEED)
    e7 = pd.read_csv(R / "e7_eval.csv")
    e8 = pd.read_csv(R / "e8_eval.csv")
    e9 = pd.read_csv(R / "e9_eval.csv")
    rep = json.loads((R / "e9_train_report.json").read_text())
    tests = []

    # ---- H8a: confirmatory GARCH cell ----
    c = e8[e8.tag == "confirm"].pivot_table(index="task", columns="policy", values="regret")
    tests.append(
        ratio_test(
            c["evsi_global"],
            c["copt"],
            rng,
            "H8a evsi_global/copt (garch weak qlike10, 150 reps)",
            "primary",
        )
    )
    for p in ("adapt_cal", "dopt", "uniform"):
        tests.append(ratio_test(c[p], c["copt"], rng, f"confirm {p}/copt", "secondary"))
    cpu_conf = e8[e8.tag == "confirm"].groupby("policy").cpu_seconds.mean()

    # ---- horizons (exploratory) ----
    hz = []
    for tg, d in e8[e8.tag == "horizon"].groupby("target"):
        p = d.pivot_table(index="task", columns="policy", values="regret")
        hz.append(
            {
                "horizon_target": tg,
                **ratio_test(p["evsi_global"], p["copt"], rng, f"horizon {tg}", "exploratory"),
            }
        )
    hz.append({"horizon_target": "qlike10 (E8 confirm)", **tests[0]})
    p7 = e7[(e7.model == "garch") & (e7.truth == "weak") & (e7.target == "qlike10")].pivot_table(
        index="task", columns="policy", values="regret"
    )
    hz.append(
        {
            "horizon_target": "qlike10 (E7, 30 reps)",
            **ratio_test(p7["evsi_global"], p7["copt"], rng, "E7 qlike10", "reference"),
        }
    )
    hz = pd.DataFrame(hz)

    # ---- H8b: SV exact vs SV QML ----
    svx = normalized(e8[e8.tag == "sv_exact"], ["truth"])
    px = svx.pivot_table(index=["truth", "task"], columns="policy", values="norm")
    tests.append(
        ratio_test(
            px["evsi_global"],
            px["copt"],
            rng,
            "H8b evsi_global/copt (SV exact likelihood, pooled)",
            "primary",
        )
    )
    for p in ("adapt_cal", "dopt", "uniform"):
        tests.append(ratio_test(px[p], px["copt"], rng, f"SV-exact {p}/copt", "secondary"))
    svq = normalized(e7[e7.model == "sv"], ["truth"])
    pq = svq.pivot_table(index=["truth", "task"], columns="policy", values="norm")
    sv_cmp = []
    for truth in ("regular", "weak"):
        a = e8[(e8.tag == "sv_exact") & (e8.truth == truth)].pivot_table(
            index="task", columns="policy", values="regret"
        )
        b = e7[(e7.model == "sv") & (e7.truth == truth)].pivot_table(
            index="task", columns="policy", values="regret"
        )
        sv_cmp.append(
            {
                "truth": truth,
                "exact: evsi/copt": a["evsi_global"].mean() / a["copt"].mean(),
                "QML (E7): evsi/copt": b["evsi_global"].mean() / b["copt"].mean(),
                "exact: uniform/copt": a["uniform"].mean() / a["copt"].mean(),
                "QML (E7): uniform/copt": b["uniform"].mean() / b["copt"].mean(),
            }
        )
    sv_cmp = pd.DataFrame(sv_cmp)
    sv_cmp_pooled = {
        "exact": px["evsi_global"].mean() / px["copt"].mean(),
        "qml": pq["evsi_global"].mean() / pq["copt"].mean(),
    }

    # ---- H9: learned policy, paired with E7 / E8 ----
    l7 = e9[e9.source == "e7"][
        ["model", "truth", "target", "task", "policy", "regret", "cpu_seconds"]
    ]
    j7 = pd.concat([e7[e7.model.isin(["garch", "sv"])][l7.columns], l7], ignore_index=True)
    j7 = normalized(j7, ["model", "truth", "target"])
    for mname, tag in (("garch", "H9a"), ("sv", "H9b")):
        p = j7[j7.model == mname].pivot_table(
            index=["truth", "target", "task"], columns="policy", values="norm"
        )
        tests.append(
            ratio_test(
                p["learned"], p["copt"], rng, f"{tag} learned/copt ({mname}, E7 seeds)", "primary"
            )
        )
        tests.append(
            ratio_test(
                p["learned"], p["evsi_global"], rng, f"{mname} learned/evsi_global", "secondary"
            )
        )
    l8 = e9[e9.source == "e8"].set_index("task").regret
    tests.append(
        ratio_test(
            l8.loc[c.index],
            c["copt"],
            rng,
            "H9c learned/copt (garch weak qlike10, 150 reps)",
            "primary",
        )
    )
    tests.append(
        ratio_test(
            l8.loc[c.index], c["evsi_global"], rng, "confirm learned/evsi_global", "secondary"
        )
    )
    cells9 = []
    for (m, tr, tg), d in j7.groupby(["model", "truth", "target"]):
        p = d.pivot_table(index="task", columns="policy", values="regret")
        cells9.append(
            {
                "cell": f"{m}/{tr}/{tg}",
                "learned/copt": p["learned"].mean() / p["copt"].mean(),
                "evsi/copt": p["evsi_global"].mean() / p["copt"].mean(),
                "uniform/copt": p["uniform"].mean() / p["copt"].mean(),
                "cpu_learned": d[d.policy == "learned"].cpu_seconds.mean(),
                "cpu_copt": d[d.policy == "copt"].cpu_seconds.mean(),
                "cpu_evsi": d[d.policy == "evsi_global"].cpu_seconds.mean(),
            }
        )
    cells9 = pd.DataFrame(cells9)
    mcs_rows = []
    pols = [
        "uniform",
        "dopt",
        "copt",
        "copt_global",
        "evsi_global",
        "adapt",
        "adapt_cal",
        "learned",
    ]
    for mname in ("garch", "sv"):
        p = j7[j7.model == mname].pivot_table(
            index=["truth", "target", "task"], columns="policy", values="norm"
        )[pols]
        surv, pv = st.mcs(p.values, pols, alpha=0.10, B=3000, rng=rng)
        mcs_rows.append(
            {"model": mname, "MCS_90": ", ".join(surv), **{f"p_{k}": pv[k] for k in pols}}
        )
    mcs = pd.DataFrame(mcs_rows)

    T = pd.DataFrame(tests)
    prim = T.family == "primary"
    T["p_holm_primary"] = np.nan
    T.loc[prim, "p_holm_primary"] = st.holm(T.loc[prim, "p_t"].values)
    T.to_csv(R / "e89_tests.csv", index=False)

    # ---- figure ----
    import matplotlib.pyplot as plt

    ps.apply()
    show = T[T.family.isin(["primary"])].copy()
    show = pd.concat([show, T[T.test.str.contains("learned/evsi")]])
    fig, ax = plt.subplots(figsize=(8.5, 3.6))
    y = np.arange(len(show))
    ax.errorbar(
        show.ratio,
        y,
        xerr=[show.ratio - show.ci_lo, show.ci_hi - show.ratio],
        fmt="o",
        color=ps.SERIES[0],
        capsize=3,
        ms=6,
    )
    ax.axvline(1, color=ps.TEXT2, ls="--", lw=1)
    ax.set_xscale("log")
    ax.set_yticks(y, [t.split(" (")[0] for t in show.test])
    ax.set_xlabel("ratio of mean regrets (log scale; < 1 favours the first policy)")
    ax.set_title("E8/E9: primary comparisons (95% paired-bootstrap CI)")
    ps.save(fig, cfg["paths"]["figures"] / "e89_ratios.png")

    md = [
        "# E8/E9 — Confirmation, SV misspecification ablation, regret-trained neural policy",
        "",
        "## All tests (Holm over the five pre-registered primary tests)",
        "",
        T.to_markdown(index=False, floatfmt=".4g"),
        "",
        "## Horizon exploration in the weak GARCH regime (global EVSI / c-opt)",
        "",
        hz[["horizon_target", "n", "ratio", "ci_lo", "ci_hi", "p_t"]].to_markdown(
            index=False, floatfmt=".4g"
        ),
        "",
        "## SV: exact likelihood (E8) vs QML quasi-likelihood (E7)",
        "",
        sv_cmp.to_markdown(index=False, floatfmt=".3f"),
        "",
        f"Pooled evsi/copt: exact {sv_cmp_pooled['exact']:.3f} vs QML {sv_cmp_pooled['qml']:.3f}",
        "",
        "## Learned policy per cell (E7 seeds) and CPU seconds per run",
        "",
        cells9.to_markdown(index=False, floatfmt=".3f"),
        "",
        "## Model Confidence Set incl. the learned policy (E7 seeds, alpha = 0.10)",
        "",
        mcs.to_markdown(index=False, floatfmt=".3f"),
        "",
        "## Training report (held-out trajectories: mean one-step true regret of the chosen "
        "source)",
        "",
        pd.DataFrame(rep).T.to_markdown(floatfmt=".4g"),
        "",
        "CPU in the confirmatory cell: " + ", ".join(f"{k} {v:.1f}s" for k, v in cpu_conf.items()),
        "",
        "Figure: `figures/e89_ratios.png`.",
    ]
    out = cfg["paths"]["reports"] / "e89_results.md"
    out.write_text("\n".join(md), encoding="utf-8")
    print(T.to_string(index=False))
    print(hz[["horizon_target", "n", "ratio", "ci_lo", "ci_hi", "p_t"]].to_string(index=False))
    print(sv_cmp.to_string(index=False), sv_cmp_pooled)
    print(cells9.to_string(index=False))
    print(mcs.to_string(index=False))
    print(json.dumps(rep, indent=1))
    print(f"RESULT_PATHS: {out}")
    print(f"[DONE] {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
