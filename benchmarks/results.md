# Benchbro Results

- schema_version: `2`
- run_id: `c9712083cf124d47aac71398131bc79a`
- started_at: `2026-08-28T20:39:46.871158+00:00`
- finished_at: `2026-08-28T20:43:10.733611+00:00`
- python_version: `3.14.4`
- platform: `macOS-15.7.9-arm64-arm-64bit-Mach-O`

| case | benchmark | metric_type | parameters | mean_s | median_s | ci95 | cv_pct | p95_s | ops_per_sec | peak_alloc_bytes | net_alloc_bytes | status |
| --- | --- | --- | --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |
| compiled-runtime | direct-python-construction | time |  | 5.63126e-07 | 5.62077e-07 | 5.54548e-07–5.71705e-07 | 1.90373 | 5.80014e-07 | 1.7758e+06 | - | - | stable |
| compiled-runtime | resolve-pre-built-instance | time |  | 2.48023e-06 | 2.44073e-06 | 2.40997e-06–2.55049e-06 | 4.08789 | 2.64973e-06 | 403188 | - | - | noisy |
| compiled-runtime | resolve-cached-singleton | time |  | 2.58653e-06 | 2.56072e-06 | 2.51256e-06–2.6605e-06 | 5.26087 | 2.77872e-06 | 386619 | - | - | noisy |
| compiled-runtime | resolve-transient | time |  | 4.97349e-06 | 4.97168e-06 | 4.94698e-06–5e-06 | 0.666082 | 5.01356e-06 | 201066 | - | - | stable |
| compiled-runtime | resolve-five-component-plan | time |  | 2.00783e-05 | 1.99878e-05 | 1.97021e-05–2.04545e-05 | 2.34151 | 2.08632e-05 | 49805 | - | - | noisy |
| compiled-runtime | create-scope | time |  | 3.75892e-06 | 3.73905e-06 | 3.70583e-06–3.812e-06 | 1.76491 | 3.87037e-06 | 266034 | - | - | noisy |
| compiled-runtime | resolve-request-slot-plan | time |  | 2.4374e-05 | 2.40541e-05 | 2.36486e-05–2.50994e-05 | 3.71948 | 2.59225e-05 | 41027.3 | - | - | noisy |
| compiled-build | build-five-component-container | time |  | 0.000336079 | 0.000336614 | 0.000334094–0.000338065 | 0.738286 | 0.000339444 | 2975.49 | - | - | stable |
| compiled-build | build-scope-overlay | time |  | 0.000279513 | 0.000278416 | 0.000277532–0.000281494 | 0.88564 | 0.000283562 | 3577.65 | - | - | noisy |
| compiled-allocations | resolve-five-component-plan | memory |  | - | - | - | 28.9836 | - | - | 4048.8 | 760.8 | noisy |
| compiled-allocations | create-scope | memory |  | - | - | - | 0.716961 | - | - | 2635.53 | 348.533 | stable |
