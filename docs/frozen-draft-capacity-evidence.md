# Frozen draft-table capacity evidence

Step 9 releases a proven-dead hash table after graph freezing. The existing
freezing loop pops every mutable draft as its immutable record is created,
limiting overlap between draft and record allocations. Popping the last entry
leaves a zero-length dictionary whose allocated hash table remains attached to
the runtime graph. `self._drafts.clear()` immediately after that loop releases
this empty storage. No records, occurrence IDs, activation steps, metadata or
validation are removed. There is no new flag, cache, forced collection, or
runtime validation deferral.

## Actual worker retained-heap diagnosis

A separate read-only diagnostic uses the installed frozen Step 7 Clean wheel,
unchanged final Bark wheel and pinned Cop checkout. Tracemalloc begins after
imports, configuration creation and ordinary pre-build collection; a snapshot
and object census follow build and collection while the container remains live.
The census happens after the heap metrics and snapshot, so its own allocations
are excluded. This intrusive diagnostic is attribution evidence, not a paired
RSS performance sample.

| Baseline worker diagnostic | Bytes |
| --- | ---: |
| Process peak RSS after imports/configuration, before build | 172,294,144 |
| Build-only traced retained allocations | 38,482,378 |
| Build-only traced allocation peak | 55,548,685 |
| Frozen occurrence records, shallow storage | 13,267,712 |
| Empty mutable draft dictionary, retained table allocation | 2,621,464 |

There are 51,827 frozen records, each 256 shallow bytes. The empty draft table
accounts for approximately 6.8% of retained traced allocations. The separate
record dictionary and origin dictionary each allocate the same table size, but
hold live records and are not changed. The import/configuration process peak is
approximately 164.3 MiB, so graph savings do not imply removal of that baseline.

`benchmarks/frozen_draft_capacity_diagnostic.json` preserves the field-identity
census, shallow Clean object bytes and traced source attribution, with absolute
paths and private configuration omitted. Immutable metadata sharing may offer
additional savings; it is a separate possible change and is not part of Step 9.

## Focused semantic regressions

`tests/test_frozen_draft_capacity.py` covers 0, 1, 1,024 and 8,192 occurrences.
It retains all pre-freeze `Component` handles and snapshots every draft field.
After freezing, every immutable record field matches, held components still
address the same occurrence records, and parent/dependency links are preserved.
The empty draft dictionary occupies the same shallow storage as a newly created
empty dictionary, independently of the previous number of occurrences.

## Installed-wheel measurements and full validation

Full `make ci` passes **2,033 tests**, Ruff lint/format, typing, documentation
examples and benchmark discovery. The existing warning is unchanged.

Two isolated environments install the identical frozen support requirements and
final Step 8 Bark wheel, paired with the Step 7/Step 9 Clean wheels. The probe
uses 64 routes in each of five Bark route families, two sagas per route, and
both diagnostic modes. It traces composition/compilation after warm imports,
releases the builder, then samples retained allocations after collection with
the container live. Storage/heap/RSS metrics precede manifest and validation
serialization. Each stage/mode has three fresh untraced RSS samples and one
separate fresh traced sample; stage order alternates for untraced samples.
No source overrides or editable installs are used.

| Diagnostics | Metric | Step 7 bytes | Step 9 bytes | Reduction bytes |
| --- | --- | ---: | ---: | ---: |
| Off | Empty draft dictionary shallow storage | 1,310,800 | 64 | 1,310,736 |
| Off | Traced retained | 30,140,001 | 28,831,270 | 1,308,731 |
| Off | Traced peak | 55,535,398 | 54,226,626 | 1,308,772 |
| On | Empty draft dictionary shallow storage | 1,310,800 | 64 | 1,310,736 |
| On | Traced retained | 54,915,576 | 53,609,478 | 1,306,098 |
| On | Traced peak | 77,256,261 | 75,950,373 | 1,305,888 |

Both modes retain exactly 23,255 physical records and 5,953,280 shallow bytes
of immutable records before and after. All 16 completed 64-route samples match
manifest and validation fingerprints, 1,036 public roots, 2,060 selected
catalogue entries, zero provider view contexts and 64 command/reply consumers.
Constructors/handlers remain dormant during build and discovery. Traced
retention falls approximately 1.25 MiB in both modes, closely matching released
draft-table storage. These are synthetic measurements, not inferred Cop savings.

| Diagnostics | Stage | Normal process peak RSS range MiB, three samples |
| --- | --- | ---: |
| Off | Step 7 | 179.44–180.77 |
| Off | Step 9 | 179.34–225.83 |
| On | Step 7 | 204.02–206.80 |
| On | Step 9 | 204.00–204.80 |

The Step 9 diagnostics-off RSS range includes one high sample. All raw values
are retained; these ranges do not establish a reliable RSS reduction. RSS
includes imports, and single traced peaks do not establish a distribution.

Four completed 256-route normal samples are also preserved as partial
observations. Remaining larger-route repetitions were explicitly stopped; no
complete larger-route heap/RSS conclusion is claimed. The completed samples
have zero stderr output. `benchmarks/frozen_draft_capacity_results.json` keeps
all 20 raw rows, complete-scenario summaries, parity fingerprints and
wheel/script/support-requirement hashes, with absolute environment paths omitted.

Actual Cop installed-wheel pairs and downstream checks are measured separately.

## Actual Cop host comparison

The parent measured the actual API and worker host modules with the frozen
Step 8 and Step 9 wheels, unchanged Bark wheel and identical frozen Cop sources.
There are three alternating normal fresh-process samples per app and stage,
plus one separately traced worker sample per stage. This is the same host
measurement boundary as Step 8: imports of config/container and bootstrapping
modules precede the timer; app-module configuration, composition and host
installation are included. Tracing starts after imports and a collection.

| Worker host allocation | Before bytes | After bytes |
| --- | ---: | ---: |
| Retained after collection | 38,559,818 | 35,932,944 |
| Traced allocation peak | 55,639,141 | 53,012,388 |
| Physical graph records | 51,834 | 51,834 |

Retained traced allocations fall by 2,626,874 bytes (6.8%); peak traced
allocations fall by 2,626,753 bytes (4.7%). The small difference from the exact
empty-table storage is normal measurement variation. Worker RSS ranges overlap:
216.77–220.55 MiB before and 217.55–220.80 MiB after. API RSS ranges also overlap:
211.27–213.70 MiB before and 212.08–215.34 MiB after. These measurements prove a
compiler allocation reduction, not a repeatable whole-process RSS reduction.
Graph records, provider views, selected catalogue and public root counts match.

All fourteen sanitized samples and frozen source/wheel identities are in
[`frozen_draft_capacity_application_results.json`](https://github.com/peter-daly/clean_ioc/blob/version2/benchmarks/frozen_draft_capacity_application_results.json).
Full Linux memory observations and downstream checks belong to the parent
[combined evidence](runtime-build-series-evidence.md).

No release, commit, push, version/pin change, resource-limit change or timeout
change is part of this step.

## Frozen candidate identity

Clean IoC remains version `2.0.0rc2` at repository HEAD
`3d576f10427d506b414889af21ad95291c39cccf`, with prior local work preserved.
Frozen Step 9 wheel SHA-256:
`c72e04bd8dc929b2e3ffe0c5d86dff9deab67f75aef602f4e104f0ad4efcb8b3`.
Compared with frozen Step 7, only `clean_ioc/components.py` and the wheel's
`RECORD` inventory differ. The production source difference is one `clear()`
call and its explanatory comment.
