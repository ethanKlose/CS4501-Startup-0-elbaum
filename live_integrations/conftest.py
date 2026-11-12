"""No fake providers; explicit flag required before external account activity."""
import json
from pathlib import Path

import pytest
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
RESULTS = []


def pytest_addoption(parser):
    group=parser.getgroup('live-platform-integrations')
    group.addoption('--run-integrations', action='store_true', help='Permit real Google/Instacart/Kroger smoke tests; see BETA_INTEGRATIONS.md')
    group.addoption('--integration-service', choices=['google','instacart','kroger','all'], default='google')


def pytest_collection_modifyitems(config, items):
    enabled=config.getoption('--run-integrations')
    chosen=config.getoption('--integration-service')
    for item in items:
        if Path(__file__).parent not in Path(str(item.fspath)).parents:
            continue
        service='google' if 'google' in item.name else 'kroger' if 'kroger' in item.name else 'instacart'
        if not enabled or chosen not in {service,'all'}:
            item.add_marker(pytest.mark.skip(reason='Real platform test requires --run-integrations and the selected service'))


@pytest.fixture
def live_environment(request):
    assert request.config.getoption('--run-integrations')
    load_dotenv(ROOT / '.env')
    yield RESULTS


def pytest_runtest_logreport(report):
    if report.when=='call' or (report.when=='setup' and report.outcome!='passed'):
        RESULTS.append(dict(test=report.nodeid,phase=report.when,outcome=report.outcome,duration_seconds=round(report.duration,3)))


def pytest_sessionfinish(session, exitstatus):
    if not session.config.getoption('--run-integrations'):
        return
    path=ROOT/'test-results'/'live-integrations-report.json'
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(dict(exit_status=int(exitstatus),results=RESULTS),indent=2)+'\n')
