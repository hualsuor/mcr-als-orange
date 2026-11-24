# -*- coding: utf-8 -*-
"""
MCR-ALS with a user-chosen spectral initial guess ("reference testing").

Input  (in_data): one Orange Table, all rows treated as samples.
Output (out_data): concentration profiles, N rows, original row order.
Output (out_object): guess + optimized pure spectra (2*k rows).
"""

import numpy as np
import matplotlib.pyplot as plt
import spectrochempy as scp
from Orange.data import Table, Domain, ContinuousVariable, DiscreteVariable

plt.style.use("default")
scp.set_loglevel("WARNING")


# =====================================================================
# CONFIGURATION
# =====================================================================

REFERENCE_INDICES = [1, 2, 3]  # 1-based input rows used as the spectral guess (St0)

UNIMODALITY = False      # impose unimodal C (only valid for a real evolving series)
PC_INDEX = 1              # PCA component used to reorder rows when UNIMODALITY=True
PC_ASCENDING = True       # sort direction for that PCA reordering

NONNEG_CONC = "all"       # non-negativity constraint on C
NONNEG_SPEC = "all"       # non-negativity constraint on St
CLOSURE_CONC = []         # [] = no closure; list of components, e.g. [0, 1, 2] = row sums of C equal 1 ("all" fails in spectrochempy 0.6.9)
NORM_SPEC = "euclid"      # St normalization convention (scale only)
SOLVER_CONC = "nnls"      # C solver: "lstsq" | "nnls" | "pnnls"
SOLVER_SPEC = "nnls"      # St solver
MAX_ITER = 200            # max ALS iterations
MAXDIV = 10                # tolerated divergent iterations
TOL_RESIDUAL_CHANGE = 1e-5    # convergence tolerance (spectrochempy >= 0.12)
TOL_PERCENT_LEGACY = 1e-3     # convergence tolerance (older spectrochempy)

PLOT = True                # show diagnostic plots
N_SVD_SHOW = 6              # singular values printed in the SVD report
R_DEGENERACY = 0.999        # |r| above this vs an experimental row flags degeneracy
NEARZERO_FRAC = 0.01        # concentration below this fraction of max flags near-zero
FIGSIZE = (14, 9)


# =====================================================================
# UTILITIES
# =====================================================================

def _set(obj, candidates, value):
    """Try each trait name in order (new API -> old API); return (name, value) or (None, None)."""
    for name in candidates:
        if hasattr(obj, name):
            try:
                setattr(obj, name, value)
                return name, value
            except Exception as exc:
                print(f"   ! could not set {name}={value!r}: {exc}")
    return None, None


def _corr(a, b):
    a = np.asarray(a, float).ravel()
    b = np.asarray(b, float).ravel()
    if np.std(a) == 0 or np.std(b) == 0:
        return np.nan
    return float(np.corrcoef(a, b)[0, 1])


def read_input(table):
    """Extract the spectral matrix and energy axis. No metadata is read."""
    if table is None or len(table) == 0:
        raise ValueError("No input data (in_data is empty).")

    D = np.asarray(table.X, dtype=float)
    if D.ndim != 2 or D.shape[1] < 2:
        raise ValueError(f"Expected a 2D spectral matrix; got {D.shape}.")
    if not np.all(np.isfinite(D)):
        n_bad = int((~np.isfinite(D)).sum())
        raise ValueError(f"{n_bad} non-finite values (NaN/inf) in the data.")

    names = [a.name for a in table.domain.attributes]
    try:
        energies = np.array([float(n.replace(",", ".")) for n in names], float)
        axis_is_energy = bool(np.all(np.isfinite(energies)))
    except (ValueError, AttributeError):
        energies = np.arange(D.shape[1], dtype=float)
        axis_is_energy = False

    if not axis_is_energy:
        print("Note: column names are not numeric; using the variable index as X axis.")

    return D, energies, names, axis_is_energy


def validate_reference_indices(indices, n_obs):
    if len(indices) < 2:
        raise ValueError(f"REFERENCE_INDICES has {len(indices)} entries; need at least 2.")
    if len(set(indices)) != len(indices):
        raise ValueError(f"REFERENCE_INDICES has duplicates: {indices}.")
    for idx in indices:
        if idx < 1 or idx > n_obs:
            raise ValueError(f"REFERENCE_INDICES has {idx}, out of range (1..{n_obs}).")


def svd_report(D, n_show):
    """SVD of the uncentered data (what applies to the bilinear MCR model)."""
    s = np.linalg.svd(D, compute_uv=False)
    ev = s ** 2
    var = 100.0 * ev / ev.sum()
    cum = np.cumsum(var)
    print("\n--- DIMENSIONALITY (SVD, uncentered data) ---")
    print(f"{'k':>3} {'sing.val':>14} {'% var':>10} {'% var cum':>12}")
    for i in range(min(n_show, len(s))):
        print(f"{i+1:>3} {s[i]:>14.5e} {var[i]:>10.4f} {cum[i]:>12.5f}")
    return cum


def pca_order(D, pc_index, ascending):
    """Order rows by their score on principal component pc_index (centered data)."""
    Dc = D - D.mean(axis=0, keepdims=True)
    U, S, _ = np.linalg.svd(Dc, full_matrices=False)
    scores = U * S
    j = pc_index - 1
    if j < 0 or j >= scores.shape[1]:
        raise ValueError(f"PC_INDEX={pc_index} out of range: only {scores.shape[1]} components.")
    key = scores[:, j]
    order = np.argsort(key if ascending else -key, kind="stable")
    var = 100.0 * S ** 2 / np.sum(S ** 2)
    print(f"\nPCA order: PC{pc_index} ({'ascending' if ascending else 'descending'}), "
          f"{var[j]:.3f} % of centered variance.")
    return order, np.argsort(order)


def build_mcrals(unimodality):
    mcr = scp.MCRALS(log_level="WARNING")
    applied = {}

    def apply(names, value, key=None):
        name, val = _set(mcr, names, value)
        if name is not None:
            applied[key or name] = val

    if hasattr(mcr, "tol_residual_change"):
        apply(["tol_residual_change"], TOL_RESIDUAL_CHANGE)
    else:
        apply(["tol"], TOL_PERCENT_LEGACY)

    apply(["max_iter", "maxit"], MAX_ITER)
    apply(["maxdiv"], MAXDIV)
    apply(["nonnegConc"], NONNEG_CONC)
    apply(["nonnegSpec"], NONNEG_SPEC)
    apply(["unimodConc"], "all" if unimodality else [])
    apply(["unimodSpec"], [])
    apply(["closureConc"], CLOSURE_CONC)
    apply(["normSpec"], NORM_SPEC)
    apply(["solver_C", "solverConc"], SOLVER_CONC)
    apply(["solver_St", "solverSpec"], SOLVER_SPEC)
    return mcr, applied


def diagnostics(D, C, St, St0, ref_rows):
    """LOF/R2, guess-vs-optimized similarity, degeneracy and near-zero checks."""
    Xhat = C @ St
    E = D - Xhat
    sse = float(np.sum(E ** 2))
    ssx = float(np.sum(D ** 2))
    lof = 100.0 * np.sqrt(sse / ssx)
    r2 = 1.0 - sse / ssx

    print("\n--- SANITY CHECKS ---")
    print(f"LOF = {lof:.5f} %    R2 = {100.0 * r2:.5f} %")

    print("\n--- SIMILARITY: chosen reference vs optimized spectrum ---")
    for j in range(St.shape[0]):
        r = _corr(St0[j], St[j])
        print(f"  Component_{j+1} (input row {ref_rows[j]}): similarity r = {r:.3f} "
              f"(information only, check the plots)")
    print("  A high r does not prove the reference is right: compare the plots, mainly after the edge.")

    print("\n--- Other checks ---")
    for j in range(St.shape[0]):
        if np.std(St[j]) == 0:
            print(f"  Component_{j+1}: *** COLLAPSED to a constant vector. Lower N_COMPONENTS.")
            continue
        rs = [abs(_corr(St[j], D[i])) for i in range(D.shape[0])]
        rs = [v for v in rs if not np.isnan(v)]
        if not rs:
            continue
        i_max = int(np.argmax(rs))
        flag = "   *** possible degenerate solution" if rs[i_max] > R_DEGENERACY else ""
        print(f"  Component_{j+1}: max |r| vs experimental spectrum = {rs[i_max]:.6f} (row {i_max + 1}){flag}")

    cmax = C.max(axis=0).copy()
    cmax[cmax == 0] = 1.0
    nz = (C / cmax) < NEARZERO_FRAC
    for j in range(C.shape[1]):
        n_off = int(nz[:, j].sum())
        flag = "   *** component off in most samples" if n_off > 0.5 * C.shape[0] else ""
        print(f"  Component_{j+1}: {n_off}/{C.shape[0]} near-zero samples{flag}")

    return Xhat, E, lof, r2


# =====================================================================
# ORANGE OUTPUT TABLES
# =====================================================================

def spectra_table(guess, optimized, attr_names):
    """2*k rows: your chosen reference and the optimized pure spectrum, tagged by Source."""
    k = guess.shape[0]
    comp_values = tuple(f"Component_{j+1}" for j in range(k))

    attrs = [ContinuousVariable(n) for n in attr_names]
    comp_var = DiscreteVariable("Component", values=comp_values)
    src_var = DiscreteVariable("Source", values=("Guess", "Optimized"))
    domain = Domain(attrs, metas=[comp_var, src_var])

    X = np.vstack([guess, optimized])
    comp_idx = np.concatenate([np.arange(k), np.arange(k)])
    src_idx = np.concatenate([np.zeros(k), np.ones(k)])
    M = np.column_stack([comp_idx, src_idx]).astype(float)
    return Table.from_numpy(domain, X, metas=M)


def concentration_table(C):
    """N rows, original input order. Raw C and relative fraction (%). Meta Index = 1..N."""
    n_obs, k = C.shape
    csum = C.sum(axis=1, keepdims=True)
    csum[csum == 0] = 1.0
    frac = 100.0 * C / csum

    attrs = ([ContinuousVariable(f"C_Component_{j+1}") for j in range(k)] +
             [ContinuousVariable(f"Frac_Component_{j+1}") for j in range(k)])
    domain = Domain(attrs, metas=[ContinuousVariable("Index")])

    X = np.hstack([C, frac])
    M = np.arange(1, n_obs + 1, dtype=float).reshape(-1, 1)
    return Table.from_numpy(domain, X, metas=M)


# =====================================================================
# PLOTS
# =====================================================================

def make_plots(D, energies, St0, C, St, Xhat, E, lof, axis_is_energy, order_label, ref_rows):
    cmap = plt.get_cmap("tab10")
    xlabel = "Energy" if axis_is_energy else "Variable index"
    n_obs = D.shape[0]

    fig, ax = plt.subplots(2, 3, figsize=FIGSIZE)
    ax = ax.flatten()
    fig.suptitle(f"Reference testing -> MCR-ALS  ·  k={St.shape[0]}  ·  {order_label}  ·  LOF={lof:.4f} %",
                 fontsize=12)

    for i in range(n_obs):
        ax[0].plot(energies, D[i], lw=0.8, color="0.5", alpha=0.7)
    ax[0].set_title(f"Experimental data ({n_obs} spectra)")

    for j in range(St0.shape[0]):
        ax[1].plot(energies, St0[j], lw=1.5, color=cmap(j % 10), label=f"Component_{j+1} (row {ref_rows[j]})")
    ax[1].set_title("Chosen references (St0)")
    ax[1].legend(fontsize=8)

    for j in range(St.shape[0]):
        ax[2].plot(energies, St[j], lw=1.8, color=cmap(j % 10), label=f"Component_{j+1}")
    ax[2].set_title("Optimized pure spectra (St)")
    ax[2].legend(fontsize=8)

    idx = np.arange(1, n_obs + 1)
    for j in range(C.shape[1]):
        ax[3].plot(idx, C[:, j], "-o", ms=4, color=cmap(j % 10), label=f"Component_{j+1}")
    ax[3].set_title("Concentration profiles (C), input order")
    ax[3].set_xlabel("Index (1..N)")
    ax[3].legend(fontsize=8)

    for i in range(n_obs):
        ax[4].plot(energies, Xhat[i], lw=0.8, color="0.5", alpha=0.7)
    ax[4].set_title("Reconstructed data (C . St)")

    for i in range(n_obs):
        ax[5].plot(energies, E[i], lw=0.7, color="0.5", alpha=0.7)
    ax[5].axhline(0, color="k", lw=0.6)
    ax[5].set_title(f"Residuals  (max |E| = {np.abs(E).max():.2e})")

    for a in (ax[0], ax[1], ax[2], ax[4], ax[5]):
        a.set_xlabel(xlabel)
        a.set_ylabel("Intensity")
    ax[3].set_ylabel("C")

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    plt.show()


# =====================================================================
# EXECUTION
# =====================================================================

print("=" * 70)
print("MCR-ALS: reference testing (manual spectral guess)")
print("spectrochempy:", getattr(scp, "version", getattr(scp, "__version__", "?")))
print("=" * 70)

D, energies, attr_names, axis_is_energy = read_input(in_data)
n_obs, n_feat = D.shape
print(f"Input matrix: {n_obs} spectra x {n_feat} variables")
if np.any(D < 0):
    print(f"Note: {int((D < 0).sum())} negative values in the data.")

validate_reference_indices(REFERENCE_INDICES, n_obs)
N_COMPONENTS = len(REFERENCE_INDICES)
print(f"\nChosen references (input rows): {REFERENCE_INDICES}")
print(f"N_COMPONENTS = {N_COMPONENTS}")

cum = svd_report(D, N_SVD_SHOW)
print(f"\nCumulative variance with {N_COMPONENTS} comp.: {cum[N_COMPONENTS - 1]:.5f} %")

if N_COMPONENTS == n_obs:
    raise ValueError(
        f"N_COMPONENTS ({N_COMPONENTS}) equals the number of spectra ({n_obs}): "
        f"MCRALS would read the spectral guess as a concentration matrix. Use fewer references."
    )

St0 = D[[idx - 1 for idx in REFERENCE_INDICES], :].copy()

if UNIMODALITY:
    order, inv_order = pca_order(D, PC_INDEX, PC_ASCENDING)
    order_label = f"unimodality ON (PC{PC_INDEX} {'asc' if PC_ASCENDING else 'desc'} order)"
else:
    order = np.arange(n_obs)
    inv_order = order
    order_label = "unimodality OFF (input order)"
print(f"\n{order_label}")

D_fit = D[order, :]
X = scp.NDDataset(D_fit, name="X")
X.set_coordset(
    y=scp.Coord(np.arange(n_obs), title="observation"),
    x=scp.Coord(energies, title="variable"),
)

print("\n--- MCR-ALS ---")
mcr, applied = build_mcrals(UNIMODALITY)
for key in sorted(applied):
    print(f"   {key:24s} = {applied[key]!r}")
mcr.fit(X, scp.NDDataset(St0))

C_fit = np.asarray(mcr.C.data, dtype=float)
St = np.asarray(mcr.St.data, dtype=float)

C = C_fit[inv_order, :]

Xhat, E, lof, r2 = diagnostics(D, C, St, St0, REFERENCE_INDICES)

out_data = concentration_table(C)
out_object = spectra_table(St0, St, attr_names)
out_learner = None
out_classifier = None

print(f"\nout_data   : {len(out_data)} rows in original order, {len(out_data.domain.attributes)} columns")
print(f"out_object : {len(out_object)} rows (guess + optimized), {len(out_object.domain.attributes)} variables")
print("To recover your metadata: use Merge Data on (Row Index) against the original table.")

if PLOT:
    make_plots(D, energies, St0, C, St, Xhat, E, lof, axis_is_energy, order_label, REFERENCE_INDICES)
