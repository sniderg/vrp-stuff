# ROADEF/EURO 2016 IRP Rules Index

This is a working index derived from the official v2.2 checker source in
`roadef_2016_data/checker_v2/Challenge_Roadef_EURO_Checker_V2/IRP_Roadef_Challenge_Checker.cs`.
The official checker remains the source of truth; this index is for interpreting and debugging route edits.

## Main Checker Groups

| Group | Checker method | Meaning |
| --- | --- | --- |
| LAY | `checkLayovers` | Layover placement rules. |
| SHI | `checkShifts` | Shift, operation, timing, quantity, accessibility, and trailer load rules. |
| DYN | `checkSites` | Dynamic customer tank inventory feasibility. |
| DRI | `checkResources` / driver subchecks | Driver rest, time-window, and max-driving constraints. |
| TL | `checkResources` / trailer subchecks | Trailer overlap and driver/trailer compatibility. |
| QS | `checkServiceQuality` | Call-in order satisfaction and VMI safety-level service quality. |
| COST | `checkCosts` | Consistency of computed costs and delivered quantities. |

## Layover Rules

| Code | Rule | Practical interpretation |
| --- | --- | --- |
| LAY02 | A shift with a layover must include at least one layover customer. | If a route has a layover but serves no customer marked `LayoverCustomer=1`, it is invalid. |
| LAY03 | A shift may contain at most one layover. | Long route edits must not force multiple layovers in one shift. |

## Shift and Operation Rules

| Code | Rule | Practical interpretation |
| --- | --- | --- |
| SHI02 | Each operation arrival must be no earlier than previous departure plus travel time plus any layover duration. | Arrival times may include waiting, but cannot beat travel time. |
| SHI03 | Loading/delivery operations take the site setup time. | Departure is derived as `arrival + setupTime`; route edits must leave enough time before the next arrival. |
| SHI04 | Customer service interval `[arrival, departure]` must fit in one customer opening window. | Customer delivery windows constrain both arrival and setup completion. |
| SHI05 | The assigned trailer must be allowed at each visited source/customer. | Site accessibility is trailer-specific. |
| SHI06 | Trailer quantity must stay in `[0, trailer capacity]` after each operation. | Positive customer quantities unload the trailer; negative source quantities load it. |
| SHI07 | A trailer starts each shift with the same quantity it ended its previous shift with. | Trailer load is stateful across shifts. |
| SHI11 | Source quantities must be negative and customer quantities must be positive. | Loading at a source is represented as negative quantity. |
| SHI16 | VMI customer delivery quantity must be between `MinOperationQuantity` and `Capacity`. | This does not apply to call-in customers in the checker. |

## Dynamic Site Rules

| Code | Rule | Practical interpretation |
| --- | --- | --- |
| DYN01 | Customer tank inventory must remain within `[0, Capacity]`. | Deliveries plus initial inventory minus forecast cannot underflow or overflow physical capacity. |

## Driver Rules

| Code | Rule | Practical interpretation |
| --- | --- | --- |
| DRI01 | Consecutive shifts for the same driver must be separated by `minInterSHIFTDURATION`. | Driver reuse needs rest time between shifts. |
| DRI03 | Driving time between layovers must not exceed `maxDrivingDuration`. | Waiting/service time does not reset driving; layovers do. |
| DRI08 | Full shift interval `[start, end]` must fit inside one driver availability window. | A route can be locally feasible but invalid for the assigned driver schedule. |

## Trailer Rules

| Code | Rule | Practical interpretation |
| --- | --- | --- |
| TL01 | Shifts using the same trailer cannot overlap. | Trailer reuse is sequential. |
| TL03 | The assigned trailer must be in the driver's allowed trailer list. | Driver/trailer assignment is compatibility constrained. |

## Service Quality Rules

| Code | Rule | Practical interpretation |
| --- | --- | --- |
| QS01 | Call-in orders ending before the planning horizon must be satisfied. | Deliveries within an order window must meet the order quantity/flexibility logic. |
| QS02 | VMI customer tank level must stay above `SafetyLevel` at every timestep. | This is the runout/autonomy requirement. |
| QS03 | Every call-in customer operation must fall within one of that customer's order windows. | No unsolicited deliveries to call-in customers. |

## Cost Rules

| Code | Rule | Practical interpretation |
| --- | --- | --- |
| COST | Distance, time, layover, total shift cost, and total quantity must match checker recomputation. | Compact submitted XMLs omit these fields; the checker derives them internally. |

## Important Modeling Notes

- Point `0` is the base.
- Sources are points `1..len(sources)`.
- Customers are points `1 + len(sources)..len(sources) + len(customers)`.
- Submitted solution operations omit the final return-to-base operation; the checker derives it.
- Submitted operations also omit departures, layovers, trailer quantities, and costs; the checker derives these.
- Time values are in minutes. Forecast timestep length is `unit` minutes, usually 60.
- Final validation should always be done with the official checker.
