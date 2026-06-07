# Research: Liquid Inventory Routing Problem (IRP) Patterns

Analysis of high-quality solutions (e.g., HUST SMART results for Set B) reveals several key strategies that distinguish a competitive solver from a simple greedy constructor.

## 1. Holistic Smoothness & "Top-Up" Strategy
- **Aggressive Delivery**: Top-tier solutions deliver significantly more than the minimum required volume. In Instance 2.12, the delivered quantity (2.28M) is nearly double the minimum required (1.14M).
- **Inventory Buffering**: Rather than delivering "just-in-time" to avoid breaches, the solver "tops up" tanks to near capacity. This creates a large safety buffer and stabilizes fleet demand over the horizon.
- **Smoothness Metrics**: Holistic stability is achieved by maintaining a low Coefficient of Variation (CV) for daily deliveries (~0.30). This ensures that no single day is overwhelmed, allowing for consistent driver scheduling.

## 2. Shift Composition Efficiency
- **Multi-Drop & Multi-Reload**: Shifts are maximized to the driver's legal limit. A single shift often contains 4-8 operations, including multiple reloads at a source.
- **Piggybacking**: Small "topping up" deliveries (e.g., 200-600kg) are inserted into shifts that are already passing near a customer. These have near-zero marginal travel cost but significantly improve inventory safety.
- **Collocation Exploitation**: Points sharing the same geographic location are almost always served together.

## 3. Duration-Based Penalties
- **Deficit-Time Product**: Safety breaches are calculated as `kg * minutes`. The current `roadef-tools penalties` implementation confirms this: `deficit * instance.unit`.
- **Zero-Tolerance for Runouts**: High-quality solutions prioritize eliminating runouts (`safety_kg_min = 0`) even if it requires slightly higher transport costs, as the duration-based penalties accumulate rapidly across the horizon.

## 4. Actionable Heuristics for Solver Improvements

### A. Cluster-Based Insertion
- **Heuristic**: When scheduling a delivery for a "needy" customer, identify all other customers in the same MDS cluster or collocation group.
- **Action**: Attempt to "top up" these neighbors in the same shift if trailer capacity and driver time allow.

### B. Multi-Reload Shift Construction
- **Heuristic**: Extend the greedy constructor to allow multiple source-customer-source cycles within a single shift.
- **Action**: A shift should only end when the driver's `max_driving_duration` or `time_window` is exhausted, not just when the trailer is empty.

### C. Safety-Gap Preemption
- **Heuristic**: Use "Days of Inventory" (DOI) as a priority metric rather than discrete breach steps.
- **Action**: Target customers with the lowest DOI first, and aim to restore them to `Capacity - (SafetyBuffer * DailyDemand)` to maximize the time until the next required visit.

### D. Post-Trim Safety Repair
- **Heuristic**: After "trimming" overfills, the resulting runouts should be fixed by shifting delivery times *earlier* or increasing quantities in *preceding* shifts, rather than just adding new shifts.
