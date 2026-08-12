"""Execution-accuracy grading of generated SQL against gold, paired by question.

Order is enforced only for questions whose text demands a ranking.
Everything else is compared as an unordered multiset of rows.
"""
import json, math, collections, pathlib, datetime as dt, os
from decimal import Decimal
import duckdb, importlib.util

# See build.py - same two productisation changes, same reason.
if __name__ != "__main__":
    raise ImportError(
        "semantic_bench.grade is a script, not a module. "
        "Run: python -m nakhoda.tests.semantic_bench.grade"
    )

B = pathlib.Path(os.environ.get("SEMANTIC_BENCH_OUT", "/tmp/semantic-bench"))
spec = importlib.util.spec_from_file_location("qs", pathlib.Path(__file__).parent / "questions.py")
qs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qs)
Q = qs.Q
GOLD = {q["id"]: q for q in Q}
ORDERED = {"q24", "q25", "q29", "q30", "q33", "q34", "q35", "q36", "q37", "q39"}

con = duckdb.connect(str(B / "erp.duckdb"), read_only=True)


def scal(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return bool(v)
    if isinstance(v, (Decimal, float, int)):
        f = float(v)
        return None if math.isnan(f) else round(f, 2)
    if isinstance(v, (dt.datetime, dt.date)):
        return str(v)[:10]
    return str(v)


def norm(df, ordered):
    rows = [tuple(scal(c) for c in r) for r in df.itertuples(index=False, name=None)]
    return rows if ordered else sorted(rows, key=lambda t: tuple(str(x) for x in t))


def cols_of(df):
    return [[scal(v) for v in df[c].tolist()] for c in df.columns]


def match(pred_df, gold_df, ordered):
    """Every gold column must appear as some predicted column, on the same row set.

    Rows are aligned by the gold ordering when the question demands a ranking,
    otherwise both sides are sorted on the full predicted tuple first.
    """
    if len(pred_df) != len(gold_df):
        return False, f"{len(pred_df)} rows vs {len(gold_df)} gold"
    p_rows = [tuple(scal(v) for v in r) for r in pred_df.itertuples(index=False, name=None)]
    g_rows = [tuple(scal(v) for v in r) for r in gold_df.itertuples(index=False, name=None)]
    if not ordered:
        order = sorted(range(len(p_rows)), key=lambda i: tuple(str(x) for x in p_rows[i]))
        p_rows = [p_rows[i] for i in order]
        g_rows = sorted(g_rows, key=lambda t: tuple(str(x) for x in t))
    p_cols = list(zip(*p_rows)) if p_rows else []
    g_cols = list(zip(*g_rows)) if g_rows else []
    used = set()
    for gi, gcol in enumerate(g_cols):
        hit = next((j for j, pcol in enumerate(p_cols) if j not in used and pcol == gcol), None)
        if hit is None:
            return False, f"gold col {gi} unmatched"
        used.add(hit)
    return True, ""


def run_sql(sql):
    try:
        return con.execute(sql).df(), None
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:90]}"


gold_df = {qid: run_sql(q["sql"])[0] for qid, q in GOLD.items()}
gen = json.loads((B / "generated.json").read_text())


def pct(sel_rows):
    return 100.0 * sum(r["status"] == "pass" for r in sel_rows) / len(sel_rows) if sel_rows else 0.0

res = []
for g in gen:
    qid = g["qid"]
    ordered = qid in ORDERED
    gd = gold_df[qid]
    if not g.get("sql"):
        res.append({**g, "status": "no_sql", "detail": ""})
        continue
    df, err = run_sql(g["sql"])
    if err:
        res.append({**g, "status": "error", "detail": err})
        continue
    if df.shape[1] < gd.shape[1]:
        res.append({**g, "status": "wrong_shape", "detail": f"{df.shape[1]} cols vs {gd.shape[1]}"})
        continue
    ok, why = match(df, gd, ordered)
    if ok:
        res.append({**g, "status": "pass", "detail": ""})
        continue
    ok_unordered, _ = match(df, gd, False)
    if ordered and ok_unordered:
        res.append({**g, "status": "wrong_order", "detail": ""})
    else:
        res.append({**g, "status": "wrong_values", "detail": why})

json.dump(res, open(B / "graded.json", "w"), indent=1)


sel = lambda **kw: [r for r in res if all(r[k] == v for k, v in kw.items())]

print(f"=== EXECUTION ACCURACY  ({len(Q)} questions, paired single-shot) ===\n")
hdr = f"{'model':14}{'A: raw DDL':>13}{'B: DocType':>13}{'delta':>9}"
print(hdr); print("-" * len(hdr))
for m in ("default", "smol", "slow"):
    a, b = pct(sel(model=m, ctx="A_raw")), pct(sel(model=m, ctx="B_semantic"))
    print(f"{m:14}{a:12.1f}%{b:12.1f}%{b-a:+8.1f}")
a, b = pct(sel(ctx="A_raw")), pct(sel(ctx="B_semantic"))
print("-" * len(hdr)); print(f"{'combined':14}{a:12.1f}%{b:12.1f}%{b-a:+8.1f}")

print("\n=== BY SEMANTIC TRAP ===")
hdr = f"{'trap':12}{'n':>3}{'A raw':>9}{'B sem':>9}{'delta':>8}"
print(hdr); print("-" * len(hdr))
traps = collections.OrderedDict()
for q in Q:
    traps.setdefault(q["trap"], []).append(q["id"])
for t, ids in sorted(traps.items(), key=lambda kv: -len(kv[1])):
    A = [r for r in res if r["ctx"] == "A_raw" and r["qid"] in ids]
    Bb = [r for r in res if r["ctx"] == "B_semantic" and r["qid"] in ids]
    print(f"{t:12}{len(ids):3}{pct(A):8.1f}%{pct(Bb):8.1f}%{pct(Bb)-pct(A):+7.1f}")

print("\n=== FAILURE MODES ===")
for c in ("A_raw", "B_semantic"):
    print(f"  {c:12}", dict(collections.Counter(r["status"] for r in res if r["ctx"] == c)))

print("\n=== PER-QUESTION (fail in A, pass in B = semantic layer earned it) ===")
for q in Q:
    row = ""
    for c in ("A_raw", "B_semantic"):
        for m in ("default", "smol", "slow"):
            r = next((x for x in res if x["qid"] == q["id"] and x["ctx"] == c and x["model"] == m), None)
            row += ("." if r and r["status"] == "pass" else "X")
        row += " "
    if row != ".. .. ":
        print(f"  {q['id']} {row} [{q['trap']:9}] {q['q'][:62]}")
print("\n  legend: 'AA BB' = A_raw(default,smol) B_semantic(default,smol); . = pass")
