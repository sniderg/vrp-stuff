# Inspiration Sources and Algorithm Techniques

This document details the external repositories, academic papers, and algorithmic techniques that inspired the architecture of this Inventory Routing Problem (IRP) solver.

---

## 1. 1st Place Winner: Ahmed Kheiri (Cardiff University)
* **Paper**: *"Heuristic sequence selection for inventory routing problem"* (Transportation Science, 2020)
* **Core Technique**: **Sequence-Based Selection Hyper-Heuristic with Hidden Markov Models (HMM)**
* **How it works**:
  - Instead of running a single local search heuristic, the solver maintains a set of **16 low-level heuristics** (e.g., node insertions, shift splits, customer swaps, inventory re-allocations).
  - A **Hidden Markov Model (HMM)** learns the transition probabilities between these heuristics based on their success/failure history in preceding iterations.
  - The solver dynamically predicts and executes the most promising sequence of heuristics.

### Relation to Our Implementation
* **ML Route Priors & Probes**: 
  - Our codebase implements ML Route Priors ([roadef_tools/solver/ml_priors.py](file:///Users/graydonsnider/PycharmProjects/Vrp_stuff/roadef_tools/solver/ml_priors.py) and [scripts/train_ml_priors.py](file:///Users/graydonsnider/PycharmProjects/Vrp_stuff/scripts/train_ml_priors.py)), which predict the value/prize of route candidates based on customer inventory states, daily demands, and geographic distance features.
  - We use these predicted prizes to bias candidate route generation and select high-quality sequences, matching the spirit of learning from historical/structural features to guide local search paths.

---

## 2. 3rd Place Finalist: HUST-Smart Team (Huazhong University of Science and Technology)
* **Repository**: [HUST-Smart/ROADEF2016-IRP-Results](https://github.com/HUST-Smart/ROADEF2016-IRP-Results)
* **Paper**: *"A Matheuristic Algorithm for the Inventory Routing Problem"* (Transportation Science, 2020)
* **Core Technique**: **Matheuristic Integration (Metaheuristic + Slave MIP/LP)**
* **How it works**:
  - A **multi-neighborhood local search** is used to explore and modify the structural routing decisions (which customers are visited in which shifts by which drivers).
  - Embedded **Mixed Integer Programming (MIP)** and **Linear Programming (LP)** solvers are called as slave routines to optimize continuous decisions: shift start times, arrival windows, and delivery quantities.

### Relation to Our Implementation
* **Column-Generation (CG) Rescue Loop**:
  - Our column-generation solver ([roadef_tools/solver/column_loop.py](file:///Users/graydonsnider/PycharmProjects/Vrp_stuff/roadef_tools/solver/column_loop.py)) acts as a classic matheuristic.
  - We heuristically generate hundreds of targeted route columns (shifts) using candidate generators ([roadef_tools/solver/candidate_gen.py](file:///Users/graydonsnider/PycharmProjects/Vrp_stuff/roadef_tools/solver/candidate_gen.py)).
  - We then feed these columns to a mathematical programming selector ([roadef_tools/solver/highs_selector.py](file:///Users/graydonsnider/PycharmProjects/Vrp_stuff/roadef_tools/solver/highs_selector.py)) which runs a Mixed Integer Linear Program (MILP) using **HiGHS** (or Gurobi) to choose the optimal, conflict-free combination of shifts and quantities.

---

## 3. Notable Mentions: Column, Cut, and Dinkelbach Decomposition (7th Place, Absi et al.)
* **Paper**: *"A Branch-and-Price-and-Cut Algorithm for the Inventory Routing Problem"*
* **Core Technique**: **Exact Branch-and-Price-and-Cut with Fractional Programming**
* **How it works**:
  - Formulates the IRP using column generation to handle the exponential number of feasible routes.
  - Integrates cutting planes to tighten bounds at the nodes of the branch-and-bound tree.
  - Uses the **Dinkelbach method** to handle the fractional objective function (which minimizes the ratio of total cost to total delivered quantity).

### Relation to Our Implementation
* **Fractional Objective Handling**:
  - Because our objective is the ratio of travel/layover cost to delivered quantity, we track the **Logistic Ratio (LR)** as our primary metric.
  - In our master selector ([roadef_tools/solver/highs_selector.py](file:///Users/graydonsnider/PycharmProjects/Vrp_stuff/roadef_tools/solver/highs_selector.py)), we handle this non-linear fractional objective by iteratively solving linear/MIP approximations or optimizing quantity delivery bounds, matching the practical insights of Dinkelbach decomposition.
