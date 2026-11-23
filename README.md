# MCR-ALS widgets for Orange

Two Python Script widgets for [Orange Data Mining](https://orangedatamining.com/) that run
**MCR-ALS** (Multivariate Curve Resolution – Alternating Least Squares) on XAS/XANES spectra,
using [SpectroChemPy](https://www.spectrochempy.fr/).

MCR-ALS decomposes a set of spectra **D** into pure-component spectra **Sᵀ** and their
concentration profiles **C**, so that D = C·Sᵀ + E.

The package also includes an installer for the Python environment, an example workflow, and
a synthetic Cu K-edge dataset to test the widgets.

For the history of this tool and the reasons behind each design choice, see
[docs/DESIGN_NOTES.md](docs/DESIGN_NOTES.md).

## The two widgets

Both widgets:

- treat every input row as a sample,
- apply non-negativity to C and Sᵀ,
- keep **unimodality off** by default (ID21 spectra usually come from independent points, not
  from an evolving series),
- return results in the original row order, so they can be joined back to the metadata with
  Orange's **Merge Data** widget (by row index),
- print an SVD table (to choose the number of components), the lack of fit (LOF) and R².

| Widget | File | Initial guess |
|---|---|---|
| **EFA concentration guess** | `widgets/mcrals_efa.py` | Builds the initial concentration profiles by evolving factor analysis (EFA). Spectra are first sorted by their score on a principal component chosen by the user, because EFA needs an ordered series. |
| **Reference testing** | `widgets/mcrals_reference_testing.py` | Starts from spectra chosen by the user (e.g. database references). After the fit, it compares each starting spectrum with its resolved spectrum and rates the match as `GOOD FIT`, `CHECK` or `POOR FIT`. |

**Outputs**

- `out_data`: concentration profiles, one row per input spectrum.
- `out_object`: resolved pure spectra (the reference testing widget also returns the starting
  spectra, so you can compare them).

**Settings** are in the `CONFIGURATION` block at the top of each file (number of components,
reference rows, constraints, solver, etc.).

## Requirements

Tested with Python 3.10.14. The exact versions are listed in `requirements.txt`.

| Package | Why it is needed |
|---|---|
| Orange3, PyQt5 | Orange Data Mining and its graphical interface |
| spectrochempy | MCR-ALS, EFA and SVD used by the widgets |
| numpy, scipy, pandas, scikit-learn | Numerical calculations |
| matplotlib | Diagnostic plots of the widgets and the example scripts |
| setuptools (< 81) | spectrochempy 0.6.9 still needs `pkg_resources` |
| Orange-Spectroscopy | **Only for the example workflow** (Spectra and Normalization widgets). The two MCR-ALS widgets do not need it. |

There are two ways to install them:

- **With the installer** (recommended on Windows): see [Installation](#installation-windows-1011)
  below. Orange-Spectroscopy is installed as an optional last step.
- **With pip**, in a Python 3.10 environment:

  ```bat
  pip install -r requirements.txt
  ```

## Installation (Windows 10/11)

1. Run `installer/orange_env_installer.bat` (double-click, or run it from a Command Prompt).
   It installs Miniconda in `%LOCALAPPDATA%\Miniconda3` (if needed), creates a conda
   environment called `orange_env` with Orange 3.36.2, SpectroChemPy 0.6.9 and compatible
   versions of numpy and scikit-learn, and then opens Orange.
   Each step is logged in `installer/install_log.txt`.
2. As a last, optional step, the installer tries to install the **Orange-Spectroscopy** add-on
   (needed only for the example workflow). If this step fails, the rest of the installation is
   kept, and the final message says so. In that case, install it from Orange: go to
   **Options → Add-ons…**, select **Spectroscopy**, and restart Orange.

## Opening Orange

Open the **Anaconda Prompt (Miniconda3)** from the Start menu, or a Command Prompt, and run:

```bat
"%LOCALAPPDATA%\Miniconda3\condabin\conda.bat" activate orange_env
python -m Orange.canvas
```

(In the Anaconda Prompt, `conda activate orange_env` is enough.)

## Opening the example workflow

1. In Orange, go to **File → Open** and select `workflow/mcrals_cu_example.ows`.
2. The data files are loaded with paths relative to the workflow, so keep the folder structure
   as it is.
3. The workflow loads 1000 simulated Cu mixtures and a set of distorted references, normalizes
   them, and runs both widgets. Each widget is connected to a **Concentrations** table and to a
   **Spectra** plot of the resolved spectra.

To use a widget in your own workflow, add a **Python Script** widget, paste the content of the
`.py` file, and edit the `CONFIGURATION` block.

## Example data (synthetic Cu K-edge)

- `cu_references_extracted.tab`: three real references: Cu(0), Cu2O (Cu(I)) and CuO (Cu(II)).
- `simulated_cu_mixtures.tab`: the three references plus 1000 mixtures, with random fractions
  (Dirichlet(1,1,1), summing to 1) and Gaussian noise (σ = 0.025). Seed 0.
- `cu_references_distorted.tab`: "wrong" references (energy shift, stretched post-edge,
  amplified oscillations) to test the reference testing widget.

The data can be regenerated with the scripts in `example_cu/scripts/` (they need numpy, scipy
and matplotlib):

```bat
python example_cu/scripts/simulate_cu_mixtures.py
python example_cu/scripts/make_distorted_references.py
```

## Folder structure

```
MCR-ALS_Orange/
├── installer/
│   └── orange_env_installer.bat      Environment installer (Windows)
├── widgets/
│   ├── mcrals_efa.py                 MCR-ALS, EFA concentration guess
│   └── mcrals_reference_testing.py   MCR-ALS, reference testing
├── workflow/
│   └── mcrals_cu_example.ows         Example Orange workflow
├── example_cu/
│   ├── data/                         Synthetic Cu K-edge data (.tab)
│   ├── scripts/                      Scripts that generate the data and figure
│   └── figures/                      Real vs. distorted references
├── docs/
│   └── DESIGN_NOTES.md               History and design decisions
├── .gitignore
├── LICENSE
├── README.md
└── requirements.txt                  Exact package versions
```

## Citation

If you use these widgets, please cite:

Suarez Orduz, H. A. (2026). MCR-ALS widgets for Orange. https://github.com/hualsuor/mcr-als-orange

A paper describing the ID21 software environment is in preparation.

## License

MIT. See [LICENSE](LICENSE).
