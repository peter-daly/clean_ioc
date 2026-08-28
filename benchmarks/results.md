# Benchbro Results

- schema_version: `2`
- run_id: `d65f42de34044467951c87b13803506d`
- started_at: `2026-08-28T17:24:56.966264+00:00`
- finished_at: `2026-08-28T17:25:22.849570+00:00`
- python_version: `3.14.4`
- platform: `macOS-15.7.9-arm64-arm-64bit-Mach-O`

| case | benchmark | metric_type | parameters | mean_s | median_s | ci95 | cv_pct | p95_s | ops_per_sec | peak_alloc_bytes | net_alloc_bytes | status |
| --- | --- | --- | --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |
| container-operations | direct-python-construction | time |  | 5.70008e-07 | 5.67463e-07 | 5.65046e-07–5.74971e-07 | 1.088 | 5.80302e-07 | 1.75436e+06 | - | - | stable |
| container-operations | resolve-pre-built-instance | time |  | 9.34088e-06 | 9.14788e-06 | 9.06265e-06–9.61912e-06 | 4.55918 | 1.01343e-05 | 107056 | - | - | noisy |
| container-operations | resolve-cached-singleton | time |  | 9.06776e-06 | 8.96518e-06 | 8.87521e-06–9.2603e-06 | 2.65368 | 9.48005e-06 | 110281 | - | - | noisy |
| container-operations | resolve-transient | time |  | 1.33972e-05 | 1.31484e-05 | 1.30024e-05–1.37921e-05 | 5.20892 | 1.45598e-05 | 74642.4 | - | - | noisy |
| container-operations | resolve-five-node-graph | time |  | 4.44728e-05 | 4.41945e-05 | 4.36302e-05–4.53155e-05 | 2.36793 | 4.62336e-05 | 22485.6 | - | - | stable |
| container-operations | explain-five-node-graph | time |  | 3.38046e-05 | 3.35908e-05 | 3.32141e-05–3.4395e-05 | 2.18281 | 3.50416e-05 | 29581.8 | - | - | noisy |
