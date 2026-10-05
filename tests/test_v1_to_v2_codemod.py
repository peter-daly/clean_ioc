"""Behavioral checks for the bundled migration helper."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import cast

SCRIPT = Path(__file__).parents[1] / ".library-skills/migrate-clean-ioc/scripts/migrate_v1_to_v2.py"
SPEC = importlib.util.spec_from_file_location("migrate_v1_to_v2", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_simple_composition_migrates_and_is_idempotent() -> None:
    original = """from clean_ioc import Container, Lifespan

class Service:
    def __init__(self, port: int):
        self.port = port

def create():
    container = Container()
    container.register(Service, lifespan=Lifespan.once_per_graph, dependency_config={"port": 80})
    service = container.resolve(Service)
    return service
"""
    updated, findings = MODULE.transform(original)
    assert findings == []
    assert "container = ContainerBuilder()" in updated
    assert "container = container.build()\n    service = container.resolve(Service)" in updated
    assert "lifespan='per_resolution'" in updated
    assert 'arguments={"port": 80}' in updated
    assert MODULE.transform(updated) == (updated, [])
    namespace: dict[str, object] = {}
    exec(updated, namespace)  # noqa: S102
    create = cast(Callable[[], object], namespace["create"])
    assert getattr(create(), "port") == 80


def test_later_mutation_does_not_move_build_too_early() -> None:
    original = """from clean_ioc import Container
c = Container()
c.register(A)
x = c.resolve(A)
if enabled:
    c.register(B)
"""
    updated, findings = MODULE.transform(original)
    assert updated == original
    assert any("build boundary" in finding.message for finding in findings)


def test_dynamic_settings_stay_for_manual_review() -> None:
    original = """from clean_ioc import Container, Lifespan
c = Container()
c.register(A, dependency_config={"value": DependencySettings(value_factory=callback)})
x = c.resolve(A)
"""
    updated, findings = MODULE.transform(original)
    assert "dependency_config=" in updated
    assert any("DependencySettings" in finding.message for finding in findings)
    assert any("dependency_config=" in finding.message for finding in findings)


def test_non_ascii_source_offsets_and_crlf() -> None:
    line_end = chr(13) + chr(10)
    original = (
        f"from clean_ioc import ContainerBuilder, Lifespan{line_end}"
        f'name = "café"; builder = ContainerBuilder(){line_end}'
        f"builder.register(Service, lifespan=Lifespan.scoped){line_end}"
    )
    updated, findings = MODULE.transform(original)
    assert findings == []
    assert updated.endswith(f"builder.register(Service, lifespan='scoped'){line_end}")


def test_unrelated_register_and_lifespan_usage_are_only_reported() -> None:
    original = """from clean_ioc import Lifespan
other.register(A, dependency_config={"x": 1})
value = int(Lifespan.singleton)
"""
    updated, findings = MODULE.transform(original)
    assert updated == original
    assert any("dependency_config=" in finding.message for finding in findings)
    assert any("Lifespan member" in finding.message for finding in findings)


def test_cli_preview_check_and_write(tmp_path: Path) -> None:
    path = tmp_path / "composition.py"
    original = "from clean_ioc import Container\nc = Container()\nc.register(A)\nx = c.resolve(A)\n"
    path.write_text(original)
    preview = subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True, check=True)  # noqa: S603
    assert "+c = c.build()" in preview.stdout
    assert path.read_text() == original
    check = subprocess.run([sys.executable, str(SCRIPT), "--check", str(path)], capture_output=True, text=True)  # noqa: S603
    assert check.returncode == 1
    subprocess.run([sys.executable, str(SCRIPT), "--write", str(path)], check=True, capture_output=True, text=True)  # noqa: S603
    assert "c = c.build()" in path.read_text()
    clean = subprocess.run([sys.executable, str(SCRIPT), "--check", str(path)], capture_output=True, text=True)  # noqa: S603
    assert clean.returncode == 0
