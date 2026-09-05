# Benchbro Results

- schema_version: `2`
- run_id: `69a84da1111048b0991884b9f80c63d7`
- started_at: `2026-09-04T23:09:01.788494+00:00`
- finished_at: `2026-09-04T23:10:58.149787+00:00`
- python_version: `3.14.4`
- platform: `macOS-15.7.9-arm64-arm-64bit-Mach-O`

| case | benchmark | metric_type | parameters | mean_s | median_s | ci95 | cv_pct | p95_s | ops_per_sec | peak_alloc_bytes | net_alloc_bytes | status |
| --- | --- | --- | --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |
| compiled-runtime | direct-python-construction | time |  | 5.76011e-07 | 5.75247e-07 | 5.69783e-07–5.8224e-07 | 1.35133 | 5.85965e-07 | 1.73608e+06 | - | - | stable |
| compiled-runtime | resolve-pre-built-instance | time |  | 9.6289e-07 | 9.6463e-07 | 9.54723e-07–9.71057e-07 | 1.05998 | 9.71327e-07 | 1.03854e+06 | - | - | noisy |
| compiled-runtime | resolve-cached-singleton | time |  | 9.03669e-07 | 9.04211e-07 | 8.96873e-07–9.10465e-07 | 0.939802 | 9.14702e-07 | 1.1066e+06 | - | - | stable |
| compiled-runtime | resolve-transient | time |  | 1.93821e-06 | 1.93803e-06 | 1.92873e-06–1.9477e-06 | 0.611611 | 1.95564e-06 | 515939 | - | - | noisy |
| compiled-runtime | resolve-five-component-plan | time |  | 6.32591e-06 | 6.30874e-06 | 6.29204e-06–6.35979e-06 | 0.669249 | 6.39627e-06 | 158080 | - | - | noisy |
| compiled-runtime | create-scope | time |  | 1.68291e-06 | 1.68204e-06 | 1.66915e-06–1.69666e-06 | 1.02127 | 1.70929e-06 | 594210 | - | - | noisy |
| compiled-runtime | resolve-request-slot-plan | time |  | 7.74435e-06 | 7.74881e-06 | 7.71489e-06–7.77382e-06 | 0.475452 | 7.79408e-06 | 129126 | - | - | noisy |
| compiled-runtime-scaling | resolve-transient-chain[depth-1] | time | depth=1 | 1.95894e-06 | 1.94984e-06 | 1.92387e-06–1.994e-06 | 2.23701 | 2.02512e-06 | 510481 | - | - | stable |
| compiled-runtime-scaling | resolve-transient-chain[depth-5] | time | depth=5 | 5.92999e-06 | 5.912e-06 | 5.86587e-06–5.99412e-06 | 1.35136 | 6.06201e-06 | 168634 | - | - | noisy |
| compiled-runtime-scaling | resolve-transient-chain[depth-20] | time | depth=20 | 2.34594e-05 | 2.33587e-05 | 2.32132e-05–2.37055e-05 | 1.31154 | 2.39246e-05 | 42626.9 | - | - | stable |
| compiled-runtime-scaling | resolve-transient-chain[depth-50] | time | depth=50 | 6.94948e-05 | 6.94124e-05 | 6.89308e-05–7.00588e-05 | 1.01432 | 7.047e-05 | 14389.6 | - | - | stable |
| compiled-build | build-five-component-container | time |  | 0.00421524 | 0.0042091 | 0.00419065–0.00423983 | 0.729129 | 0.00425067 | 237.234 | - | - | stable |
| compiled-build | build-five-component-container-with-entrypoint-diagnostics | time |  | 0.00425843 | 0.00426558 | 0.00418583–0.00433104 | 2.13074 | 0.00437459 | 234.828 | - | - | noisy |
| compiled-build | build-scope-overlay | time |  | 0.00452073 | 0.00451781 | 0.00450081–0.00454065 | 0.550622 | 0.00455702 | 221.203 | - | - | noisy |
| compiled-build | build-open-generic-factory-container | time |  | 0.00227194 | 0.00226134 | 0.00225162–0.00229225 | 1.1176 | 0.00230675 | 440.153 | - | - | stable |
| compiled-build-features | build-five-component-graph[core] | time | scenario='core' | 0.00425171 | 0.0042327 | 0.00420589–0.00429752 | 1.34665 | 0.00434689 | 235.2 | - | - | noisy |
| compiled-build-features | build-five-component-graph[ordinary-validation] | time | scenario='ordinary-validation' | 0.00428832 | 0.00427822 | 0.00425427–0.00432237 | 0.992366 | 0.00435741 | 233.191 | - | - | noisy |
| compiled-build-features | build-five-component-graph[deferred-strict-validation] | time | scenario='deferred-strict-validation' | 0.0042966 | 0.00429156 | 0.00426104–0.00433215 | 1.03415 | 0.00434681 | 232.742 | - | - | stable |
| compiled-build-features | build-five-component-graph[resource-ownership] | time | scenario='resource-ownership' | 0.00442897 | 0.00442438 | 0.0043951–0.00446284 | 0.955784 | 0.00449318 | 225.786 | - | - | noisy |
| compiled-build-features | build-five-component-graph[typed-provider] | time | scenario='typed-provider' | 0.00425323 | 0.00426728 | 0.00421945–0.00428702 | 0.992735 | 0.00430512 | 235.115 | - | - | stable |
| compiled-build-features | build-five-component-graph[assembly-boundaries] | time | scenario='assembly-boundaries' | 0.00425776 | 0.00426312 | 0.00421871–0.0042968 | 1.14605 | 0.00431901 | 234.865 | - | - | stable |
| compiler-validation | run-deferred-graph-walk | time |  | 2.80787e-05 | 2.78554e-05 | 2.7778e-05–2.83793e-05 | 1.9699 | 2.9097e-05 | 35614.2 | - | - | noisy |
| compiler-validation | run-deferred-type-ast-inspection | time |  | 0.000262604 | 0.000260409 | 0.000259065–0.000266143 | 1.68404 | 0.000270198 | 3808.01 | - | - | noisy |
| compiler-tooling | create-semantic-manifest | time |  | 0.000107202 | 0.000106637 | 0.000106206–0.000108199 | 1.16179 | 0.000109334 | 9328.16 | - | - | noisy |
| compiler-tooling | diff-identical-manifest | time |  | 7.72201e-05 | 7.66869e-05 | 7.60882e-05–7.8352e-05 | 1.83185 | 7.95898e-05 | 12950 | - | - | noisy |
| compiler-tooling | diff-single-edge-change | time |  | 8.62574e-05 | 8.57281e-05 | 8.50778e-05–8.7437e-05 | 1.70906 | 8.83028e-05 | 11593.2 | - | - | stable |
| compiler-tooling | create-resource-ownership-report | time |  | 0.000111234 | 0.000111192 | 0.000110182–0.000112285 | 1.18144 | 0.000113297 | 8990.08 | - | - | stable |
| compiled-allocations | resolve-five-component-plan | memory |  | - | - | - | 0.8843 | - | - | 2468.53 | 524.533 | stable |
| compiled-allocations | create-scope | memory |  | - | - | - | 0.800256 | - | - | 2633.33 | 601.333 | stable |
| fastapi-five-layer-request | native-depends | time |  | 0.000264669 | 0.000261417 | 0.000260377–0.00026896 | 2.02623 | 0.000273823 | 3778.31 | - | - | noisy |
| fastapi-five-layer-request | clean-ioc | time |  | 0.00028064 | 0.000275299 | 0.000272437–0.000288843 | 4.94634 | 0.000306555 | 3563.28 | - | - | noisy |
