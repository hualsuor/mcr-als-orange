# Design notes

This document explains where the MCR-ALS widgets come from, which problems were found during
their development, and why the code works the way it does. It is meant for users who want to
understand their results, and for anyone who wants to change the code.

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

### 1. The results depended on the order of the spectra

At ID21, spectra are often collected on several points of a map. These points are
independent: point 5 does not come "after" point 4 in any physical sense. However, when the
same spectra were loaded in a different order, the earlier widgets gave different results.
The pure spectra changed, and so did the proportion of each species on each point. This
should not happen: the chemistry of a sample does not depend on the order of the rows in a
file.

### 2. A hidden constraint was active by default

The cause was a default setting of SpectroChemPy, the library that performs the MCR-ALS
calculation. In SpectroChemPy 0.6.9, the version used here, the concentration of every
component is forced by default to rise and then fall only once along the list of spectra.
This makes sense for a kinetic experiment or a chromatogram, where the spectra follow time and
a species appears, reaches a maximum and disappears. It makes no sense for a set of points on a
map. For example, in a map of copper corrosion products, Cu(II) can be high on point 3, low on
point 4 and high again on point 5. The constraint does not allow this, so the calculation
distorts the result to fit it. When the order of the points changes, the distortion changes
too. Users who keep the default settings of the library are not aware of this constraint.

### 3. The starting guess also assumed an evolution

MCR-ALS needs a first guess to start the calculation. One common way to build it is evolving
factor analysis (EFA), which looks at where each species appears and disappears along the
series of spectra. This works well for a titration, a temperature ramp or a depth profile. On
points taken from a map, in the order in which they happened to be saved, there is no
evolution to follow. The first guess then depends on the order of the file, and so does the
final result.

### 4. The widgets depended on the metadata

Earlier versions used metadata columns, such as sample names, inside the widget to keep track
of the spectra. This tied the widgets to one specific table layout. A table prepared in a
slightly different way could not be used directly.

## Design decisions and why

### The spectra are tracked by their position only

The widgets now read only the spectra, not the metadata. Each spectrum keeps its original
position in the input table, and this position is written next to the results. Users can then
join the results back to their own information (sample name, point of interest, tags from the
acquisition) with the standard Merge Data widget of Orange. In this way, the widgets work with
any table, and no information is lost.

### The hidden constraint is switched off by default

The constraint described in problem 2 is now off unless the user switches it on. It should
only be used when the spectra really follow an evolution, for example a series collected
during heating. When it is switched on, the widget first sorts the spectra in a reproducible
way (see the next point), so that the result does not depend on the order of the file.

### The spectra are sorted before the first guess, then put back in order

To give EFA a series to follow, the widget sorts the spectra along their main source of
variation, found by principal component analysis (PCA). In a map that contains metallic copper
and copper oxides, for example, this can sort the spectra from the most metallic to the most
oxidized. EFA and MCR-ALS are run on this sorted series. At the end, the results are put back
in the original order of the input table, so the link with the metadata is kept.

### A reference testing widget

Users often have candidate reference spectra, for example metallic copper, Cu2O and CuO from
the ID21 database, and want to know whether these compounds are present in their samples. The
reference testing widget starts the calculation from the references chosen by the user. The
calculation then refines these spectra to fit the data. At the end, each refined spectrum is
compared with the reference it started from. If the two are still very similar, the widget
reports GOOD FIT. If they are less similar, it reports CHECK, and if the calculation moved far
away from the reference, it reports POOR FIT. A poor fit suggests that the true compound in the
sample is different, for example a Cu(II) species other than the oxide. The opposite is not
always true: because the edge jump dominates XANES spectra, a wrong reference can still give
GOOD FIT, so the verdict must be read together with the plots. This widget replaced
an earlier automatic method (SIMPLISMA), because it makes the choice of the starting spectra
explicit and answers a question that users ask often.

### Help to choose the number of components

The number of components (species) is the most important choice in MCR-ALS. Both widgets print
a table that shows how much of the signal is explained by one, two, three or more components.
When the curve stops improving, adding more components usually only describes noise.

### Warnings when the result is not reliable

Both widgets report how well the result reproduces the measured spectra. They also give a
warning when a component becomes flat, when a component is almost identical to one single
measured spectrum, or when a component is almost absent from most of the points. These are
the usual signs that too many components were requested.

### Two separate outputs

The first output contains the proportions of each component, one row per measured spectrum,
as raw values and as percentages. This is the result that most users join with their metadata
and plot on a map or per sample. The second output contains the recovered spectra of the pure
components. It can be connected directly to the Spectra widget and compared with known
references. In the reference testing widget, this output also contains the starting
references, so the user can see how much each one changed.

### A reliable installation

The widgets depend on several libraries that must work together: Orange, SpectroChemPy and the
usual scientific Python packages. With uncontrolled versions, installing one library can
silently update another one and break Orange. For this reason, the installer creates a
separate environment with fixed versions, and it prevents later steps from changing the
versions already installed. An older component of the Python installation tools is also kept,
because the setup still needs it to start. Finally, the Orange-Spectroscopy add-on is
installed as an optional last step. The MCR-ALS widgets do not need it; only the example
workflow does, for spectra display and normalization. If this step fails, the rest of the
installation is kept and the user is told how to install the add-on from Orange.

## Validation

A synthetic copper dataset is included to test the widgets on a case where the right answer
is known. It is built from three real Cu K-edge reference spectra: metallic copper (Cu(0)),
Cu2O (Cu(I)) and CuO (Cu(II)).

- **Mixtures.** The file contains the three references and 1000 mixture spectra. Each mixture
  is a combination of the three references in random proportions, with added random noise,
  similar to a map where each point contains a different amount of each copper species. The
  true composition of each mixture is written in its name, for example "Mix 1: Cu(0) 40%,
  Cu2O (Cu(I)) 59%, CuO(II) 1%". The proportions found by the widgets can therefore be
  compared directly with the true ones. The dataset can be regenerated exactly with
  `example_cu/scripts/simulate_cu_mixtures.py`.
- **Distorted references.** To test the reference testing widget, a set of "wrong" references
  was made. They look like a different compound with the same oxidation state: the edge is
  shifted, and the oscillations after the edge are stretched, stronger and slightly modified.
  The region before the edge is not changed. A simple energy shift was not enough, because it
  looks more like a calibration problem than a different compound. The script is
  `example_cu/scripts/make_distorted_references.py`.

The tests were run with the package versions listed in `requirements.txt`, on the spectra
without normalization. The following results were obtained:

- **EFA widget, 1000 mixtures.** The recovered spectra are practically identical to the true
  references. The proportions found differ from the true ones by about 2–3 % on average, and
  by about 10 % at most. When the spectra are loaded in a different order, the results are the
  same. Only the numbering of the components can change.
- **Reference testing with the true references.** GOOD FIT for the three components.
- **Reference testing with the distorted references.** GOOD FIT for Cu(0) and Cu(II), CHECK for
  Cu(I). Two of the three wrong references were therefore not detected by the verdict. The
  reason is that in XANES the edge jump dominates the spectrum, so even a distorted reference
  remains very similar to the true one. However, the calculation still corrected the wrong
  references: the refined spectra end very close to the true ones.

The same tests can be repeated with the example workflow, `workflow/mcrals_cu_example.ows`.
The workflow normalizes the spectra before the calculation, so its values can differ slightly
from the ones above.

## Advantages

- **Many spectra at once.** Hundreds or thousands of spectra, for example all the points of a
  XANES map, can be analysed together in a short time.
- **No references needed in advance.** MCR-ALS recovers the spectra of the pure components and
  their proportion on each point, even when no reference spectra are available.
- **A link with linear combination fitting.** The recovered spectra can be used as references
  in a linear combination fit (LCF). The results can then be compared with an LCF made with
  references from a database, which helps to identify the species present.
- **Inside Orange.** No programming is needed. The widgets run inside the workflows that ID21
  users already use, next to normalization, PCA and clustering.
- **Not only XANES.** The method can be applied to any set of spectra or signals that are
  mixtures of several contributions, for example IR, Raman, UV-Vis or XRF data.

## Limitations

- **A data analysis method, not a proof.** MCR-ALS is only a method of data analysis. Its
  results should always be compared with other methods of analysis and with other
  characterization techniques. It is a useful tool, but like every method it has risks and
  limits.
- **More than one answer is possible.** Different starting guesses and settings can give
  different results that reproduce the data equally well. It is good practice to compare both
  widgets and to check the recovered spectra against known references when possible.
- **The sorted order is not a real evolution.** Sorting the spectra by their main variation
  helps to build a good starting guess, but it does not describe a physical process. The
  profiles along this order should not be read as a kinetics or as a spatial gradient. The
  constraint described in problem 2 should stay off unless the data really follow an
  evolution.
- **The number of components is chosen by the user.** The table printed by the widgets helps,
  but there is no automatic choice.
- **The fit verdict is only a guide.** GOOD FIT, CHECK and POOR FIT are based on fixed limits
  chosen from experience, not on a statistical test. In XANES, the edge jump makes different
  spectra look very similar, so a GOOD FIT does not prove that the reference is the right
  compound. The plots should always be checked, especially the region after the edge.
- **The code is stored twice.** The widget code is in the `widgets` folder and also inside the
  example workflow. A change in one place must be copied to the other.
- **The installer is for Windows only.** On other systems, the packages listed in
  `requirements.txt` can be installed with pip.

## Technical notes

- **Software versions:** Python 3.10.14, Orange 3.36.2, SpectroChemPy 0.6.9, numpy 1.26.4,
  scipy 1.15.2, pandas 2.3.3, matplotlib 3.10.9, scikit-learn 1.3.2, PyQt 5.15.10,
  setuptools 80.10.2 (must stay below 81, because newer versions no longer include
  `pkg_resources`), Orange-Spectroscopy 0.6.13 (optional).
- **SpectroChemPy default:** in version 0.6.9, `MCRALS` uses `unimodConc="all"`. The widgets
  set it to `[]` unless `UNIMODALITY = True`.
- **Main settings** (in the `CONFIGURATION` block of each widget): `N_COMPONENTS`,
  `EXCLUDE_INDICES` (EFA widget), `REFERENCE_INDICES` (reference testing widget, 1-based input
  rows), `PC_INDEX` and `PC_ASCENDING` (component and direction used to sort the spectra),
  `UNIMODALITY` (default `False`).
- **Other defaults:** non-negativity on concentrations and spectra, no closure, `nnls` solver
  for both, at most 200 iterations.
- **Number of components:** singular values of the uncentered data matrix, which matches the
  bilinear model D = C·Sᵀ + E. Sorting uses PCA scores on mean-centred data.
- **Reference testing verdict:** Pearson correlation r between each starting and refined
  spectrum. GOOD FIT if |r| ≥ 0.98, CHECK if |r| ≥ 0.90, otherwise POOR FIT.
- **Warnings:** a refined spectrum with |r| > 0.999 against a measured spectrum is flagged as
  a possible degenerate solution; a component below 1 % of its maximum in more than half of
  the spectra is flagged as absent. Fit quality is reported as LOF and R².
- **Outputs:** `out_data` contains the concentrations (raw and as % of the row sum) with an
  `Index` meta column holding the original 1-based position. `out_object` contains the
  resolved spectra; in the reference testing widget it also contains the starting spectra,
  tagged by a `Source` column (Guess or Optimized).
- **Synthetic mixtures:** 1003 rows in `simulated_cu_mixtures.tab` (3 references + 1000
  mixtures). Fractions drawn from a Dirichlet(1,1,1) distribution (they sum to 1); additive
  white Gaussian noise with σ = 0.025; random seed 0.
- **Validation values** (non-normalized spectra): correlation of the EFA-recovered spectra with
  the true references ≥ 0.9999. Reference testing with the distorted references: Cu(0)
  r = 0.980 (GOOD FIT), Cu(I) r = 0.948 (CHECK), Cu(II) r = 0.986 (GOOD FIT).
- **Distorted references:** edge shift 2 eV, post-edge energy stretch 6 %, post-edge
  amplitude × 1.30, smooth onset over 5 eV after the edge, baseline smoothing 5 eV, added
  oscillation with a period of 15 eV and an amplitude of 0.05.

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
