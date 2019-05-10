import os
import sys
from io import StringIO
from tempfile import NamedTemporaryFile

import yaml
import pyodbc
import pytest

root = (os.path.split(__file__)[0] or '.') + '/..'
sys.path.append(root)
from library import sql_query
from library.sql_query import DOCUMENTATION
from library.sql_query import EXAMPLES
from library.sql_query import RETURN
from library.sql_query import DRIVERS
from library.sql_query import get_config
from library.sql_query import find_drivers


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
    monkeypatch.setattr(sql_query, 'connect', lambda x: FakeCursor())
    assert ([], False) == sql_query.run_query('select', [], INTERNAL_CONFIG)
    assert ([], True) == sql_query.run_query('delete', [], INTERNAL_CONFIG)

    # Set rowcount to 0 so it's not marked as modified
    monkeypatch.setattr(sql_query, 'connect', lambda x: FakeCursor(0))
    assert ([], False) == sql_query.run_query('select', [], INTERNAL_CONFIG)
    assert ([], False) == sql_query.run_query('delete', [], INTERNAL_CONFIG)


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


def test_get_config_empty():
    """
    Test that get_config raises an error when given an empty dictionary.
    """
    module = FakeModule({})
    with pytest.raises(SystemExit) as error:
        get_config(module)
    assert 'fail_json' in str(error.value)


@pytest.mark.parametrize('key', PARAM_CONFIG)
def test_get_config_missing_required(key):
    """
    Check that get_config raises an error when a required key is missing.
    """
    config = PARAM_CONFIG.copy()
    config.pop(key)
    module = FakeModule(config)
    with pytest.raises(SystemExit) as error:
        get_config(module)
    assert 'fail_json' in str(error.value)
    assert key in str(error.value)


def test_get_config_invalid_database():
    """
    Check that get_config raises an error when passing an unknown dbtype.
    """
    db = 'this is not a valid database'
    config = PARAM_CONFIG.copy()
    config['dbtype'] = db
    module = FakeModule(config)
    with pytest.raises(SystemExit) as error:
        get_config(module)
    assert 'fail_json' in str(error.value)
    assert 'must be one of' in str(error.value)


@pytest.mark.parametrize('keys, expect', [
    (['[MySQL 5]', '[MySQL]'], 'MySQL 5'),
    (['[MySQL 5.1]', '[MySQL 5]'], 'MySQL 5.1'),
    (['[MySQL 8 Driver]', '[ODBC MySQL 5]'], 'MySQL 8 Driver'),
    (['[MySQL 5]', '[ODBC Driver 5]'], 'MySQL 5'),
], ids=[
    'Version better than no version',
    'version.1 better than bare version',
    'Parse with extra info in names',
    'Only match mysql drivers',
])
def test_find_driver_mysql(monkeypatch, keys, expect):
    with NamedTemporaryFile(mode='w+') as tmp:
        for key in keys:
            tmp.write('{}\nkey=value\n'.format(key))
        tmp.flush()
        monkeypatch.setattr(sql_query, 'ODBCINST', tmp.name)
        find_drivers()
        assert sql_query.DRIVERS['mysql'] == expect


@pytest.mark.parametrize('keys, expect', [
    (['[FreeTDS]', '[SQL Server 18.1]'], 'FreeTDS'),
    (['[FreeTDS 3]', '[SQL Server 18.1]'], 'FreeTDS 3'),
    (['[SQL Server 18]', '[SQL Server 13]'], 'SQL Server 18'),
    (['[SQL Server]', '[SQL Server 1]'], 'SQL Server 1'),
    (['[SQL Server]', '[MySQL]'], 'SQL Server'),
], ids=[
    'FreeTDS over sql server',
    'Versioned FreeTDS over sql server',
    'Pick newest sql server',
    'Version better than no version',
    'Only match sql server drivers',
])
def test_find_driver_mssql(monkeypatch, keys, expect):
    with NamedTemporaryFile(mode='w+') as tmp:
        for key in keys:
            tmp.write('{}\nkey=value\n'.format(key))
        tmp.flush()
        monkeypatch.setattr(sql_query, 'ODBCINST', tmp.name)
        find_drivers()
        assert sql_query.DRIVERS['mssql'] == expect
