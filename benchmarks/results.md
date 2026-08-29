# Benchbro Results

- schema_version: `2`
- run_id: `2b3418a47e1343f1b09d32472d0a95e9`
- started_at: `2026-08-29T11:48:08.675535+00:00`
- finished_at: `2026-08-29T11:48:24.864867+00:00`
- python_version: `3.14.4`
- platform: `macOS-15.7.9-arm64-arm-64bit-Mach-O`

| case | benchmark | metric_type | parameters | mean_s | median_s | ci95 | cv_pct | p95_s | ops_per_sec | peak_alloc_bytes | net_alloc_bytes | status |
| --- | --- | --- | --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |
| compiled-runtime | direct-python-construction | time |  | 5.65368e-07 | 5.65544e-07 | 5.62396e-07–5.68341e-07 | 1.00372 | 5.73143e-07 | 1.76876e+06 | - | - | noisy |
| compiled-runtime | resolve-pre-built-instance | time |  | 2.51441e-06 | 2.40102e-06 | 2.35661e-06–2.67221e-06 | 11.9807 | 2.90967e-06 | 397708 | - | - | noisy |
| compiled-runtime | resolve-cached-singleton | time |  | 2.51604e-06 | 2.48459e-06 | 2.46565e-06–2.56643e-06 | 3.82311 | 2.68174e-06 | 397450 | - | - | noisy |
| compiled-runtime | resolve-transient | time |  | 5.00057e-06 | 4.9358e-06 | 4.92964e-06–5.07149e-06 | 2.70756 | 5.29841e-06 | 199977 | - | - | noisy |
| compiled-runtime | resolve-five-component-plan | time |  | 2.01434e-05 | 1.98521e-05 | 1.97357e-05–2.05511e-05 | 3.86419 | 2.12582e-05 | 49644.1 | - | - | noisy |
| compiled-runtime | create-scope | time |  | 3.91388e-06 | 3.86718e-06 | 3.8584e-06–3.96935e-06 | 2.70597 | 4.12461e-06 | 255501 | - | - | noisy |
| compiled-runtime | resolve-request-slot-plan | time |  | 2.42604e-05 | 2.41058e-05 | 2.3873e-05–2.46478e-05 | 3.04845 | 2.52532e-05 | 41219.5 | - | - | noisy |
