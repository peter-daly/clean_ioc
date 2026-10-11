# Task 24 consumer correctness evidence

The final checks use the actual local Clean IoC source, with isolated Bark and Cop
source copies. `imports.json` identifies each imported module. All package and
consumer/test Python hashes match before and after the final sweep; the version
label remains 2.0.0rc4 and is not used to identify the implementation.

- Bark: 6,040 unit tests passed, 29 existing skips. Compared with the earlier
  6,055-case run, 15 duplicate host-mode cases are retired because hosts now call
  build only: nine provider-root combinations, three invalid-root combinations,
  two required-daemon combinations, and one warmup combination. Policy assertions
  move to analyse; the actual dispatch, scope, provider and cleanup assertions stay.
- Cop: 504 unit tests and all 64 integration tests passed. Integration test sources
  and capacity assertions remain unchanged. The native integration run uses the
  existing Python 3.14.4 environment, Uvicorn hosts, an owned LocalStack container
  and trusted local TLS proxy. All temporary services are stopped by the harness.
- API/worker catalogues match across fresh build/analyse compositions: 245/332
  entries, including private/deferred handlers and decorators. Provider roots stay
  empty as declared by the consumer. Production builds call no UoW validators;
  analyse calls both real registered rules. Analysis produces warnings, no errors.
- Three real invalid UoW/SQL fixtures still produce their expected analysis errors.
  Build invokes zero validators. Reading/serializing the completed report does not
  repeat validators. `bark-rules.json` and its proof source record these checks.

`*-from-original-checkout.patch` can be reviewed/applied against the original
consumer source identity. `*-from-preserved-consumer.patch` isolates this migration
from the earlier local verification adaptations. Both contain Python changes only;
no environment, TLS files or credentials are included. `patch-manifest.json` names
all changed paths. All four patches pass `git apply --check` against their named
base directories (read-only verification). No original consumer checkout was changed; hashes of 750 Bark
and 150 Cop Python files are checked again after verification.

Full test/service logs remain in the private verification directory. Their hashes
and locations are recorded in `private-log-manifest.json`; this folder includes
only sanitized results, source identities and patches. An earlier passing sweep
was superseded after final analysis-provenance fixes changed the package hashes.
The final stable sweep is the acceptance evidence.

These are correctness checks. Existing bounded-memory assertions are preserved,
but no new memory/startup performance comparison or Docker memory run was made.
Task 25 remains responsible for performance acceptance against preserved baselines.
