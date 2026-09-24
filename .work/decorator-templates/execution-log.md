# Sequential execution log

Started: 2026-09-23. Branch: `codex/decorator-templates`.
Initial clean-ioc HEAD: `520161b41bc35967a77b4bea0334e6fba9d62349`.
Initial bark-core HEAD: `b0cd55693889785a14be128d1f78f815f2a6e5fe` (clean, no task commits).

Only the coordinator updates this log. The current gate's SHA is added after its commit, and is included in the next
checkpoint; commits are not amended to include their own hashes. Commit messages also identify the milestone/gate.

| Milestone | Gate | Status | Local clean-ioc commit | Evidence |
| --- | --- | --- | --- | --- |
| 01 | Search | Passed | `da20679d89cf0779c8c30365196375901f62e8b5` | [Search evidence](01-search.md); 76 focused baseline tests; lint/type/full-unit-test commit hooks passed |
| 01 | Implementation verification | Passed | `ae33390c8e255a2a0c386cfc36bae42e2de0af6c` | Astra High `/root/m01_implementation`; [handoff](01-handoff.md); 13 probes, 277 focused regressions, 98 final container/probe tests, Ruff/ty passed; coordinator repeated 13 probes; full-unit/lint/type commit hooks passed |
| 01 | Independent technical review | Passed round 2 | `0815f6d9afec9dd25d1606b72218d36e9122a63d` | Astra High `/root/m01_review`; [review](01-review.md); both findings resolved; independent 14 probes passed |
| 01 | Implementation verification, repair | Passed | `2179fa6fc5660cd4f960a7fc89258bde3de9136a` | Both review findings repaired; 14 probes and 277 focused regressions plus Ruff/ty/format passed; coordinator repeated 14 probes; full-unit/lint/type commit hooks passed |
| 01 | Final handoff | Passed | `485e27d` | All prior gates verified; no public docs gate applies; next assignment M02 |

| 02 | Search | Passed | `9cb82d7` | Luna Low `/root/m02_search`; [evidence](02-search.md) |

| 02 | Implementation verification | Passed | `799d528` | Sol High `/root/m02_implementation`; [handoff](02-handoff.md); 319 focused tests, Ruff/ty/diff and full-unit/lint/type commit hooks passed |

| 02 | Implementation verification, repair | Passed | `541f611` | Union equivalence and Callable list constraints repaired; 321 focused tests, Ruff/ty/diff and full-unit/lint/type commit hooks passed |

| 02 | Implementation verification, repair 2 | Passed | `156abd5` | Open-union constraints repaired; 322 focused tests, Ruff/ty/diff and full-unit/lint/type commit hooks passed |

| 02 | Independent technical review | Passed round 3 | `64958b4` | Astra High `/root/m02_review`; [review](02-review.md); 322 tests plus nine union probes; all findings resolved |

| 02 | Final handoff | Passed | `fa33b7f` | All previous gates verified; no public docs gate; M03 next |

| 03 | Search | Passed | `37a22f2` | Luna Low `/root/m03_search`; [evidence](03-search.md) |

| 03 | Implementation verification | Passed | `60cf3a2` | Astra High `/root/m03_implementation`; [handoff](03-handoff.md); 352 focused tests; Python3.11 57 passed/1 expected skip; Ruff/ty/format/diff and full-unit/lint/type commit hooks passed |

| 03 | Implementation verification, repair | Passed | `daa8871` | Three P2s repaired; 356 focused tests; Python3.11 61 passed/1 expected skip; Ruff/ty/format/diff and full-unit/lint/type commit hooks passed |

| 03 | Independent technical review | Passed round 2 | `c652a5f` | Astra High `/root/m03_review`; [review](03-review.md); 356 independent tests and targeted probes; all findings resolved |

| 03 | Final handoff | Passed | `530a725` | All prior gates verified; no public docs gate; M04 next |

| 04 | Search | Passed | `f831e3a` | Luna Low `/root/m04_search`; [evidence](04-search.md); internal expansion/recheck seam identified |

| 04 | Implementation verification | Passed | `3e7e3dc` | Astra High `/root/m04_implementation`; [handoff](04-handoff.md); 481 focused tests; Python3.11 95 passed/1 expected skip; Ruff/ty/format/diff and full-unit/lint/type commit hooks passed |

| 04 | Implementation verification, repair | Passed | `65792c2` | Safe instance capture and typed-factory source metadata repaired; 483 focused tests; Python3.11 97 passed/1 expected skip; Ruff/ty/format/diff and full-unit/lint/type commit hooks passed |

| 04 | Independent technical review | Passed round 2 | `b6b7c41` | Astra High `/root/m04_review`; [review](04-review.md); 147 independent tests and targeted probes; all findings resolved |

| 04 | Final handoff | Passed | `596e12a` | All prior gates verified; actual generated activation/recheck handed to M05 |

| 05 | Search | Passed | `e6bd146` | Luna Low `/root/m05_search`; [evidence](05-search.md); activation/lifecycle/boundary and snapshot scale seams mapped |

| 05 | Implementation verification | Passed | `1c508ea` | Astra High `/root/m05_implementation`; [handoff](05-handoff.md); 537 focused tests; Python3.11 139 passed/1 expected skip; Ruff/ty/format/diff and full-unit/lint/type commit hooks passed |

| 05 | Implementation verification, repair | Passed | `f9cbaee` | Three P2s repaired; 546 focused tests; Python3.11 145 passed/4 expected skips; Ruff/ty/format/diff and full-unit/lint/type commit hooks passed |

| 05 | Independent technical review | Passed round 2 | `636205b` | Astra High `/root/m05_review`; [review](05-review.md); 546 independent tests/probes and Ruff/ty; all findings resolved |

| 05 | Final handoff | Passed | `d62c87e` | All prior gates verified; full scope/boundary/edit acceptance handed to M06 |

| 06 | Search | Passed | `8800f1d` | Luna Low `/root/m06_search`; [evidence](06-search.md); preview gap and runtime ownership/visibility cases mapped |

| 06 | Implementation verification | Passed | `c8998b9` | Astra High `/root/m06_implementation`; [handoff](06-handoff.md); 573 focused tests; Python3.11 350 passed/4 expected skips; Ruff/ty/format/diff and full-unit/lint/type commit hooks passed |

| 06 | Implementation verification, repair | Passed | `caa2dd3` | Shared layer traversal order repaired; 589 focused tests; Python3.11 366 passed/4 expected skips; Ruff/ty/format/diff and full-unit/lint/type commit hooks passed |

| 06 | Independent technical review | Passed round 2 | `a23a5ac` | Astra High `/root/m06_review`; [review](06-review.md); 589 independent tests and original reproduction; all findings resolved |

Checkpoint `98666ca` recorded the repair SHA only because the evidence-writing command could not find Python; this subsequent checkpoint records the review evidence. All hooks passed.

Implementation/review/documentation gates not listed here have not passed. M06 final handoff passed; M07 accepted; final handoff passed; M08–M10 have not started.

| 06 | Final handoff | Passed | `34f19e6` | All prior gates verified; no public documentation changes; diagnostics handed to M07 |

| 07 | Search | Passed | `4e9174a` | Luna Low `/root/m07_search`; [evidence](07-search.md); frozen facts/reporting gaps mapped |

| 07 | Implementation verification | Passed | `d1d7ff7` | Sol High `/root/m07_implementation`; [handoff](07-handoff.md); 598 focused tests; Python3.11 412 passed/6 expected skips; Ruff/ty/format/diff and full-unit/lint/type commit hooks passed |

M07 review round 1 found three P2s; see [review](07-review.md). Original implementation-agent restoration, fresh Sol High replacement, and reviewer-delegated replacement all failed with the same agent thread limit. No acceptance/checkpoint claimed for this failed gate. M08–M10 remain unstarted.

2026-09-24 continuation: original Sol High `/root/m07_implementation` restored successfully; capacity blocker cleared. Three review findings assigned for repair and subsequent independent recheck.

| 07 | Implementation verification, repair | Passed | `71183b8` | Original Sol High agent restored; all three P2s repaired; 458 relevant tests; Python3.11 364 passed/4 expected skips; Ruff/ty/format/diff passed; [handoff](07-handoff.md) |

| 07 | Implementation verification, repair 2 | Passed | `6f454aa` | Ancestor graph-keyed frozen sidecars; nested regression; 458 affected tests; Python3.11 364 passed/4 expected skips; Ruff/ty/format/diff passed |

| 07 | Independent technical review | Passed round 3 | `906452e` | Astra High `/root/m07_review`; 601 independent tests plus five-generation probe; [review](07-review.md); no remaining findings |

| 07 | Final handoff | Passed | `2780e0e` | All prior gates verified; no public docs gate applies; M08 integration next |

| 08 | Search | Passed | `1818392` | Luna Low `/root/m08_search`; [evidence](08-search.md); bark clean baseline110 passed; verified checkout import |

| 08 | Implementation verification | Passed | `0f63ace` | Astra High `/root/m08_implementation`; [handoff](08-handoff.md); bark409 passed incl14 new cases and changed-file static checks; clean make ci735 tests/precommit passed; bark ledger12 files, no commits/env changes |

| 08 | Independent technical review | Passed | `827964d` | Astra High `/root/m08_review`; [review](08-review.md);409 independent tests plus closed-generic source probe; ledger/no-commit verified |

| 08 | Final handoff | Passed | `2ba08f2` | Prior gates verified;12-file uncommitted bark ledger retained; no public docs reader gate; M09 docs next |

| 09 | Search | Passed | `487b304` | Luna Low `/root/m09_search`; [evidence](09-search.md); public docs/API/validator gaps mapped; no integration material used |

| 09 | Implementation verification | Passed | `1507ef2` | Sol High `/root/m09_implementation`; [handoff](09-handoff.md); exact Markdown examples, strict MkDocs build, Ruff/ty/format/diff passed; independent examples, no integration references |

| 09 | Independent technical review | Passed | `f56369a` | Astra High `/root/m09_review`; [review](09-review.md); validator/strictdocs/190tests/static pass; reader gate pending |

| 09 | Implementation verification, documentation repair | Passed | `0457789` | Reader round1 retained as failed (19/20 plus core F1); explicit overlay order/example repaired; exactdocs/strictdocs/2nested tests/static pass |

| 09 | Independent technical review, repair | Passed | `87529ef` | Astra High F1 repair accepted; exactdocs/strictdocs/2nestedtests/diff pass; fresh round2 required |

| 09 | Documentation comprehension | Passed round2 20/20 | `5b64ccd` | Fresh Luna Low `/root/m09_reader_r2`, Astra High examiner; [grade](09-reader-round2-grade.md); Q1–7full/nozero; both transfer programs pass; no core gaps |

| 09 | Final handoff | Passed | `9734712` | All technical/docs gates committed; round2 20/20; public revision0457789 frozen; M10 final checks next |

Historical capacity pause after M09: M01–M09 accepted and all applicable gates committed. M10 search could not start: two fresh Luna Low spawn attempts from coordinator and one from independent reviewer all returned `agent thread limit reached`. No M10 gate is claimed passed. Final acceptance mapping and supported Python matrix remain required. Baseline recheck: Clean task files committed (unrelated .work notes preserved); bark has exactly12 ledger files uncommitted at original b0cd556 HEAD. Actual CI config .github/workflows/ci.yml: requiredPython3.11/3.12/3.13/3.14 onUbuntu, experimental3.15-dev; FastAPI minimum/latest compatibility also defined. Local platform checks must not be called remote CI coverage.

Continuation: fresh `/root/m10_search` Luna Low started successfully after user requested continuation. Coordinator verified unchanged clean task state and exact12-file bark ledger at original HEAD.

| 10 | Search | Passed | `fb041a3` | Fresh Luna Low `/root/m10_search`; [39-row evidence map](10-search.md); actual CI/version/FastAPI requirements and ledgers checked |

| 10 | Implementation verification | Passed | `14a9bfe` | Sol High `/root/m10_implementation`; [handoff](10-handoff.md); makeci Python3.11 727/8skip,3.12 732/3skip,3.13/3.14 735each; FastAPI min/latest14each; precommit/strictdocs pass; no implementation changes |

| 10 | Implementation verification, coverage repair | Passed | Pending checkpoint | Row7 retained4variant regression distinctclasses/positions/filters/exactIDs; compilation file3.11/3.12 52passed3skip,3.13/3.14 55passed; static/diff pass; no production/docs/bark changes |
