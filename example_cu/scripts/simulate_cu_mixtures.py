# -*- coding: utf-8 -*-
"""
Regenerate Simulated_Cu_spectra_3_references.tab from the 3 real Cu
references. No Orange dependency; native .tab I/O.

Generative model, reverse-engineered from the lost original dataset
(NNLS fit of each mixture against the 3 references, fraction parsing
from its own description text, and residual statistics -- see the
printed analysis and README notes below):
    mixture = f1*ref1 + f2*ref2 + f3*ref3 + N(0, NOISE_SIGMA)
    fractions ~ Dirichlet(1,1,1)  (uniform on the simplex, sum to 1)
    noise: additive, white (no energy or amplitude dependence)

Input:  example_cu/data/cu_references_extracted.tab (3 real references)
Output: example_cu/data/simulated_cu_mixtures.tab (3 refs + N_MIXTURES
        noisy mixtures), plus a console comparison against the original
        Simulated_Cu_spectra_3_references.tab if that file is present.
"""

import os
import re
import csv
import numpy as np
from scipy.optimize import nnls

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "data"))
IN_TAB = os.path.join(DATA_DIR, "cu_references_extracted.tab")
ORIGINAL_TAB = os.path.join(DATA_DIR, "Simulated_Cu_spectra_3_references.tab")
OUT_TAB = os.path.join(DATA_DIR, "simulated_cu_mixtures.tab")

N_MIXTURES = 1000
NOISE_SIGMA = 0.025
RANDOM_SEED = 0


def read_reference_tab(path):
    """Read a 3-header-row .tab. Returns energy_tokens (original column
    text), energy, and rows of (id, group, description, subgroup, values)."""
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
    tab_types = ["string", "10 1000 Ref", "string", "Clean Noisy Ref"] + ["continuous"] * len(energy_tokens)
    tab_flags = ["meta", "meta", "meta", "meta"] + [""] * len(energy_tokens)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, delimiter="\t")
        writer.writerow(tab_names)
        writer.writerow(tab_types)
        writer.writerow(tab_flags)
        for spectrum_id, group, description, subgroup, values in rows:
            writer.writerow([spectrum_id, group, description, subgroup] +
                             [repr(float(v)) for v in values])


def fit_fractions(mix_specs, basis):
    """NNLS fit of each mixture against the reference basis (n_energy x 3)."""
    out = np.zeros((len(mix_specs), basis.shape[1]))
    for i, spec in enumerate(mix_specs):
        coef, _ = nnls(basis, spec)
        out[i] = coef
    return out


def dataset_stats(fracs, mix_specs, basis, label):
    recon = fracs @ basis.T
    resid = mix_specs - recon
    print(f"[{label}]")
    print(f"  n mixtures = {len(mix_specs)}")
    print(f"  fraction sum: mean={fracs.sum(1).mean():.4f} std={fracs.sum(1).std():.4f}")
    for i, name in enumerate(("comp1", "comp2", "comp3")):
        c = fracs[:, i]
        print(f"  {name}: mean={c.mean():.3f} std={c.std():.3f} min={c.min():.3f} max={c.max():.3f}")
    corr = np.corrcoef(fracs.T)
    print(f"  fraction correlation (off-diag mean) = {(corr.sum() - 3) / 6:.3f}")
    print(f"  residual std: mean={resid.std(axis=1).mean():.4f} "
          f"(per-spectrum range {resid.std(axis=1).min():.4f}-{resid.std(axis=1).max():.4f})")
    print(f"  mean spectrum shape (first/mid/last point) = "
          f"{mix_specs.mean(0)[0]:.3f} / {mix_specs.mean(0)[len(energy)//2]:.3f} / {mix_specs.mean(0)[-1]:.3f}")


print(f"Reading real references: {IN_TAB}")
energy_tokens, energy, ref_rows = read_reference_tab(IN_TAB)
refs = np.array([r[4] for r in ref_rows])      # (3, n_energy)
basis = refs.T                                  # (n_energy, 3)
labels = [re.sub(r"^\d+_Pure\s*", "", r[2]) for r in ref_rows]  # "Cu(0)", "Cu2O (Cu(I))", "CuO(II)"
print("References:", labels)

# --- generate -----------------------------------------------------------
rng = np.random.default_rng(RANDOM_SEED)
rows = list(ref_rows)
new_fracs = np.zeros((N_MIXTURES, 3))
for i in range(N_MIXTURES):
    frac = rng.dirichlet([1.0, 1.0, 1.0])
    new_fracs[i] = frac
    clean = frac @ refs
    noisy = clean + rng.normal(0.0, NOISE_SIGMA, size=clean.shape)
    pct = [round(f * 100) for f in frac]
    desc = f"Mix {i+1}: {labels[0]} {pct[0]}%, {labels[1]} {pct[1]}%, {labels[2]} {pct[2]}%"
    rows.append((str(i + 4), "1000", desc, "Noisy", noisy))

write_reference_tab(OUT_TAB, energy_tokens, rows)
print(f"\nSaved: {OUT_TAB}  ({len(rows)} rows: 3 references + {N_MIXTURES} mixtures)")

# --- validate: compare regenerated vs. the real original, if present ----
new_mix_specs = np.array([r[4] for r in rows[3:]])
print("\n=== Validation: regenerated vs. parameters used ===")
dataset_stats(new_fracs, new_mix_specs, basis, "regenerated (ground truth fractions)")

if os.path.exists(ORIGINAL_TAB):
    print(f"\nReading original for comparison: {ORIGINAL_TAB}")
    _, _, orig_rows = read_reference_tab(ORIGINAL_TAB)
    orig_mix_rows = [r for r in orig_rows if r[1] == "1000"]
    orig_mix_specs = np.array([r[4] for r in orig_mix_rows])
    pat = re.compile(r"(\d+)%.*?(\d+)%.*?(\d+)%")
    orig_fracs = np.array([[int(x) / 100.0 for x in pat.search(r[2]).groups()]
                            for r in orig_mix_rows])
    print("\n=== Validation: original dataset (for direct comparison) ===")
    dataset_stats(orig_fracs, orig_mix_specs, basis, "original")
else:
    print(f"\nOriginal file not found at {ORIGINAL_TAB}; skipping side-by-side comparison.")
