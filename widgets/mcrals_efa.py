# -*- coding: utf-8 -*-
"""
MCR-ALS with an EFA concentration initial guess (PCA-ordered).

Input  (in_data): one Orange Table, all rows treated as samples
                   unless listed in EXCLUDE_INDICES.
Output (out_data): concentration profiles, one row per included
                    spectrum, meta Index = original input position.
Output (out_object): k optimized pure spectra.
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

N_COMPONENTS = 3           # k; check the printed SVD table before fixing this

EXCLUDE_INDICES = []       # 1-based input rows to drop entirely from the calculation

PC_INDEX = 1                # PCA component used to order rows before EFA
PC_ASCENDING = True         # sort direction for that PCA order

EFA_CUTOFF = None           # None = no cutoff; a value trims small eigenvalues

UNIMODALITY = False          # impose unimodal C (only valid for a real evolving series)

NONNEG_CONC = "all"         # non-negativity constraint on C
NONNEG_SPEC = "all"         # non-negativity constraint on St
CLOSURE_CONC = []           # [] = no closure; list of components, e.g. [0, 1, 2] = row sums of C equal 1 ("all" fails in spectrochempy 0.6.9)
NORM_SPEC = "euclid"        # St normalization convention (scale only)
SOLVER_CONC = "nnls"        # C solver: "lstsq" | "nnls" | "pnnls"
SOLVER_SPEC = "nnls"        # St solver
MAX_ITER = 200              # max ALS iterations
MAXDIV = 10                  # tolerated divergent iterations
TOL_RESIDUAL_CHANGE = 1e-5      # convergence tolerance (spectrochempy >= 0.12)
TOL_PERCENT_LEGACY = 1e-3       # convergence tolerance (older spectrochempy)

PLOT = True                  # show diagnostic plots
N_SVD_SHOW = 6                # singular values printed in the SVD report
R_DEGENERACY = 0.999          # |r| above this vs an experimental row flags degeneracy
NEARZERO_FRAC = 0.01          # concentration below this fraction of max flags near-zero
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


def apply_exclusions(D, exclude_indices):
    """Drop EXCLUDE_INDICES (1-based, original positions). Returns the filtered
    matrix and the array of kept original 1-based positions, in order."""
    n_obs = D.shape[0]
    if not exclude_indices:
        return D, np.arange(1, n_obs + 1)

    exclude_set = set(exclude_indices)
    for idx in exclude_set:
        if idx < 1 or idx > n_obs:
            raise ValueError(f"EXCLUDE_INDICES has {idx}, out of range (1..{n_obs}).")

    kept_positions = np.array([i for i in range(1, n_obs + 1) if i not in exclude_set], dtype=int)
    print(f"\nEXCLUDE_INDICES active: dropping {len(exclude_set)} row(s) -> {sorted(exclude_set)}")
    print(f"{len(kept_positions)} of {n_obs} rows remain for PCA/EFA/MCR-ALS.")
    return D[kept_positions - 1, :], kept_positions


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


def efa_c0(X, k, cutoff):
    """Build C0 with EFA, tolerant of the n_components/n_pc and fit API differences."""
    model = None
    for kw in ({"n_components": k}, {"n_pc": k}):
        try:
            model = scp.EFA(cutoff=cutoff, log_level="WARNING", **kw)
            break
        except Exception:
            continue
    if model is None:
        model = scp.EFA(log_level="WARNING")
        _set(model, ["n_components", "n_pc"], k)
        _set(model, ["cutoff"], cutoff)

    try:
        result = model.fit_transform(X)
    except Exception:
        model.fit(X)
        result = model.transform()

    return np.asarray(getattr(result, "data", result), dtype=float)


def sanitize_c0(C0):
    """Clip EFA eigenvalues to >= 0 and scale each column to [0, 1] (scale is
    irrelevant to MCR due to the bilinear model's scale ambiguity)."""
    C0 = np.clip(C0, 0.0, None)
    colmax = C0.max(axis=0).copy()
    colmax[colmax == 0] = 1.0
    return C0 / colmax


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


def diagnostics(D, C, St):
    """LOF/R2, degeneracy and near-zero checks."""
    Xhat = C @ St
    E = D - Xhat
    sse = float(np.sum(E ** 2))
    ssx = float(np.sum(D ** 2))
    lof = 100.0 * np.sqrt(sse / ssx)
    r2 = 1.0 - sse / ssx

    print("\n--- SANITY CHECKS ---")
    print(f"LOF = {lof:.5f} %    R2 = {100.0 * r2:.5f} %")

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

def spectra_table(St, attr_names):
    """k rows: the optimized pure spectra."""
    k = St.shape[0]
    attrs = [ContinuousVariable(n) for n in attr_names]
    comp_var = DiscreteVariable("Component", values=tuple(f"Component_{j+1}" for j in range(k)))
    domain = Domain(attrs, metas=[comp_var])
    M = np.arange(k, dtype=float).reshape(-1, 1)
    return Table.from_numpy(domain, St, metas=M)


def concentration_table(C0, C, kept_positions):
    """One row per included spectrum, original order. EFA guess, raw C and
    fraction (%). Meta Index = original input position (not renumbered)."""
    n_obs, k = C.shape
    csum = C.sum(axis=1, keepdims=True)
    csum[csum == 0] = 1.0
    frac = 100.0 * C / csum

    attrs = ([ContinuousVariable(f"C0_Component_{j+1}") for j in range(C0.shape[1])] +
             [ContinuousVariable(f"C_Component_{j+1}") for j in range(k)] +
             [ContinuousVariable(f"Frac_Component_{j+1}") for j in range(k)])
    domain = Domain(attrs, metas=[ContinuousVariable("Index")])

    X = np.hstack([C0, C, frac])
    M = kept_positions.astype(float).reshape(-1, 1)
    return Table.from_numpy(domain, X, metas=M)


# =====================================================================
# PLOTS
# =====================================================================

def make_plots(D, energies, C0_sorted, C_sorted, C, St, E, lof, axis_is_energy, order_label, kept_positions):
    cmap = plt.get_cmap("tab10")
    xlabel = "Energy" if axis_is_energy else "Variable index"
    n_obs = D.shape[0]

    fig, ax = plt.subplots(2, 3, figsize=FIGSIZE)
    ax = ax.flatten()
    fig.suptitle(f"EFA -> MCR-ALS  ·  k={St.shape[0]}  ·  {order_label}  ·  LOF={lof:.4f} %", fontsize=12)

    for i in range(n_obs):
        ax[0].plot(energies, D[i], lw=0.8, color="0.5", alpha=0.7)
    ax[0].set_title(f"Data included in the calculation ({n_obs} spectra)")
    ax[0].set_xlabel(xlabel)
    ax[0].set_ylabel("Intensity")

    pos = np.arange(1, n_obs + 1)
    for j in range(C0_sorted.shape[1]):
        ax[1].plot(pos, C0_sorted[:, j], "-o", ms=4, color=cmap(j % 10), label=f"Component_{j+1}")
    ax[1].set_title("EFA initial guess (C0), PCA order")
    ax[1].set_xlabel("Position in PCA order")
    ax[1].set_ylabel("C0 (norm.)")
    ax[1].legend(fontsize=8)

    for j in range(St.shape[0]):
        ax[2].plot(energies, St[j], lw=1.8, color=cmap(j % 10), label=f"Component_{j+1}")
    ax[2].set_title("Optimized pure spectra (St)")
    ax[2].set_xlabel(xlabel)
    ax[2].set_ylabel("Intensity")
    ax[2].legend(fontsize=8)

    for j in range(C_sorted.shape[1]):
        ax[3].plot(pos, C_sorted[:, j], "-o", ms=4, color=cmap(j % 10), label=f"Component_{j+1}")
    ax[3].set_title("Optimized C, PCA order (what ALS saw)")
    ax[3].set_xlabel("Position in PCA order")
    ax[3].set_ylabel("C")
    ax[3].legend(fontsize=8)

    for j in range(C.shape[1]):
        ax[4].plot(kept_positions, C[:, j], "-o", ms=4, color=cmap(j % 10), label=f"Component_{j+1}")
    ax[4].set_title("Optimized C, Index = original input position")
    ax[4].set_xlabel("Index (original position)")
    ax[4].set_ylabel("C")
    ax[4].legend(fontsize=8)

    for i in range(n_obs):
        ax[5].plot(energies, E[i], lw=0.7, color="0.5", alpha=0.7)
    ax[5].axhline(0, color="k", lw=0.6)
    ax[5].set_title(f"Residuals  (max |E| = {np.abs(E).max():.2e})")
    ax[5].set_xlabel(xlabel)
    ax[5].set_ylabel("Residual")

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    plt.show()


# =====================================================================
# EXECUTION
# =====================================================================

print("=" * 70)
print("MCR-ALS with EFA concentration guess")
print("spectrochempy:", getattr(scp, "version", getattr(scp, "__version__", "?")))
print("=" * 70)

D_full, energies, attr_names, axis_is_energy = read_input(in_data)
n_obs_full = D_full.shape[0]
print(f"Input matrix: {n_obs_full} spectra x {D_full.shape[1]} variables")
if np.any(D_full < 0):
    print(f"Note: {int((D_full < 0).sum())} negative values in the data.")

D, kept_positions = apply_exclusions(D_full, EXCLUDE_INDICES)
n_obs, n_feat = D.shape

cum = svd_report(D, N_SVD_SHOW)
print(f"\nN_COMPONENTS = {N_COMPONENTS}  ->  cumulative variance: {cum[N_COMPONENTS - 1]:.5f} %")

if n_obs == n_feat:
    print(f"   *** WARNING: square matrix ({n_obs}x{n_feat}); MCRALS tells C0 from St0 "
          f"only by the guess shape, so the interpretation can be ambiguous.")

order, inv_order = pca_order(D, PC_INDEX, PC_ASCENDING)
order_label = f"PC{PC_INDEX} {'asc' if PC_ASCENDING else 'desc'} order  ·  unimodality {'ON' if UNIMODALITY else 'OFF'}"
print(order_label)

D_sorted = D[order, :]
X_sorted = scp.NDDataset(D_sorted, name="X_sorted")
X_sorted.set_coordset(
    y=scp.Coord(np.arange(n_obs), title="pseudo-evolution index"),
    x=scp.Coord(energies, title="variable"),
)

print("\n--- EFA CONCENTRATION GUESS (on PCA order) ---")
C0_sorted = sanitize_c0(efa_c0(X_sorted, N_COMPONENTS, EFA_CUTOFF))
print(f"C0: {C0_sorted.shape}")
if C0_sorted.shape[1] != N_COMPONENTS:
    print(f"   *** WARNING: EFA returned {C0_sorted.shape[1]} components, not {N_COMPONENTS}.")

print("\n--- MCR-ALS ---")
mcr, applied = build_mcrals(UNIMODALITY)
for key in sorted(applied):
    print(f"   {key:24s} = {applied[key]!r}")
mcr.fit(X_sorted, scp.NDDataset(C0_sorted))

C_sorted = np.asarray(mcr.C.data, dtype=float)
St = np.asarray(mcr.St.data, dtype=float)

C = C_sorted[inv_order, :]
C0 = C0_sorted[inv_order, :]

Xhat, E, lof, r2 = diagnostics(D, C, St)

out_data = concentration_table(C0, C, kept_positions)
out_object = spectra_table(St, attr_names)
out_learner = None
out_classifier = None

print(f"\nout_data   : {len(out_data)} rows (Index = original position), {len(out_data.domain.attributes)} columns")
print(f"out_object : {len(out_object)} pure spectra, {len(out_object.domain.attributes)} variables")
print("To recover your metadata: use Merge Data on (Row Index) against the original table.")

if PLOT:
    make_plots(D, energies, C0_sorted, C_sorted, C, St, E, lof, axis_is_energy, order_label, kept_positions)
