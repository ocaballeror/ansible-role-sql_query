import os
import sys
from io import StringIO

import yaml
import pyodbc
import pytest

root = (os.path.split(__file__)[0] or '.') + '/..'
sys.path.append(root)
from library import run_query
from library.run_query import DOCUMENTATION
from library.run_query import EXAMPLES
from library.run_query import RETURN
from library.run_query import DRIVERS
from library.run_query import get_config


INTERNAL_CONFIG = {
    'driver': 'mysql',
    'db': 'db',
    'user': 'user',
    'pwd': 'pwd',
    'server': 'server',
}
PARAM_CONFIG = {
    'username': 'user',
    'password': 'pwd',
    'dbtype': 'mysql',
    'servername': 'server',
    'database': 'db',
}


def raise_error():
    raise pyodbc.Error


class FakeCursor:
    def __init__(self, rowcount=1):
        self.rowcount = rowcount

    def __enter__(self):
        print('before')
        return self

    def __exit__(self, *args):
        print('after', *args)

    def execute(self, query, *args):
        if query.lower().startswith('select'):
            self.fetchall = lambda: []
        else:
            self.fetchall = raise_error


class FakeModule:
    def __init__(self, params=None):
        self.params = params or {}

    def exit_json(self, **kwargs):
        raise SystemExit('exit_json: {}'.format(kwargs))

    def fail_json(self, **kwargs):
        raise SystemExit('fail_json: {}'.format(kwargs))


def test_docs():
    assert yaml.safe_load(StringIO(DOCUMENTATION))
    assert yaml.safe_load(StringIO(EXAMPLES))
    assert yaml.safe_load(StringIO(RETURN))


def test_run_query(monkeypatch):
    monkeypatch.setattr(run_query, 'connect', lambda x: FakeCursor())
    assert ([], False) == run_query.run_query('select', [], INTERNAL_CONFIG)
    assert ([], True) == run_query.run_query('delete', [], INTERNAL_CONFIG)

    # Set rowcount to 0 so it's not marked as modified
    monkeypatch.setattr(run_query, 'connect', lambda x: FakeCursor(0))
    assert ([], False) == run_query.run_query('select', [], INTERNAL_CONFIG)
    assert ([], False) == run_query.run_query('delete', [], INTERNAL_CONFIG)


def test_get_config():
    config = PARAM_CONFIG.copy()
    expect = INTERNAL_CONFIG.copy()
    expect['driver'] = DRIVERS['mysql']

    module = FakeModule(config)
    assert get_config(module) == expect

    module = FakeModule({'config': config})
    assert get_config(module) == expect

    username = 'other user'
    other_config = config.copy()
    other_expect = expect.copy()
    other_config['user'] = username
    other_expect['user'] = username
    module = FakeModule({'config': config, 'username': username})
    assert get_config(module) == other_expect


def test_get_config_errors():
    # Empty dictionary
    module = FakeModule({})
    with pytest.raises(SystemExit) as error:
        get_config(module)
    assert 'fail_json' in str(error.value)

    # Check that all the keys are required
    for key in PARAM_CONFIG:
        config = PARAM_CONFIG.copy()
        config.pop(key)
        module = FakeModule(config)
        with pytest.raises(SystemExit) as error:
            get_config(module)
        assert 'fail_json' in str(error.value)
        assert key in str(error.value)

    # Try an invalid database name
    db = 'this is not a valid database'
    config = PARAM_CONFIG.copy()
    config['dbtype'] = db
    module = FakeModule(config)
    with pytest.raises(SystemExit) as error:
        get_config(module)
    assert 'fail_json' in str(error.value)
    assert 'must be one of' in str(error.value)