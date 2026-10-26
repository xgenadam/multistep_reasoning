# Future projects (noted 2026-10-26, from a conversation with the user)

These are projects in their own right (the user: "those should be noted as future projects in their own right, not
just tests of the agent"). Each has value without the harness. Each could also become a long, checkable task for it,
which ties them to the north star: longer, more complex tasks such as reproducing scientific work.

None is scheduled. Current work (the lead/worker redesign, E-1, `lead-worker.md`) comes first. Datasets and prior
work below are from memory and need checking (contents, licence, availability) before any is relied on. Under the
repo's rules, third-party code and data are referenced by pinned revision and sha256, fetched into ignored paths,
never committed.

## 1. A GPU-native, Python plane-wave DFT code (Quantum ESPRESSO's core, in PyTorch)

- **What:** reproduce the core of `pw.x` (plane-wave pseudopotential DFT) in Python, on the GPU (PyTorch, or JAX,
  CuPy). The user has worked with QE and prefers Python to its codebase.
- **Value on its own:** a hackable, differentiable DFT code that runs on commodity GPUs. Differentiability opens
  gradient-based workflows: fitting, inverse design, learned components.
- **Stages, each with reference numbers:**
  1. Empirical-pseudopotential band structures (Cohen–Bergstresser, Si).
  2. A Kohn–Sham SCF with LDA: plane waves, local pseudopotential, GPU FFTs, k-points, Davidson-type eigensolver,
     Pulay mixing.
  3. Nonlocal norm-conserving pseudopotentials (UPF files) and the Ewald energy.
  4. Forces and stress, then relaxation. The user's main use of QE was relaxations.
  5. Scaling to larger cells.
- **Validation:** QE run on the same inputs, in its own container. QE is GPL, so none of its code is committed; the
  rebuild is clean-room from the physics.
  - total energy within about 1 meV per atom;
  - lattice constants and band energies;
  - relaxed structures.
- **Prior work to learn from:**
  - DFTK.jl (Julia);
  - GPAW (Python/C, GPU);
  - PySCF and GPU4PySCF (Gaussian basis, periodic systems);
  - SIRIUS (a GPU plane-wave library);
  - DQC (differentiable quantum chemistry in PyTorch).
- **Pseudopotentials:** PseudoDojo or SSSP, at pinned versions.

## 2. Better initial inverse Hessians for BFGS relaxations

- **What:** a method for the initial inverse Hessian in BFGS structure relaxation. The user developed one earlier
  ("not great, not terrible").
- **Value on its own:** fewer force evaluations per relaxation, which is most of the cost of a relaxation workflow.
- **Evaluation:**
  - evaluations to converge (forces under a threshold) and robustness, over a fixed mixed set: molecules, strained
    bulk, surfaces, defects, interfaces;
  - against a scaled identity, a Lindh-style model Hessian, the exponential preconditioner (ASE), and the user's
    method;
  - **dataset:** Open Catalyst (OC20) relaxations on slabs, with full trajectories. Licence believed CC-BY; to check.
- **Links:** project 1's relaxation stage, and project 3's interfaces, where two stiffnesses meet and generic guesses
  struggle.

## 3. Interfaces between bulk materials: boundary conditions periodic in 2 of 3 dimensions, bulk beyond

- **What:** simulate a boundary between two materials that are bulk on either side, periodic in-plane only, with
  "conditioning" for the bulk beyond the simulated region. That replaces the usual slab supercells, which create two
  interfaces, finite thickness and forced lattice matching.
- **State of the art, as recalled (to check):**
  - **Done in specific forms:**
    - Inglesfield embedding and surface Green's function matching;
    - layer/screened KKR for semi-infinite systems and interfaces;
    - NEGF-DFT transport codes with semi-infinite electrodes (TranSIESTA, Smeagol, QuantumATK);
    - in QE, PWcond (transport between semi-infinite leads) and ESM (Otani & Sugino 2006, modified boundary
      conditions along the normal).
  - **Not routine, and partly open:**
    - plane-wave GPU codes with true semi-infinite bulk on both sides;
    - incommensurate interfaces (no common in-plane period; recent configuration-space work for 2-D
      heterostructures);
    - self-consistent far-field electrostatics (band offsets, interface dipoles).
- **Validation by limits, even for a new method:**
  - the same material on both sides reproduces bulk;
  - results converge to thick-slab supercell results;
  - known band offsets (Si/Ge, GaAs/AlAs, …);
  - charge neutrality;
  - the potential settles to each bulk's value.
- **Extensions:**
  - **Interface structure search (the user's idea): simulated annealing, and Monte Carlo swapping candidates and
    relaxing.**
    - Search with a universal ML interatomic potential (MACE-MP-0, CHGNet, M3GNet; PyTorch).
    - Re-rank the best with DFT (project 1).
    - Baselines: lattice-matching builders (pymatgen, Zur–McGill), USPEX/CALYPSO interface modes, basin hopping,
      hybrid MC/MD with swaps.
    - Grade against known interface and grain-boundary structures and energies (a Materials Project grain-boundary
      database, about 2020; surface energies, Tran et al. 2016; C2DB and JARVIS-2D heterostructures; to check), and
      against experimentally observed epitaxial orientation relationships.
  - **Growth on a substrate (the user):** kinetic Monte Carlo of deposition and diffusion on a fixed slab. Validated
    against classic growth experiments: island-density scaling, layer-by-layer oscillations.
  - **Processing on a static plane (the user: lithography):** the atomistic end first (atomic-layer deposition and
    etching on a fixed surface). Full lithography is mostly process-scale (resist chemistry, exposure, etching), a
    later stretch. "It needs refinement, but it's a start" (the user).

## 4. Biological simulation, and a cell you can watch

- **What:**
  - stochastic simulations of the central dogma: Gillespie gene expression (DNA → mRNA → protein, degradation),
    with telegraph-model bursting;
  - population genetics (Wright–Fisher);
  - DNA sequence evolution (Jukes–Cantor, Kimura);
  - DNA melting (nearest-neighbour thermodynamics);
  - later, coarse-grained DNA mechanics (oxDNA-style).
- **The capstone, "a cell in a browser":** an interactive page showing genes switching, polymerases transcribing,
  ribosomes translating, molecules diffusing and decaying.
- **Value on its own:** teaching, outreach, intuition for noise and bursting in expression, and a base to grow
  toward whole-cell models.
- **Scientific anchors:**
  - the Karr et al. (2012) whole-cell model of *Mycoplasma genitalium*;
  - the 4-D model of the JCVI-syn3A minimal cell (Cell, 2022).
- **Validation:** exact theory where it exists:
  - Poisson mRNA counts with mean k/γ for constant expression, and the telegraph model's Fano factor;
  - fixation probabilities and heterozygosity decay;
  - substitution formulas;
  - published nearest-neighbour parameters.

## 5. Rebuilding open-source projects from a spec and their tests

- **What:** we write a spec of an open-source project. The model, or a developer, gets the spec, a selection of the
  project's tests and the public interface, minus the imports that reveal the internal structure, and builds it.
- **Value on its own:** clean-room reimplementations (for instance a GPU or pure-Python port of a library), and a
  clear measure of building from a spec.
- **Evaluation:** visible tests against held-out tests (the gap shows following the tests against building the real
  thing). Size can be tuned from small libraries to multi-package projects.
- **Prior art:** Commit0 (rebuilding Python libraries from docs and unit tests).
- **Risks:** memorisation of popular projects (prefer small, obscure or post-cutoff ones, or rename the API), and
  licences (permissive projects; tests fetched at pinned revisions, never committed).

## 6. Reproducing scientific papers

- **What:** reproduce the computational results of selected papers, across ML methods, numerical and physics
  simulation, statistics and economics replications, bioinformatics, biological simulation (the user: "all of those").
- **Grading:** in order of preference:
  - numeric targets within a tolerance;
  - hidden tests on functions the task specifies;
  - rubric items by a judge model (PaperBench-style).
- **Constraints:**
  - experiments must run on this box in minutes to an hour;
  - memorisation (prefer lesser-known or post-cutoff papers; grade only numbers the run computed, with logs; perturb
    the setup);
  - papers referenced by arXiv id;
  - data pinned and fetched, never stored.
- **Prior art:** PaperBench, CORE-Bench, SciCode, MLE-bench.

## As tests of the harness (one use among others)

A difficulty ladder for the agent work, if and when these are used that way:

| Tier | Tasks |
| --- | --- |
| v1 | Single files with specified functions (done) |
| v2 | Multi-file projects; small open-source rebuilds (5) |
| v3 | Biological simulations with known theory (4); mini-papers (6) |
| v4 | DFT stages 1–3 (1); larger rebuilds; one-table papers |
| v5 | Relaxation and the initial-Hessian task (1, 2); the cell in a browser (4); full papers |
| v6, open research | Interfaces with bulk beyond, structure search, growth (3), graded by limits and known data |

From v3 up, the harness needs sandboxed code execution for workers: simulations have to be run to be checked.
