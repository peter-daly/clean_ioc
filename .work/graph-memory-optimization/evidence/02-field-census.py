"""Additional identity-only field census, outside all memory/time measurements."""

import asyncio
import json
import sys
from dataclasses import fields
from pathlib import Path

from benchmarks import graph_memory_fixture as fixture
from benchmarks.graph_memory_evidence import DEFINITION_FIELDS, source_provenance
from clean_ioc.components import _ComponentDraft

case = fixture.build(8)
records = case.runtime._plan.graph._records
if records is None:
    raise RuntimeError("Expected a frozen component graph")
names = tuple(item.name for item in fields(_ComponentDraft))
result = {"source": source_provenance(), "routes": 8, "physical_records": len(records), "kinds": {}}
for kind in sorted({record.kind.value for record in records.values()}):
    group = [record for record in records.values() if record.kind.value == kind]
    result["kinds"][kind] = {
        "records": len(group),
        "unique_referents": {name: len({id(getattr(record, name)) for record in group}) for name in names},
        "definition_patterns": len(
            {
                tuple(
                    tuple(id(tag) for tag in record.tags) if name == "tags" else id(getattr(record, name))
                    for name in DEFINITION_FIELDS
                    if name != "id"
                )
                for record in group
            }
        ),
    }
Path(sys.argv[1]).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
asyncio.run(case.runtime.__aexit__(None, None, None))
