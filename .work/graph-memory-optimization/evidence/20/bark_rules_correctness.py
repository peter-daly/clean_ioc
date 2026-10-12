"""Correctness-only proof using both real, preserved Bark rule implementations.

No consumer file is edited. The adapter only migrates rule registration in this
process to the unified API; both original function objects still execute.
"""
import hashlib
import json
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[4]
BASELINE = Path('/Users/peter.daly/.codex/task-baselines/clean-ioc-task20-20261010-v2')
CONSUMER = BASELINE / 'consumer-current'
sys.path[:0] = [str(CONSUMER / 'bark-source'), str(WORKSPACE), str(CONSUMER / 'cop-source')]

import clean_ioc.container as compiler
from clean_ioc import ContainerBuilder
from bark_core.unit_of_work import UnitOfWork
from bark_core.unit_of_work import bundles
from tests.unit.bundles import test_unit_of_work as fixture

real_rules = (bundles.validate_unit_of_work_graph, bundles.validate_unit_of_work_graph_on_validation)
events = []


def register_both(builder):
    for rule in real_rules:
        def counted(context, rule=rule):
            events.append(rule.__name__)
            yield from rule(context)
        builder.add_validation_rule(counted)


# The preserved consumer bundle still uses mode='validation'. Its registration
# surface is migrated locally, with neither callback removed or stubbed.
def migrated_apply(self, builder):
    register_both(builder)


bundles.RegisterUnitOfWorkValidationBundle.apply = migrated_apply


def wrong_lifespan():
    builder = ContainerBuilder()
    builder.register(UnitOfWork, fixture.ResourceIndependentUnitOfWork, lifespan='singleton')
    register_both(builder)
    return builder


def wrong_sql_write():
    builder = ContainerBuilder()
    builder.register(fixture.RepositorySession, factory=fixture.create_repository_session, lifespan='scoped')
    builder.register(fixture.SqlAlchemyWritingRepository)
    builder.register(fixture.CommandHandler[fixture.MockCommand], fixture.WritingOperationHandler)
    register_both(builder)
    return builder


def wrong_sql_begin():
    return fixture._sqlalchemy_repository_builder(
        fixture.BeginningRepositoryCommandHandler, fixture.SqlAlchemyBeginningRepository
    )


results = []
for factory, expected in (
    (wrong_lifespan, 'uow-scope-mismatch'),
    (wrong_sql_write, 'uow-sqlalchemy-write-without-boundary'),
    (wrong_sql_begin, 'uow-sqlalchemy-begin-inside-boundary'),
):
    events.clear()
    with factory().build():
        pass
    assert events == [], events
    with factory().analyse() as analysis:
        assert analysis.emission_complete, analysis.report.to_text()
        assert analysis.report.complete, analysis.report.to_text()
        assert all(outcome.status == 'completed' for outcome in analysis.report.rule_outcomes), analysis.report.rule_outcomes
        codes = sorted({issue.code for issue in analysis.report.errors})
        assert expected in codes, (expected, codes)
        assert events == [rule.__name__ for rule in real_rules], events
        for _ in range(2):
            analysis.report.to_json()
            analysis.report.to_text()
            analysis.report.to_sarif()
        assert events == [rule.__name__ for rule in real_rules], events
        results.append({'fixture': factory.__name__, 'build_calls': 0, 'analysis_calls': list(events), 'errors': codes})

files = [Path(compiler.__file__), Path(bundles.__file__), Path(fixture.__file__)]
print(json.dumps({'correctness_only': True, 'imports': [
    {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()} for path in files
], 'results': results}, indent=2))
