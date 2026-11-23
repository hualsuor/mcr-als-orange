# Design notes

This document explains where the MCR-ALS widgets come from, which problems we found on the
way, and why the code works the way it does. It is meant for users who want to understand the
results, and for anyone who wants to change the code.

## Background

This work started at the ID21 beamline of the ESRF. The first versions were Python scripts run
in Spyder. They were written to analyse µXANES data with MCR-ALS in projects such as the study
of mineralization in SaOS-2 cells and the work on TiO2 nanoparticles in soils.

Earlier versions of the code were used in these published articles:

- Sadurní, R., Molera, J., Hole, C., Suarez Orduz, H. A., Juanhuix, J., Cotte, M. & Pradell, T.
  (2026). Shedding light on the formation mechanisms of Islamic polychrome lusters: A Cu, Fe,
  Ag micro XANES study. *Science Advances*, 12(37), eaeg5529.
  https://doi.org/10.1126/sciadv.aeg5529
- Rossi, F., et al. (2026). Osteogenic differentiation restores physiological mineralization
  pathways in SaOS-2 osteosarcoma cells. *Acta Biomaterialia*, 225, 839–848.
  https://doi.org/10.1016/j.actbio.2026.08.045

The code was then moved into Orange Data Mining as Python Script widgets, so that ID21 users
can run MCR-ALS inside the same workflows they already use for normalization, PCA and
clustering. This version brings together several years of work and many discussions with
colleagues.

## Problems found

### 1. Results depended on the order of the rows

With the same spectra loaded in a different order, the earlier widgets gave different pure
spectra and concentrations. For a set of independent measurement points, the row order has no
physical meaning, so the result should not depend on it.

### 2. Unimodality was on by default

The root cause of problem 1 was a default of SpectroChemPy: in SpectroChemPy 0.6.9, the
version used here, `MCRALS` sets `unimodConc="all"`. This forces every concentration profile to rise and fall
only once along the row axis. That is a sensible default for kinetics or chromatography, where
the rows follow time. For ID21 data, where spectra usually come from independent points of
interest, it imposes a shape that does not exist, and the shape changes when the rows are
reordered. Users who call the library with its default settings do not see this.

### 3. EFA assumes an ordered, evolving series

Evolving factor analysis (EFA) finds where each component appears and disappears along the
rows. This only makes sense when the rows follow an evolution (time, temperature, depth). On a
table of independent points in arbitrary order, EFA has nothing to follow, and the initial
guess it produces depends on the row order.

### 4. Metadata dependence

Earlier versions used metadata columns inside the widget to keep track of the rows. This tied
the widgets to a specific table layout. The current version removes this dependency (see the
first design decision below).

## Design decisions and why

| Decision | Why |
|---|---|
| **Traceability by row index only.** The widgets read only the spectral matrix. Each output row of concentrations carries an `Index` meta column with the original input position. | The widgets work with any table, whatever metadata it has. Users join the results back to their metadata with Orange's **Merge Data** widget, using the row index. |
| **Unimodality off by default** (`UNIMODALITY = False`). The user can switch it on. | It is only valid for a real evolving series (problem 2). When it is on, the widget also orders the rows by a principal component, so the axis of the constraint is explicit and reproducible. |
| **Rows ordered by a principal component before EFA, then returned to the original order.** The EFA widget sorts the spectra by their score on a user-chosen component (`PC_INDEX`, `PC_ASCENDING`), runs EFA and MCR-ALS on that order, and then puts the concentrations back in the input order. | This gives EFA an ordered axis to work on (problem 3), defined from the data and not from the order of the file. The output stays in the input order, so the Merge Data step still works. |
| **SVD report.** Both widgets print the singular values of the uncentered data and their cumulative variance. | The number of components is the most important choice in MCR-ALS. The SVD of the uncentered matrix is the one that matches the bilinear model D = C·Sᵀ + E. |
| **Reference testing widget**, with a verdict per component: `GOOD FIT` (\|r\| ≥ 0.98), `CHECK` (\|r\| ≥ 0.90) or `POOR FIT`. The user chooses some input rows as the initial spectra; after the fit, the widget computes the correlation r between each starting spectrum and its resolved spectrum. | Users often have candidate references and want to know whether they explain the data. If the fit moves far away from a reference, that reference is probably not the right compound. The verdict makes this visible instead of hiding it in the plots. |
| **SIMPLISMA replaced by reference testing.** | Reference testing covers the common case where the user already has candidate spectra, and it makes the choice of starting spectra explicit. |
| **Extra warnings.** Both widgets report LOF and R², flag a component that collapses to a constant, a component almost identical to one experimental spectrum (\|r\| > 0.999), and a component that is close to zero in most samples. | These are the usual signs that the number of components is too high or that the solution is degenerate. |
| **Two outputs: `out_data` and `out_object`.** `out_data` holds the concentration profiles, one row per input spectrum (raw values and relative fractions in %). `out_object` holds the resolved pure spectra as an Orange table; the reference testing widget adds the starting spectra, tagged by `Source` (Guess or Optimized). | Concentrations are the result most users merge with metadata, so they go on the main data output. Spectra go on the second output and can be plotted directly with the Spectra widget. |
| **Installer with frozen versions.** The installer creates a conda environment with fixed versions (Python 3.10.14, Orange 3.36.2, numpy 1.26.4, scikit-learn 1.3.2, PyQt 5.15.10, SpectroChemPy 0.6.9). It freezes what conda resolved before running pip, so pip cannot change those packages. | SpectroChemPy is installed with pip on top of a conda environment. Without the freeze, pip can silently upgrade numpy or scipy and break Orange. |
| **setuptools < 81.** | Newer setuptools versions no longer include `pkg_resources`, which this setup still needs at startup. |
| **Orange-Spectroscopy optional.** The installer tries to install it as a last step. If that fails, the installation is kept and the user is told to install it from Orange's Add-ons menu. | The MCR-ALS widgets do not import it. Only the example workflow needs it (Spectra and Normalization widgets). Earlier installers that included it ran into dependency conflicts. |

## Validation

The package includes a synthetic Cu K-edge dataset, built from three real reference spectra:
Cu(0), Cu2O (Cu(I)) and CuO (Cu(II)).

- **Mixtures.** 1000 spectra, each one f1·ref1 + f2·ref2 + f3·ref3 plus white Gaussian noise
  with σ = 0.025. The fractions come from a Dirichlet(1,1,1) distribution, so they are uniform
  on the simplex and sum to 1. The random seed is fixed (0), so the dataset can be regenerated
  exactly with `example_cu/scripts/simulate_cu_mixtures.py`. Because the true fractions and
  spectra are known, the output of both widgets can be compared with the truth.
- **Distorted references.** To test the reference testing widget, we made "wrong" references
  that look like a different compound with the same oxidation state. They change shape, not
  only position: an edge shift of 2 eV, a 6 % stretch of the post-edge energy scale, a 30 %
  increase of the post-edge oscillation amplitude, and a weak added oscillation (period 15 eV,
  amplitude 0.05). All changes are smooth and start after the edge, so the pre-edge is not
  modified. A pure energy shift would be too easy a test, because it is a common calibration
  problem and not a different compound. The script is
  `example_cu/scripts/make_distorted_references.py`.

The expected behaviour is that reference testing gives `GOOD FIT` with the true references and
`CHECK` or `POOR FIT` with the distorted ones. The results of both widgets on this dataset can
be reproduced with the example workflow, `workflow/mcrals_cu_example.ows`.

## Limitations

- **The PCA order is a pseudo-evolution.** Sorting the spectra by a principal component gives
  EFA an ordered axis, which is useful to build an initial guess. It is not a real physical
  evolution. Do not interpret the concentration profiles along that order as a kinetics or a
  spatial gradient, and do not switch unimodality on unless the data really follow an
  evolution.
- **Rotational ambiguity.** MCR-ALS solutions are not unique. Different initial guesses and
  constraints can give different results with the same fit quality. Compare both widgets, and
  check the resolved spectra against known references when you can.
- **The number of components is chosen by the user.** The SVD report helps, but there is no
  automatic choice.
- **The fit verdict is a heuristic.** The thresholds 0.98 and 0.90 are practical limits, not a
  statistical test.
- **Code is stored twice.** The widget code is in `widgets/*.py` and also inside the example
  workflow (`.ows`). A change in a `.py` file must be copied into the workflow.
- **The installer is for Windows only.** On other systems, use `requirements.txt`.

## Acknowledgements

Thanks to Hiram Castillo-Michel (ID21, ESRF) for a very close collaboration on the development, the
debugging and the philosophy of this approach. Thanks also to the ID21 colleagues and to the
users who tested earlier versions.

## References

**Software**

- Travert, A. & Fernandez, C. SpectroChemPy (version 0.6.9). Zenodo.
  https://doi.org/10.5281/zenodo.3823841 (DOI for all versions).
- Demšar, J., et al. (2013). Orange: Data Mining Toolbox in Python. *Journal of Machine
  Learning Research*, 14, 2349–2353.
- Toplak, M., Read, S. T., Sandt, C. & Borondics, F. (2021). Quasar: Easy Machine Learning for
  Biospectroscopy. *Cells*, 10(9), 2300. https://doi.org/10.3390/cells10092300
  (Quasar is built on Orange and the Orange-Spectroscopy add-on.)
- Toplak, M. et al. (2017). Infrared Orange: Connecting Hyperspectral Data with Machine
  Learning. *Synchrotron Radiation News*, 30(4), 40–45.

**Methods**

- Tauler, R. (1995). Multivariate curve resolution applied to second order data.
  *Chemometrics and Intelligent Laboratory Systems*, 30, 133–146.
  https://doi.org/10.1016/0169-7439(95)00047-X
- de Juan, A. & Tauler, R. (2021). Multivariate Curve Resolution: 50 years addressing the
  mixture analysis problem – A review. *Analytica Chimica Acta*, 1145, 59–78.
  https://doi.org/10.1016/j.aca.2020.10.051
- Maeder, M. & Zuberbühler, A. D. (1986). The resolution of overlapping chromatographic peaks
  by evolving factor analysis. *Analytica Chimica Acta*, 181, 287–291.
