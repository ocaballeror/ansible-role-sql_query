import os
import sys
from io import StringIO
from tempfile import NamedTemporaryFile

import yaml
import pyodbc
import pytest

# flake8: noqa: E402
root = (os.path.split(__file__)[0] or '.') + '/..'
sys.path.append(root)
from library import sql_query
from library.sql_query import DOCUMENTATION
from library.sql_query import EXAMPLES
from library.sql_query import RETURN
from library.sql_query import DRIVERS
from library.sql_query import ModuleError
from library.sql_query import get_config
from library.sql_query import find_drivers


INTERNAL_CONFIG = {
    'driver': 'mysql',
    'database': 'database',
    'uid': 'uid',
    'pwd': 'pwd',
    'server': 'server',
}
PARAM_CONFIG = {
    'username': 'uid',
    'password': 'pwd',
    'dbtype': 'mysql',
    'servername': 'server',
    'database': 'database',
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
    assert get_config(config) == expect
    assert get_config({'config': config}) == expect

    username = 'other user'
    other_config = config.copy()
    other_expect = expect.copy()
    other_config['user'] = username
    other_expect['uid'] = username
    assert get_config({'config': config, 'username': username}) == other_expect


def test_get_config_empty():
    """
    Test that get_config raises an error when given an empty dictionary.
    """
    with pytest.raises(ModuleError) as error:
        get_config({})
    assert 'Missing configuration parameter' in str(error.value)


@pytest.mark.parametrize('key', PARAM_CONFIG)
def test_get_config_missing_required(key):
    """
    Check that get_config raises an error when a required key is missing.
    """
    config = PARAM_CONFIG.copy()
    config.pop(key)
    with pytest.raises(ModuleError) as error:
        get_config(config)
    assert 'Missing configuration parameter' in str(error.value)
    assert key in str(error.value)


def test_get_config_invalid_database():
    """
    Check that get_config raises an error when passing an unknown dbtype.
    """
    db = 'this is not a valid database'
    config = PARAM_CONFIG.copy()
    config['dbtype'] = db
    with pytest.raises(ModuleError) as error:
        get_config(config)
    assert 'must be one of' in str(error.value)


def assert_driver(monkeypatch, keys, expect, driver):
    with NamedTemporaryFile(mode='w+') as tmp:
        for key in keys:
            tmp.write('{}\nkey=value\n'.format(key))
        tmp.flush()
        monkeypatch.setattr(sql_query, 'ODBCINST', tmp.name)
        find_drivers()
        assert sql_query.DRIVERS[driver] == expect


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
    assert_driver(monkeypatch, keys, expect, 'mysql')


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
    assert_driver(monkeypatch, keys, expect, 'mssql')
