"""Extra checks: (1) does truncating to our proj>8 (as in the live frame) inflate the
ECR blend gain?  (2) RB/TE/WR points-blend weight curve (per fold, OOS) incl. MAE/bias.
Run after ecr_blend.py. Writes analysis/proj_ecr/extra_checks.txt."""
import numpy as np
import pandas as pd

import ecr_blend as eb

out = []
e, mp, elig = eb.load_ecr()
df = eb.ev.load_arm("baseline")
df = df[df.season.isin([2020, 2021]) & df.position.isin(eb.SKILL) & (df.final_projection > 0)]
m = eb.attach_ecr(df, e, "b")
m["elig"] = eb.eligible(m, elig)
C = m[m.ecr.notna() & m.elig & m.played].copy()
grp = ["season", "week"]
for tr, te in ((2020, 2021), (2021, 2020)):
    maps = eb.fit_maps(C[C.season == tr])
    Te = C[C.season == te]
    for lab, T in (("full common set", Te), ("truncated proj>8", Te[Te.final_projection > 8])):
        T = eb.add_scores(T, maps, grp + ["position"])
        for pos in ["RB", "WR", "TE", "QB"]:
            P = T[T.position == pos].copy()
            base = eb.cellstats(P, "final_projection", grp)
            line = [f"test {te} {lab:17s} {pos} n={len(P)}"]
            for w in (0.3, 0.5, 0.7, 1.0):
                P["s"] = eb.score(P, "pts", w)
                c = eb.cellstats(P, "s", grp)
                ps = eb.pointstats(P, "s")
                line.append(f"w{w}: dSp {c.sp.mean()-base.sp.mean():+.3f} dTopN {c.tn.mean()-base.tn.mean():+.2f} "
                            f"dMAE {ps['MAE']-eb.pointstats(P,'final_projection')['MAE']:+.3f} "
                            f"bias {ps['bias']:+.2f}")
            out.append(" | ".join(line))
txt = "\n".join(out)
print(txt)
(eb.HERE / "extra_checks.txt").write_text(txt, encoding="utf-8")
