# M06 implementation verification handoff

Status: Round-1 review repair verified; coordinator repair checkpoint and same-reviewer recheck pending.
Implementation agent: `/root/m06_implementation`, `gpt-6-astra`, high reasoning.
Baseline: accepted M05 `d62c87e`, accepted search checkpoint `8800f1d`, branch `codex/decorator-templates`.
Coordinator owns commits, review, milestone status and execution log. This agent made no commits.

## Delivered behavior and interfaces

- `_BuilderBase._compilation_snapshot(build_args)` now supplies the same original layered blueprint and typed
  `_CompilationInputs` to root/scope build, public component preview and internal source-expansion inspection.
  Scope previews include parent layers, inherited boundaries with offsets, merged build arguments, singleton and
  preconfiguration anchors, owner tokens and inherited explanations. Preview still bypasses final validation rules.
  Generated candidates are retained separately from original templates and are re-created for each compiled overlay;
  ordinary runtime scopes reuse the plan and invoke no template callbacks.
- Public patch/remove semantics continue to shadow inherited root policies by ID. Patches preserve ID/order and now
  replace an existing local shadow in place, matching ordinary decorator patches. Tombstones suppress the policy in
  all descendant overlays; independent policies and immutable ancestor plans remain intact. Changing `for_each`,
  `source_filter`, or the factory works through public APIs. Private boundary template IDs remain inaccessible to root
  and overlay edits.
- Generated/ordinary sorting retains position, layer and reverse declaration ordinal. For ordinal collisions caused
  by inherited patches, shared per-layer insertion rank precedes reverse source ordinal, keeping each template's
  source layers together without kind precedence. `_Layer.decorator_declaration_ids` retains one immutable sequence
  across ordinary decorators and templates; registrations and first inherited patches append, in-place repatches
  retain their slot, and removals remove their ID. Alias normalization preserves this sequence. Activation runs
  inside-out, so the later inserted tied declaration is outermost. Unique-ordinal sorting is unchanged. Stored IDs
  and ordinals remain unchanged; no UUID-based ordering is introduced.
- Boundary metadata preparation and expanded-visibility recheck now receive the same parent compiler inputs. An actual
  failing probe demonstrated a false `template-visibility-cycle`: a newly installed template decorated a parent-owned
  singleton in the temporary metadata compiler, while runtime compilation correctly retained its old pipeline.
  Propagating anchors fixes Use.root, Expose and aliased Use selection. Metadata cloning restores the original source
  service/name/tags before applying the current public alias; otherwise an anchor first published through an alias
  failed an original-name Expose filter. Parent activation steps and dependency selections are unchanged.
- Existing visibility and registration selection rules remain intact. Shared group identity grants no access; source
  aliases select the original ID, multiple aliases deduplicate by ID, private/ineligible exact dependencies fail with
  no fallback, and named target overrides receive only their explicit memberships. No source-shadowing policy added.

## Evidence

Changed production file: `clean_ioc/container.py`. New `tests/test_decorator_template_composition.py`: **43 cases**.
Coverage includes group/DerivedServices inherited new sources and targets; nested overlays; public preview parity and
no validation finalization; plain scopes without callback replay; named membership overrides; independent family edits,
removal inheritance, source-key replacement and retained original/generated identities; mixed ordinary/template ordinal
collisions and repeated patches; generic source metadata; private source/target negatives and inaccessible policy IDs;
legal Expose/Use and aliases; false boundary feedback on anchored objects; failed build diagnostic retries and repair.

Ownership tests activate parent singleton wrappers both before and first from a child, prove exact source/resource
identity despite overlay replacements and new policies, compare graph cache/cleanup owners and retaining components,
and assert finalizer events occur at the correct parent or overlay boundary. A second test activates an overlay-owned
singleton with two generated resource wrappers from nested compiled/plain scopes: nested closure releases neither;
overlay closure releases both overlay wrappers and its source; parent closure releases the remaining wrapper/source.

Actual final checks, repository Python 3.14.4:

```
.venv/bin/python -m pytest tests/test_decorator_template_composition.py tests/test_decorator_template_compilation.py tests/test_decorator_template_expansion.py tests/test_decorator_template_feasibility.py tests/test_service_targets.py tests/test_service_groups.py tests/test_boundaries.py tests/test_resource_ownership.py tests/test_compiler_tooling.py tests/test_closed_generic_constructors.py tests/test_registration_patterns.py tests/test_container.py tests/test_bundles.py tests/test_type_aliases.py tests/test_type_alias_lookup_paths.py tests/test_complex_dependencies.py -q --disable-warnings --maxfail=3
```

**589 passed in 4.99s.** New composition file alone: **43 passed in 0.86s**.

Isolated Python 3.11, no project environment modifications:

```
uv run --no-project --isolated --python 3.11 --with pytest==9.1.1 --with pytest-asyncio==1.4.0 --with funcie==0.2.0 --with typetoolbox==0.4.0 --with typing_extensions==4.16.0 python -m pytest tests/test_decorator_template_composition.py tests/test_decorator_template_compilation.py tests/test_decorator_template_expansion.py tests/test_decorator_template_feasibility.py tests/test_service_targets.py tests/test_service_groups.py tests/test_boundaries.py tests/test_resource_ownership.py tests/test_compiler_tooling.py -q --disable-warnings --maxfail=3
```

**366 passed, 4 skipped in 2.72s.** All 43 new cases pass; skips are the four previously documented Python-version cases
(PEP695 and stdlib TypeVar defaults), passing on 3.14. Ruff check and ty check pass for both Python files; Ruff format
check reports **2 files already formatted**. `git diff --check` passes. Initial ownership fixture assumptions about
redacted owner tokens/self-owner links were corrected to the actual public ownership report, not production changes.

## Limits / next gate

Independent Astra High `/root/m06_review` requested one P2 ordering correction at verification checkpoint `c8998b9`.
The repair is implemented and verified but acceptance is not claimed; coordinator must checkpoint it and obtain the
same reviewer's independent recheck. Detailed diagnostics/inspection remain M07; bark-core integration M08; public
explanatory documentation M09; full CI/matrix M10. No public docs/examples, bark-core files/environment, unrelated work
items, or commit history were changed. No documentation comprehension gate applies to this implementation-only change.


## Independent-review repair

Round 1 found that the initial tie rank encoded ordinary-first compiler assembly rather than shared layer insertion.
With parent ordinary P(order0), then local L(order0) and patch P, ordinary L produced P->L outside-in while equivalent
one-source template L produced L->P. The shared sequence above repairs that inconsistency and supersedes the initial
handoff's kind-precedence statement. Added **16 runtime matrix cases**: both kinds on each side, patch before/after the
local declaration, one/two sources, repatching both IDs, and nested overlay retention. They preserve the ordinary-only
reference behavior and prove each template's source layers remain adjacent. The exact regression/3.11 commands above
were rerun after repair with the updated results shown. Ruff, ty, format and diff checks pass. Only `container.py`,
`test_decorator_template_composition.py` and this handoff were edited during repair; no commits or public/bark edits.

## Final gate record

Accepted after independent review round 2. Search `8800f1d`; implementation `c8998b9`; repair `caa2dd3`; review evidence `a23a5ac` (preceded by log-only checkpoint `98666ca`). All checkpoint hooks passed. Reviewer independently passed 589 focused tests and the original ordering reproduction. No unresolved M06 findings. No public documentation changes, so reader gate does not apply. Bark-core remains untouched. M07 should capture diagnostics and immutable inspection facts while preserving the accepted runtime and ownership behavior.

## Verified checkpoint index

Coordinator completion audit; gate hashes resolve to local commit objects. The final M10 hash is filled after its commit.

| Gate | Outcome | Local commit |
| --- | --- | --- |
| Search | Passed | `8800f1d` |
| Implementation verification | Passed | `c8998b9` |
| Implementation verification, repair | Passed | `caa2dd3` |
| Independent technical review | Passed round 2 | `a23a5ac` |
| Final handoff | Passed | `34f19e6` |
