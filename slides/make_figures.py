#!/usr/bin/env python3
"""Genera tutte le figure del deck con font e palette uniformi.
Uso: ../.venv/bin/python make_figures.py   (eseguire dentro slides/)
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from scipy.io import loadmat

# --- stile uniforme col deck ---
plt.rcParams.update({
    "font.family": "Arial",
    "font.size": 12,
    "axes.titleweight": "bold",
    "axes.edgecolor": "#444",
    "axes.grid": True,
    "grid.alpha": 0.3,
})
BLUE = "#14507a"   # primario deck
GREEN = "#2ca02c"  # accent deck
RED = "#c0392b"    # strong deck
MIDBLUE = "#2a6f97"
GREY = "#888888"

# colori semantici dei 3 controller (coerenti in tutte le figure)
C_PPO = RED        # baseline data-driven
C_HAND = BLUE      # Handover (ours)
C_MMC = GREEN      # MMC-PI (ours)

ROOT = ".."  # repo root rispetto a slides/

def load(p):
    d = loadmat(p)
    return (np.array(d["time"]).flatten(),
            np.array(d["rts"]).flatten(),
            np.array(d["cores"]).flatten())

def smooth(x, w=200):
    return x if len(x) < w else np.convolve(x, np.ones(w)/w, mode="valid")

# ============================================================ problem.png
fig, ax = plt.subplots(figsize=(5.2, 4.2))
b = ax.bar(["pre-drift\n(in distrib.)", "post-drift\n(OOD)"], [0.0, 23.2],
           color=[GREEN, RED], width=0.6)
for bar, v in zip(b, [0.0, 23.2]):
    ax.text(bar.get_x()+bar.get_width()/2, v+0.6, f"{v:.1f}%",
            ha="center", fontweight="bold", fontsize=13)
ax.set_ylabel("Violazioni SLA (%)")
ax.set_title("PPO frozen: crolla fuori distribuzione")
ax.set_ylim(0, 28)
plt.tight_layout(); plt.savefig("problem.png", dpi=140); plt.close()

# ============================================================ local_results.png
SLA = 0.25
runs = {
 "PPO-only":        (f"{ROOT}/experiments/exp-local-baseline-ppo-lam30-n10-1778519358220/data.mat", C_PPO),
 "Handover (ours)": (f"{ROOT}/experiments/exp-local-handover-lam30-n10-1778521183542/data.mat",     C_HAND),
 "MMC-PI (ours)":   (f"{ROOT}/experiments/exp-local-mmc-pi-lam30-n10-1778519992434/data.mat",       C_MMC),
}
names = list(runs)
fig, ax = plt.subplots(1, 3, figsize=(15, 4.3))
# (a) violations
viol = []
for n in names:
    _, rt, _ = load(runs[n][0]); viol.append(100*(rt > SLA).sum()/len(rt))
bars = ax[0].bar(names, viol, color=[runs[n][1] for n in names])
for bar, v in zip(bars, viol):
    ax[0].text(bar.get_x()+bar.get_width()/2, v+0.15, f"{v:.1f}%", ha="center", fontweight="bold")
ax[0].set_ylabel("SLA violation rate (%)")
ax[0].set_title("(a) Violazioni SLA sotto drift\nlam=30, drift avg ramp t=300→600")
ax[0].set_ylim(0, max(viol)*1.25)
# (b) RT timeseries
for n in names:
    t, rt, _ = load(runs[n][0]); rs = smooth(rt); ts = t[:len(rs)]
    ax[1].plot(ts, rs, label=n, color=runs[n][1], lw=1.8)
ax[1].axhline(SLA, color="k", ls="--", lw=1, label=f"SLA={SLA}s")
ax[1].axvspan(300, 600, color="orange", alpha=.12, label="drift")
ax[1].set_xlabel("time (s)"); ax[1].set_ylabel("response time p-avg (s)")
ax[1].set_title("(b) RT nel tempo — onset drift a t=300"); ax[1].legend(fontsize=9)
# (c) cores
for n in names:
    t, _, co = load(runs[n][0]); cs = smooth(co); ts = t[:len(cs)]
    ax[2].plot(ts, cs, label=n, color=runs[n][1], lw=1.8)
ax[2].axvspan(300, 600, color="orange", alpha=.12)
ax[2].set_xlabel("time (s)"); ax[2].set_ylabel("cores allocati")
ax[2].set_title("(c) Costo (cores) — il prezzo della safety"); ax[2].legend(fontsize=9)
plt.tight_layout(); plt.savefig("local_results.png", dpi=140); plt.close()

# ============================================================ architecture.png
fig, ax = plt.subplots(figsize=(12, 6.5))
ax.set_xlim(0, 12); ax.set_ylim(0, 7); ax.axis("off")

def box(x, y, w, h, text, fc, ec, fs=13):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.08,rounding_size=0.12",
                 fc=fc, ec=ec, lw=2, zorder=3))
    ax.text(x+w/2, y+h/2, text, ha="center", va="center", fontsize=fs, fontweight="bold", zorder=4)

def arrow(x1, y1, x2, y2, color="#444", lw=2.2, ls="-"):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=20,
                 color=color, lw=lw, linestyle=ls, zorder=1))

box(0.4, 5.4, 3.2, 1.0, "Controller\nData-Driven\n(PPO / DL / ...)", "#fdecec", RED, 13)
box(0.4, 3.6, 3.2, 0.9, "ProcessID  (online μ̂)", "#eaf2f8", MIDBLUE, 12)
box(0.4, 2.3, 3.2, 0.9, "Physical Model\n(forma chiusa)", "#eaf2f8", MIDBLUE, 12)
box(0.4, 1.0, 3.2, 0.9, "PI feedback", "#ececec", GREY, 12)
ax.text(2.0, 4.62, "domain-specific (si cambia per dominio)", ha="center", fontsize=9, style="italic", color=MIDBLUE)
ax.text(2.0, 0.78, "generale (SISO)", ha="center", fontsize=9, style="italic", color="#555")
box(5.3, 2.6, 2.6, 1.6, "FSM\nHANDOVER", "#d7f0d7", GREEN, 15)
ax.text(6.6, 2.4, "trigger su violazione SLO\nisteresi + dwell", ha="center", fontsize=9, style="italic", color=GREEN)
box(9.4, 2.7, 2.2, 1.4, "SISTEMA", "#efefef", "#333", 15)
arrow(3.6, 5.9, 5.5, 4.0)
arrow(3.6, 1.45, 5.3, 2.9)
arrow(2.0, 3.6, 2.0, 3.25, color=MIDBLUE)
arrow(2.0, 2.3, 2.0, 1.95, color=MIDBLUE)
arrow(7.9, 3.4, 9.4, 3.4, color=GREEN, lw=3)
arrow(10.5, 2.7, 6.6, 1.6, color="#999", lw=1.8, ls=(0, (5, 3)))
ax.text(8.4, 1.25, "errore SLO osservabile (RT p95)", ha="center", fontsize=9, color="#777")
ax.text(6.0, 6.7, "Adaptive Safety Envelope — un pattern, layer fisici swappabili",
        ha="center", fontsize=15, fontweight="bold")
plt.tight_layout(); plt.savefig("architecture.png", dpi=140, bbox_inches="tight"); plt.close()

# ============================================================ positioning_map.png
# layout landscape: largo e basso → si mostra grande (testo leggibile) con poca altezza
fig, ax = plt.subplots(figsize=(14, 7))
ax.set_xlim(0, 14); ax.set_ylim(0, 7); ax.axis("off")
hx, hy = 7.0, 3.5
fields = [
 ("Control Theory for SE", "Filieri ICSE'14 · Shevtsov TSE'17", MIDBLUE),
 ("Safe-RL / Shielding", "Alshiekh AAAI'18 · SMARLA TSE'24", MIDBLUE),
 ("Runtime Enforcement", "Schneider'00 · Bloem TACAS'15", MIDBLUE),
 ("Simplex / Runtime Assurance", "Sha IEEE-SW'01 · Neural Simplex NFM'20", RED),
 ("Models@runtime", "Blair'09 · Gandhi DC2 ICAC'14", MIDBLUE),
 ("Uncertainty in SAS", "Esfahani'13 · SimCA* TAAS'18", MIDBLUE),
 ("SE4AI / Concept Drift", "Pham ICSE'24 · Paleyes CSUR'22", MIDBLUE),
 ("Physics-informed / Residual RL", "Johannink ICRA'19 · InvQueue TPDS'21", MIDBLUE),
]
pos = [(2.6, 6.2), (7.0, 6.2), (11.4, 6.2), (11.8, 3.5),
       (11.4, 0.8), (7.0, 0.8), (2.6, 0.8), (2.2, 3.5)]
# 1) linee SOTTO (zorder basso): nascoste dietro i box pieni
for (txt, cite, col), (x, y) in zip(fields, pos):
    ax.add_patch(FancyArrowPatch((x, y), (hx, hy), arrowstyle="-", mutation_scale=10,
                 color="#cccccc", lw=1.3, zorder=1))
# 2) hub SOPRA le linee
ax.add_patch(FancyBboxPatch((hx-2.1, hy-0.8), 4.2, 1.6, boxstyle="round,pad=0.1,rounding_size=0.18",
             fc=BLUE, ec="#0d3550", lw=2.5, zorder=3))
ax.text(hx, hy+0.22, "Adaptive Safety Envelope", ha="center", va="center",
        fontsize=20, fontweight="bold", color="white", zorder=4)
ax.text(hx, hy-0.36, "(il nostro lavoro)", ha="center", va="center",
        fontsize=13, style="italic", color="#cfe3f0", zorder=4)
# 3) box laterali SOPRA le linee (font ingranditi)
for (txt, cite, col), (x, y) in zip(fields, pos):
    w, h = 3.7, 1.2
    ax.add_patch(FancyBboxPatch((x-w/2, y-h/2), w, h, boxstyle="round,pad=0.06,rounding_size=0.12",
                 fc=("#fdecec" if col == RED else "#eaf2f8"), ec=col, lw=2, zorder=3))
    ax.text(x, y+0.2, txt, ha="center", va="center", fontsize=13.5, fontweight="bold", color=col, zorder=4)
    ax.text(x, y-0.3, cite, ha="center", va="center", fontsize=10, color="#555", zorder=4)
plt.tight_layout(); plt.savefig("positioning_map.png", dpi=140, bbox_inches="tight"); plt.close()

print("Generate: problem.png, local_results.png, architecture.png, positioning_map.png")
