"""Figures of Chapter 7, built from the raw results of the repository (results/)."""
import csv, json, glob, gzip, statistics as st, collections, sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

R = Path(sys.argv[1])            # repo root
OUT = Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)

INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
C = {  # fixed entity colours (validated categorical order)
    "keyword": "#2a78d6", "embedding": "#eb6834", "nemotron": "#1baf7a",
    "gpt-oss-120b": "#eda100", "mistral-large-4": "#e87ba4",
}
STORE = {"memory": "#2a78d6", "ngsild": "#eb6834"}
plt.rcParams.update({
    "font.family": "serif", "font.serif": ["cmr10"], "mathtext.fontset": "cm",
    "axes.formatter.use_mathtext": True, "axes.unicode_minus": False,
    "font.size": 9, "axes.titlesize": 9, "axes.labelsize": 9,
    "xtick.labelsize": 8, "ytick.labelsize": 8, "legend.fontsize": 8,
    "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
    "legend.frameon": False, "savefig.bbox": "tight", "savefig.pad_inches": 0.02,
    "lines.linewidth": 2, "lines.markersize": 5,
})
W = 6.1  # inches, text width

def save(fig, name):
    fig.savefig(OUT / f"{name}.pdf")
    fig.savefig(OUT / f"{name}.png", dpi=160)
    plt.close(fig)

def rows(p): return list(csv.DictReader(open(p, encoding="utf-8")))

NAMES = {"keyword": "keyword", "embedding": "embedding",
         "llm:nvidia/nemotron-3.5-super-vl:free": "nemotron",
         "llm:openai/gpt-oss-120b": "gpt-oss-120b",
         "llm:mistralai/mistral-large-4-0": "mistral-large-4"}
ORDER = ["keyword", "embedding", "nemotron", "gpt-oss-120b", "mistral-large-4"]

# ---------- majority answers on the test split ----------
# Each language model was run three times; a request counts once, with the answer given
# in at least two of the three repeats, so that every technique is measured on 156 requests.
from cpsagent.contracts import GroundingResultAdapter
from cpsagent.eval.dataset import bind_scenario, from_repo, load_cases
from cpsagent.eval.metrics import score
from cpsagent.eval.report import wilson
TEST_RUNS = {"keyword": "20261121-131024_keyword_keyword_test",
             "embedding": "20261121-131024_embedding_embedding_test",
             "nemotron": "20261121-152330_llm_nvidia-nemotron-3.5-super-vl-free_test",
             "gpt-oss-120b": "20261121-154439_llm_openai-gpt-oss-120b_test_deepinfra",
             "mistral-large-4": "20261121-155508_llm_mistralai-mistral-large-4-0_test"}
_session = bind_scenario()
MAJ = {}
for g, d in TEST_RUNS.items():
    meta = json.loads((R/"results/final"/d/"run.json").read_text())
    cases = {c.id: c for c in load_cases(from_repo(meta["dataset"]))[0]}
    per = collections.defaultdict(list)
    for line in (R/"results/final"/d/"predictions.jsonl").read_text().splitlines():
        rec = json.loads(line)
        per[rec["id"]].append(score(cases[rec["id"]], rec["repeat"],
                                    GroundingResultAdapter.validate_python(rec["prediction"]), _session))
    MAJ[g] = {i: {"strict": sum(s.strict for s in v) * 2 > len(v), "outcome": sum(s.outcome_ok for s in v) * 2 > len(v),
                  "category": v[0].case.category} for i, v in per.items()}

# ---------- F1: test split accuracy with Wilson intervals ----------
fig, axes = plt.subplots(1, 2, figsize=(W, 2.1), sharey=True)
for ax, (key, title) in zip(axes, [("strict", "(a) Strict accuracy"), ("outcome", "(b) Outcome accuracy")]):
    ys = range(len(ORDER))[::-1]
    for y, g in zip(ys, ORDER):
        h = sum(r[key] for r in MAJ[g].values()); n = len(MAJ[g])
        v = h / n * 100; lo, hi = (x * 100 for x in wilson(h, n))
        ax.barh(y, v, height=0.55, color=C[g], zorder=2)
        ax.errorbar(v, y, xerr=[[v - lo], [hi - v]], fmt="none", ecolor=INK, elinewidth=0.9, capsize=2.5, zorder=3)
        ax.text(hi + 1.2, y, f"{v:.1f}%", va="center", fontsize=8, color=INK)
    ax.set_xlim(50, 108); ax.set_title(title, loc="left")
    ax.set_xlabel("% of the 156 test requests")
    ax.grid(axis="y", visible=False)
axes[0].set_yticks(list(range(len(ORDER))[::-1])); axes[0].set_yticklabels(ORDER)
save(fig, "fig_test_accuracy")

# ---------- F2: per-category heatmap ----------
cats = ["explicit", "explicit_other_zone", "implicit", "zone_dependent", "following", "environment",
        "ambiguous", "unsupported", "out_of_scope", "adversarial"]
ncat = {c: sum(1 for r in MAJ["keyword"].values() if r["category"] == c) for c in cats}
M = [[100 * sum(r["strict"] for r in MAJ[g].values() if r["category"] == c) / ncat[c] for g in ORDER] for c in cats]
from matplotlib.colors import LinearSegmentedColormap
blue = LinearSegmentedColormap.from_list("b", ["#f2f7fd", "#9ec5f4", "#3987e5", "#1c5cab", "#0d366b"])
def heat(ax, M, rows, cols, fmt, vmax=100, txt=None):
    im = ax.imshow(M, cmap=blue, vmin=0, vmax=vmax, aspect="auto")
    for i, row in enumerate(M):
        for j, v in enumerate(row):
            s = txt[i][j] if txt else fmt(v)
            ax.text(j, i, s, ha="center", va="center", fontsize=8, color="white" if v >= 0.6 * vmax else INK)
    ax.set_xticks(range(len(cols))); ax.set_yticks(range(len(rows))); ax.set_yticklabels(rows)
    ax.grid(False)
    for s in ax.spines.values(): s.set_visible(False)
    ax.set_xticks([x - .5 for x in range(1, len(cols))], minor=True)
    ax.set_yticks([y - .5 for y in range(1, len(rows))], minor=True)
    ax.grid(which="minor", color="white", linewidth=2); ax.tick_params(which="minor", length=0)
    ax.tick_params(which="major", length=0)
    return im
fig, ax = plt.subplots(figsize=(W * 0.82, 3.1))
im = heat(ax, M, [f"{c.replace('_', ' ')} ({ncat[c]})" for c in cats], ORDER, lambda v: f"{v:.0f}")
ax.set_xticklabels(ORDER, rotation=20, ha="right")
cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02); cb.set_label("strict accuracy (%)"); cb.outline.set_visible(False)
save(fig, "fig_test_categories")

# ---------- F3: qualitative set ----------
qs = rows(R/"results/qualitative/combined/summary.csv")
def qname(r):
    m = r["model"]
    return {"": r["interpreter"], "nvidia/nemotron-3.5-super-vl:free": "nemotron",
            "openai/gpt-oss-120b": "gpt-oss-120b", "mistralai/mistral-large-4-0": "mistral-large-4"}[m]
groups = [("articulated", "1", "articulated"), ("hard", "1", "hard"), ("multi_action", "2", "2 actions"),
          ("multi_action", "3", "3 actions"), ("multi_action", "4", "4 actions"), ("multi_action", "5", "5 actions")]
fig, axes = plt.subplots(1, 2, figsize=(W, 2.4), gridspec_kw={"width_ratios": [1.0, 1.0]})
ax = axes[0]
bw = 0.15
for gi, g in enumerate(ORDER):
    vals = []
    for cat, k, _ in groups:
        r = next(r for r in qs if qname(r) == g and r["grouping"] == "category x k" and r["category"] == cat and r["k"] == k)
        vals.append(float(r["full_success_rate"]) * 100)
    xs = [i + (gi - 2) * bw for i in range(len(groups))]
    ax.bar(xs, vals, width=bw * 0.88, color=C[g], label=g, zorder=2)
ax.set_xticks(range(len(groups))); ax.set_xticklabels(["artic.", "hard", "k=2", "k=3", "k=4", "k=5"])
ax.set_ylim(0, 105); ax.set_ylabel("messages fully correct (%)")
ax.set_title("(a) Full success by kind of message", loc="left"); ax.grid(axis="x", visible=False)
ax = axes[1]
ks = [2, 3, 4, 5]
for g in ORDER:
    rec = []
    for k in ks:
        r = next(r for r in qs if qname(r) == g and r["grouping"] == "category x k" and r["category"] == "multi_action" and r["k"] == str(k))
        rec.append(int(r["correct"]) / 8)
    ax.plot(ks, rec, marker="o", color=C[g], label=g)
ax.plot(ks, [min(k, 3) for k in ks], color=INK2, linestyle=(0, (3, 2)), linewidth=1, label="at most 3 parts")
ax.plot(ks, ks, color=GRID, linewidth=1, zorder=1)
ax.set_xticks(ks); ax.set_xlabel("actions asked in the message"); ax.set_ylabel("actions carried out correctly")
ax.set_ylim(0, 5.3); ax.set_title("(b) Correct actions per message", loc="left")
h, l = axes[1].get_legend_handles_labels()
fig.legend(h, l, loc="upper center", ncol=3, bbox_to_anchor=(0.5, -0.02), handlelength=4.2, numpoints=2, columnspacing=1.6)
fig.subplots_adjust(bottom=0.31, wspace=0.3)
save(fig, "fig_qualitative")

# ---------- F4: emulator vs Orion-LD (backends harness) ----------
def bench(d):
    f = glob.glob(str(R/d/"events.jsonl*"))[0]
    op = gzip.open if f.endswith(".gz") else open
    rs = [json.loads(l) for l in op(f, "rt")]
    rs = [r for r in rs if not r.get("warmup")]
    by = collections.defaultdict(list)
    for r in rs:
        m = r["measure"]
        if m == "operation": by[r["operation"]].append(r["latency_ns"] / 1e6)
        elif m == "signal" and r.get("forwarded") and not r.get("recovered"): by["signal delivery"].append(r["delivery_ns"] / 1e6)
        elif m == "cycle" and r["kind"] == "request": by["request (text in, reply out)"].append(r["total_ns"] / 1e6)
        elif m == "zone_change":
            for k, lab in (("trigger", "zone change to trigger"), ("estimate", "zone change to estimate"), ("lampOn", "zone change to lamp on")):
                if r.get(k): by[lab].append(r[k]["ns"] / 1e6)
        elif m == "restoration" and r.get("reason") == "person_left_zone": by["restoration"].append(r["ns"] / 1e6)
    return by
mem = bench("results/bench/final_memory/memory-20261121T150629Z")
ngs = bench("results/bench/final_ngsild/ngsild-20261121T150631Z")
labels = ["listZones", "listDevices", "getDeviceState", "invokeCommand", "interpret", "signal delivery",
          "restoration", "request (text in, reply out)", "zone change to trigger", "zone change to estimate", "zone change to lamp on"]
def pct(v, q):
    v = sorted(v); return v[min(len(v) - 1, int(round(q / 100 * (len(v) - 1))))]
fig, ax = plt.subplots(figsize=(W, 3.3))
ys = list(range(len(labels)))[::-1]
for off, (name, data, lab) in zip((0.18, -0.18), (("memory", mem, "in memory (emulator)"), ("ngsild", ngs, "Orion-LD"))):
    for y, l in zip(ys, labels):
        v = data[l]; p50, p95 = pct(v, 50), pct(v, 95)
        ax.barh(y + off, p50, height=0.32, color=STORE[name], zorder=2, label=lab if l == labels[0] else None, log=True)
        ax.errorbar(p50, y + off, xerr=[[0], [p95 - p50]], fmt="none", ecolor=INK, elinewidth=0.8, capsize=2, zorder=3)
ax.set_xscale("log"); ax.set_xlim(1e-3, 300)
ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:g}"))
ax.set_yticks(ys); ax.set_yticklabels(labels); ax.grid(axis="y", visible=False)
ax.set_xlabel("latency (ms, log scale): median, whisker to 95th percentile")
ax.legend(loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.09))
save(fig, "fig_backends")
json.dump({l: {"memory": [pct(mem[l], 50), pct(mem[l], 95), len(mem[l])], "ngsild": [pct(ngs[l], 50), pct(ngs[l], 95), len(ngs[l])]} for l in labels},
          open(OUT / "backends_summary.json", "w"), indent=1)

# ---------- F5: closed-loop load ----------
pts = rows(R/"results/load/tables/points.csv")
series = [("closed_memory_keyword", "memory, keyword", "#2a78d6", "-"), ("closed_memory_embedding", "memory, embedding", "#eb6834", "-"),
          ("closed_ngsild_keyword", "Orion-LD, keyword", "#2a78d6", "--"), ("closed_ngsild_embedding", "Orion-LD, embedding", "#eb6834", "--")]
fig, axes = plt.subplots(1, 2, figsize=(W, 2.5))
for run, lab, col, ls in series:
    rs = [r for r in pts if r["run"] == run]
    n = [int(r["persons"]) for r in rs]
    axes[0].plot(n, [float(r["lat_p95_ms"]) for r in rs], color=col, linestyle=ls, marker="o", label=lab)
    axes[1].plot(n, [float(r["tickLag_p95_ms"]) / 1000 for r in rs], color=col, linestyle=ls, marker="o", label=lab)
    for r in rs:
        if r["failed"]:
            for ax, key, sc in ((axes[0], "lat_p95_ms", 1), (axes[1], "tickLag_p95_ms", 1000)):
                ax.plot(int(r["persons"]), float(r[key]) / sc, marker="x", color=INK, markersize=7, mew=1.5, zorder=4)
for ax in axes:
    ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlabel("persons (N)")
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:g}")); ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:g}"))
axes[0].set_ylabel("request latency, p95 (ms)"); axes[0].set_title("(a) End-to-end latency", loc="left")
axes[1].set_ylabel("tick delay, p95 (s)"); axes[1].set_title("(b) Delay of the positioning signals", loc="left")
h, l = axes[0].get_legend_handles_labels()
fig.legend(h, l, loc="upper center", ncol=2, bbox_to_anchor=(0.5, -0.02), handlelength=4.2, numpoints=2, columnspacing=2.0)
fig.subplots_adjust(bottom=0.33, wspace=0.35)
save(fig, "fig_load_closed")

# ---------- F6: open loop ----------
fig, ax = plt.subplots(figsize=(W * 0.62, 2.4))
for run, lab, col in (("open_memory_keyword_N10", "keyword", C["keyword"]), ("open_memory_embedding_N10", "embedding", C["embedding"])):
    rs = sorted([r for r in pts if r["run"] == run], key=lambda r: float(r["rate"]))
    x = [float(r["rate"]) for r in rs]
    ax.plot(x, [float(r["lat_p50_ms"]) for r in rs], color=col, marker="o", label=f"{lab}, median")
    ax.plot(x, [float(r["lat_p95_ms"]) for r in rs], color=col, marker="o", linestyle="--", label=f"{lab}, p95")
ax.set_xscale("log"); ax.set_yscale("log")
ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:g}")); ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:g}"))
ax.set_xlabel("offered load (requests per second, 10 persons)"); ax.set_ylabel("latency (ms)")
ax.legend(loc="upper left", handlelength=4.2, numpoints=2)
save(fig, "fig_load_open")

# ---------- F7: language-model load ----------
fig, ax = plt.subplots(figsize=(W * 0.62, 2.4))
for run, lab, col in (("closed_memory_llm_nemotron", "nemotron", C["nemotron"]), ("closed_memory_llm_gptoss", "gpt-oss-120b", C["gpt-oss-120b"])):
    rs = [r for r in pts if r["run"] == run]
    n = [int(r["persons"]) for r in rs]
    ax.plot(n, [float(r["lat_p50_ms"]) / 1000 for r in rs], color=col, marker="o", label=f"{lab}, request latency")
    ax.plot(n, [float(r["interpService_p50_ms"]) / 1000 for r in rs], color=col, marker="s", linestyle=":", label=f"{lab}, model call")
ax.set_xscale("log", base=2); ax.set_xticks([1, 2, 4, 8]); ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:g}"))
ax.set_xlabel("persons (N)"); ax.set_ylabel("median (s)"); ax.legend(loc="upper left", handlelength=4.2, numpoints=2)
save(fig, "fig_load_llm")

# ---------- F8: resources ----------
cpu = rows(R/"results/load/tables/cpu.csv"); memt = rows(R/"results/load/tables/memory.csv")
fig, axes = plt.subplots(1, 2, figsize=(W, 2.5))
ax = axes[0]
confs = [("closed_memory_keyword", "memory\nkeyword"), ("closed_memory_embedding", "memory\nembedding"),
         ("closed_ngsild_keyword", "Orion-LD\nkeyword"), ("closed_memory_llm_gptoss", "memory\ngpt-oss-120b")]
x = range(len(confs))
agent = [float(next(r for r in cpu if r["run"] == c and r["persons"] == ("10" if "llm" not in c else "8"))["req_agent_us"]) / 1000 for c, _ in confs]
env = [float(next(r for r in cpu if r["run"] == c and r["persons"] == ("10" if "llm" not in c else "8"))["req_env_us"]) / 1000 for c, _ in confs]
ax.bar([i - 0.18 for i in x], agent, width=0.34, color=STORE["memory"], label="person side (agent)", zorder=2)
ax.bar([i + 0.18 for i in x], env, width=0.34, color=STORE["ngsild"], label="environment side", zorder=2)
for i, (a, e) in enumerate(zip(agent, env)):
    ax.text(i - 0.18, a * 1.15, f"{a:.1f}", ha="center", fontsize=7); ax.text(i + 0.18, e * 1.15, f"{e:.1f}", ha="center", fontsize=7)
ax.set_yscale("log"); ax.set_ylim(0.1, 100); ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
ax.set_xticks(list(x)); ax.set_xticklabels([l for _, l in confs]); ax.grid(axis="x", visible=False)
ax.set_ylabel("CPU time per request (ms)"); ax.set_title("(a) CPU per request (N = 10; LLM N = 8)", loc="left")
ax.legend(loc="upper left")
ax = axes[1]
for run, lab, col in (("closed_memory_keyword", "environment tables", STORE["ngsild"]),):
    rs = [r for r in memt if r["run"] == run]
    n = [int(r["persons"]) for r in rs]
    ax.plot(n, [float(r["env_tables_bytes"]) / 1024 for r in rs], color=col, marker="o", label="environment state (all persons)")
    per = [(float(r["localization_bytes_mean"]) + float(r["session_bytes_mean"])) / 1024 for r in rs]
    ax.plot(n, per, color=STORE["memory"], marker="o", label="agent state per person (excl. trace)")
ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlabel("persons (N)"); ax.set_ylabel("KiB")
ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}")); ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
ax.set_title("(b) Memory of the state (memory, keyword)", loc="left"); ax.legend(loc="upper left")
save(fig, "fig_resources")

# ---------- F9: conflicts and restorations ----------
cf = rows(R/"results/load/tables/conflicts.csv")
fig, axes = plt.subplots(1, 2, figsize=(W, 2.3))
for run, lab, col in (("closed_memory_keyword", "keyword", C["keyword"]), ("closed_memory_embedding", "embedding", C["embedding"])):
    rs = [r for r in cf if r["run"] == run]
    n = [int(r["persons"]) for r in rs]
    axes[0].plot(n, [int(r["contradictory_pairs"]) / float(r["requests"]) * 100 for r in rs], color=col, marker="o", label=lab)
    axes[1].plot(n, [int(r["restorations_during_run"]) for r in rs], color=col, marker="o", label=lab)
for ax in axes:
    ax.set_xscale("log"); ax.set_xlabel("persons (N)"); ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
axes[0].set_ylabel("per 100 requests"); axes[0].set_title("(a) Contradictory commands within 5 s", loc="left")
axes[1].set_ylabel("count in the measured window"); axes[1].set_title("(b) Restorations by the policy", loc="left")
axes[0].legend(loc="upper left")
save(fig, "fig_conflicts")
print("ok")
