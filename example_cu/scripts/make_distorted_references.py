# -*- coding: utf-8 -*-
"""
Build a "wrong" Cu XANES reference set that looks like a different
compound of the same oxidation state: same overall shape, different
fine structure. All operations are smooth and continuous (no hard
windows, no holes, no negative-value clipping artifacts).

Operations, all gated to the post-edge region by a smooth ramp (so
nothing touches the pre-edge / edge-rise, which is not an oscillation):
(1) E0 shift, (2) post-edge energy-scale stretch (changes oscillation
frequency), (3) post-edge oscillation amplitude change relative to a
smooth baseline, (4) a weak added oscillation. No Orange dependency;
native .tab I/O.

Input:  example_cu/data/cu_references_extracted.tab (energy axis in keV)
Output: example_cu/data/cu_references_distorted.tab and
        example_cu/figures/cu_references_distorted.png
"""

import os
import csv
import numpy as np
import matplotlib.pyplot as plt

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "data"))
FIGURES_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "figures"))
IN_TAB = os.path.join(DATA_DIR, "cu_references_extracted.tab")
OUT_TAB = os.path.join(DATA_DIR, "cu_references_distorted.tab")
OUT_PNG = os.path.join(FIGURES_DIR, "cu_references_distorted.png")

BASELINE_SIGMA_EV = 5.0     # smoothing width defining the "smooth baseline"
PRE_EDGE_POINTS = 5
AMP_RAMP_EV = 5.0           # post-edge ramp-in for amplitude/shoulder changes
OSCILLATION_PERIOD_EV = 15.0
OSCILLATION_AMPLITUDE = 0.05  # fraction of post-edge level (~1.0)
CLIP_NEGATIVE = True

SHIFT_EV = 2.0            # edge shift
STRETCH_FRAC = 0.06       # post-edge energy-scale stretch (+ = slower oscillations)
AMP_FACTOR = 1.30         # post-edge oscillation amplitude multiplier


def read_reference_tab(path):
    """Read a 3-header-row .tab. Returns energy_tokens (original column
    text), energy in keV, and rows of (id, group, description, subgroup, values)."""
    with open(path, encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        names = next(reader)
        types = next(reader)
        next(reader)  # flags
        data_rows = list(reader)
    energy_idx = [i for i, t in enumerate(types) if t == "continuous"]
    energy_tokens = [names[i] for i in energy_idx]
    energy = np.array([float(t) for t in energy_tokens])
    label_idx = names.index("Energy") if "Energy" in names else None
    rows = []
    for row in data_rows:
        description = row[label_idx] if label_idx is not None else row[0]
        values = np.array([float(row[i]) for i in energy_idx])
        rows.append((row[0], row[1], description, row[3], values))
    return energy_tokens, energy, rows


def write_reference_tab(path, energy_tokens, rows):
    tab_names = ["Spectrum", "Group", "Energy", "Subgroup"] + energy_tokens
    tab_types = ["string", "string", "string", "string"] + ["continuous"] * len(energy_tokens)
    tab_flags = ["meta", "meta", "meta", "meta"] + [""] * len(energy_tokens)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, delimiter="\t")
        writer.writerow(tab_names)
        writer.writerow(tab_types)
        writer.writerow(tab_flags)
        for spectrum_id, group, description, subgroup, values in rows:
            writer.writerow([spectrum_id, group, description, subgroup] +
                             [repr(float(v)) for v in values])


def detect_edge(energy_keV, spectrum):
    """Edge E0 = first half-max crossing (data is pre-normalized to ~1 post-edge)."""
    post = spectrum[-10:].mean()
    half = 0.5 * post
    above = np.where(spectrum >= half)[0]
    i = int(above[0]) if len(above) else len(spectrum) // 2
    if i == 0:
        return energy_keV[0]
    x0, x1 = energy_keV[i - 1], energy_keV[i]
    y0, y1 = spectrum[i - 1], spectrum[i]
    frac = 0.0 if y1 == y0 else (half - y0) / (y1 - y0)
    return x0 + frac * (x1 - x0)


def warp_shift_stretch(energy_keV, spectrum, E0, shift_eV, stretch_frac):
    """Continuous piecewise remap: shift everywhere, and additionally
    stretch/compress the post-edge energy scale around the shifted edge.
    No discontinuity in value at the junction (both branches equal E0 there)."""
    shift_keV = shift_eV / 1000.0
    new_E0 = E0 + shift_keV
    sample = np.where(
        energy_keV <= new_E0,
        energy_keV - shift_keV,
        E0 + (energy_keV - new_E0) / (1.0 + stretch_frac),
    )
    return np.interp(sample, energy_keV, spectrum)


def smooth_baseline(energy_keV, spectrum, sigma_eV):
    """Gaussian-smoothed envelope, edge-padded to avoid boundary pull-down."""
    step_eV = np.median(np.diff(energy_keV)) * 1000.0
    sigma_pts = sigma_eV / step_eV
    half = max(1, int(np.ceil(4 * sigma_pts)))
    x = np.arange(-half, half + 1)
    kernel = np.exp(-0.5 * (x / sigma_pts) ** 2)
    kernel /= kernel.sum()
    padded = np.pad(spectrum, half, mode="edge")
    return np.convolve(padded, kernel, mode="same")[half:-half]


def edge_ramp(energy_keV, new_E0, ramp_eV):
    """Smoothstep 0->1 starting at new_E0. Gates post-edge-only operations
    so they cannot touch the pre-edge / edge-rise. A symmetric baseline
    smooth leaks the steep edge rise backward into the pre-edge region;
    without this gate, scaling that leaked residual there (e.g. by
    AMP_FACTOR) can push the pre-edge below zero and get clipped, leaving
    a flat-then-jump artifact right before the edge."""
    t = np.clip((energy_keV - new_E0) * 1000.0 / ramp_eV, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def build_distorted(energy_keV, spectrum):
    E0 = detect_edge(energy_keV, spectrum)
    new_E0 = E0 + SHIFT_EV / 1000.0
    ramp = edge_ramp(energy_keV, new_E0, AMP_RAMP_EV)

    warped = warp_shift_stretch(energy_keV, spectrum, E0, SHIFT_EV, STRETCH_FRAC)
    baseline = smooth_baseline(energy_keV, warped, BASELINE_SIGMA_EV)
    residual = warped - baseline

    r_mean = residual.mean()
    delta = (residual - r_mean) * (AMP_FACTOR - 1.0)
    residual = residual + ramp * delta

    out = baseline + residual

    phase = 2 * np.pi * (energy_keV - new_E0) * 1000.0 / OSCILLATION_PERIOD_EV
    out = out + OSCILLATION_AMPLITUDE * np.sin(phase) * ramp

    out = out - out[:PRE_EDGE_POINTS].mean()
    if CLIP_NEGATIVE:
        out = np.clip(out, 0, None)
    return out


os.makedirs(FIGURES_DIR, exist_ok=True)
print(f"Reading: {IN_TAB}")
energy_tokens, energy, ref_rows = read_reference_tab(IN_TAB)
print(f"{len(energy)} energy points ({energy[0]:.4f}-{energy[-1]:.4f} keV), "
      f"{len(ref_rows)} references:")
for spectrum_id, group, description, subgroup, _ in ref_rows:
    print(f"  - Spectrum {spectrum_id}: {description}")

print(f"\nDistortion: shift={SHIFT_EV} eV, stretch={STRETCH_FRAC:.0%}, "
      f"amplitude x{AMP_FACTOR}, weak oscillation added")

distorted_rows = []
for spectrum_id, group, description, subgroup, values in ref_rows:
    distorted = build_distorted(energy, values)
    n_neg = int((distorted <= 0).sum())
    print(f"  Spectrum {spectrum_id}: min={distorted.min():.4f}, "
          f"{n_neg} points at/below zero (pre-edge baseline)")
    distorted_rows.append((spectrum_id, "Ref_distorted", f"{description} (distorted)",
                            "Distorted", distorted))

write_reference_tab(OUT_TAB, energy_tokens, distorted_rows)
print(f"\n.tab saved: {OUT_TAB}")

fig, axes = plt.subplots(len(ref_rows), 1, figsize=(9, 3.5 * len(ref_rows)), sharex=True)
if len(ref_rows) == 1:
    axes = [axes]
for ax, (spectrum_id, _, description, _, values), (_, _, _, _, distorted) in \
        zip(axes, ref_rows, distorted_rows):
    ax.plot(energy, values, lw=1.6, color="0.4", ls="--", label="Real")
    ax.plot(energy, distorted, lw=1.8, color="crimson", label="Distorted")
    ax.set_title(f"{spectrum_id}: {description}")
    ax.set_ylabel("Absorption (a.u.)")
    ax.legend(fontsize=8, loc="upper left")
axes[-1].set_xlabel("Energy (keV)")
fig.suptitle("Real vs. distorted Cu references", fontsize=12)
fig.tight_layout()
fig.savefig(OUT_PNG, dpi=150)
print(f"Figure saved: {OUT_PNG}")
plt.close(fig)
