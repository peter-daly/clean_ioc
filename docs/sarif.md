# Source-linked CI reporting

`clean-ioc check` can export compiler and policy findings as
[SARIF 2.1.0](https://www.oasis-open.org/standard/sarif-v2-1-0/), the standard JSON format for static-analysis results.
CI services and compatible viewers can link these findings to the relevant composition source.

```bash
clean-ioc check my_app.composition:application_builder --format sarif -o clean-ioc.sarif
```

The target follows the usual [CLI rules](compiler-tooling.md#use-it-from-the-command-line): a builder, built container or
scope, or a zero-argument factory returning one. The check runs build rules and, when building succeeds, validate-only
rules. It never activates components to generate the report.

## Findings and source locations

Each result contains the stable `BuildIssue.code` as its `ruleId`, its error/warning severity, the issue message, and
the semantic component path. Dependency paths appear as SARIF code flows, with registration, decorator, and
pre-configuration locations wherever captured provenance is available.

Use `visit.issue(...)` in custom graph rules to preserve exact occurrence attribution. A manually created `BuildIssue`
with only type names may match several named or contextual registrations; ambiguous source locations are omitted.
Unlocated findings and path steps remain valid SARIF with logical type locations. GitHub requires a usable source
location to show a source annotation, so an unlocated finding remains visible in the file and still affects the check's
exit status.

Source URIs are encoded relative to the current working directory. Run from the repository root when uploading to
GitHub. Paths outside that directory, unavailable sources, and unknown line numbers are omitted. Reports never invent
a location for a missing registration.

The report records the installed Clean IoC version and, when a complete compiled graph exists, its **all-roots graph
fingerprint**. A structural build failure still produces a valid SARIF file, using captured failure evidence; it has
no complete-graph fingerprint. A complete graph rejected by a build-mode policy can retain its fingerprint and exact
registration sources.

Build inputs, configured values, runtime IDs, and callable representations are not added to SARIF. Source metadata and
policy findings do not change graph fingerprints. As with existing reports, custom issue messages must be safe to
publish. SARIF's required `version: "2.1.0"` identifies the external standard; Clean IoC's own JSON formats remain
unversioned during beta.

## Exit status and output files

The check exits `0` when validation passes, `1` for errors or unsuppressed warnings in strict mode, and `2` for invalid
targets, CLI options, or output paths. Strictness does not change the severity written into SARIF. `--no-strict` keeps
warnings informational; `--ignore CODE` suppresses warnings only, including warnings alongside build failures.

Omit `-o` to write SARIF to stdout. `check -o` also supports text and JSON, including failed-build reports. Invalid
targets do not create or replace a findings file. `--triage` supports text and JSON and cannot be combined with SARIF,
which reports individual findings.

## GitHub Actions

After checkout and dependency installation, add these steps to a job with `security-events: write` permission.
The upload step also runs after a failed validation check, provided the report was created:

```yaml
permissions:
  contents: read
  actions: read
  security-events: write

steps:
  # Check out the repository and install the application and Clean IoC first.
  - name: Validate dependency graph
    run: clean-ioc check my_app.composition:application_builder --format sarif -o clean-ioc.sarif
  - name: Upload architecture findings
    if: ${{ !cancelled() && hashFiles('clean-ioc.sarif') != '' }}
    uses: github/codeql-action/upload-sarif@v4
    with:
      sarif_file: clean-ioc.sarif
      category: clean-ioc-architecture
```

The validation step keeps its failing exit status. See GitHub's
[SARIF upload guide](https://docs.github.com/en/code-security/how-tos/find-and-fix-code-vulnerabilities/integrate-with-existing-tools/upload-sarif-file)
for repository eligibility and upload configuration, and its
[SARIF support reference](https://docs.github.com/en/code-security/reference/code-scanning/sarif-files/sarif-support)
for source annotation behaviour.

## Programmatic export

Reports created by a container or scope retain the compiled graph they were validated against. Call
`report.to_sarif()` to include source locations and the complete graph fingerprint automatically. The report retains
static reporting context rather than the runtime container, so it can still be rendered after the container closes.
Failed-build reports also retain their captured source evidence.

This standalone example creates a validate-only policy finding without activating either class:

```python
import json

import clean_ioc.component_filters as cf
from clean_ioc import ContainerBuilder, ContainerBuildError
from clean_ioc.policies import forbid_dependency


class Database:
    pass


class Handler:
    def __init__(self, database: Database):
        raise AssertionError("Exporting SARIF must not activate the handler")


builder = ContainerBuilder()
builder.register(Database)
builder.register(Handler)
builder.add_validation_rule(
    forbid_dependency(cf.service_type_is(Handler), cf.service_type_is(Database)),
    mode="validation",
)
container = builder.build()
report = container.validation_report()
document = json.loads(report.to_sarif())
assert document["runs"][0]["results"][0]["ruleId"] == "policy-forbidden-dependency"

try:
    report.assert_valid()
except AssertionError as error:
    assert json.loads(str(error)) == document
else:
    raise AssertionError("Expected the policy finding to fail the assertion")

# A structural failure can be exported directly from the exception.
invalid = ContainerBuilder()
invalid.register(Handler)
try:
    invalid.build()
except ContainerBuildError as error:
    failure = json.loads(error.to_sarif())
    assert failure["runs"][0]["results"][0]["ruleId"] == "missing-component"
else:
    raise AssertionError("Expected a missing database registration")
```

`ContainerBuildError.compiled_graph` is available when compilation produced a complete graph that final validation
rejected. Structural failures retain their existing partial diagnostic graph and failure evidence. Both forms can be
exported through `error.to_sarif()` without retrying compilation.

## Assert validity in tests

Call `report.assert_valid()` to pass a valid report or raise `AssertionError` with the complete SARIF document as its
message. Captured source locations and the graph fingerprint are included automatically:

```python
from clean_ioc import ContainerBuilder


class Service:
    pass


builder = ContainerBuilder()
builder.register(Service)
container = builder.build()
report = container.validation_report()
report.assert_valid()
```

The method follows `report.is_valid`: errors fail; warnings alone pass. It returns `None` without rendering when the
report is valid. It inspects the existing report without re-running validation or activating components, and remains
active under Python's `-O` mode. `error.report.assert_valid()` uses captured failure evidence automatically too.

For a manually constructed `BuildReport`, the optional `graph`, `explanations`, and `evidence` arguments to
`to_sarif()` and `assert_valid()` supply reporting context. Explicit arguments can also override captured context;
`indent` controls JSON formatting. Context remains private and does not change report equality, hashing, or existing
text/JSON output.
