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
from library.sql_query import ARG_MAPPING
from library.sql_query import ModuleError
from library.sql_query import get_config
from library.sql_query import find_drivers
from library.sql_query import connection_string


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


@pytest.fixture
def drivers(monkeypatch):
    drivers = {k: k for k in DRIVERS}
    monkeypatch.setattr(sql_query, 'DRIVERS', drivers)


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


def test_get_config(drivers):
    config = PARAM_CONFIG.copy()
    expect = INTERNAL_CONFIG.copy()
    expect['driver'] = sql_query.DRIVERS['mysql']
    assert get_config(config) == expect
    assert get_config({'config': config}) == expect

    username = 'other user'
    other_config = config.copy()
    other_expect = expect.copy()
    other_config['user'] = username
    other_expect['uid'] = username
    assert get_config({'config': config, 'username': username}) == other_expect


def test_get_config_empty(drivers):
    """
    Test that get_config raises an error when given an empty dictionary.
    """
    with pytest.raises(ModuleError) as error:
        get_config({})
    assert 'Missing configuration parameter' in str(error.value)


@pytest.mark.parametrize('key', PARAM_CONFIG)
def test_get_config_missing_required(key, drivers):
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


@pytest.mark.parametrize(
    'keys, expect',
    [
        (['[MySQL 5]', '[MySQL]'], '{MySQL 5}'),
        (['[MySQL 5.1]', '[MySQL 5]'], '{MySQL 5.1}'),
        (['[MySQL 8 Driver]', '[ODBC MySQL 5]'], '{MySQL 8 Driver}'),
        (['[MySQL 5]', '[ODBC Driver 5]'], '{MySQL 5}'),
    ],
    ids=[
        'Version better than no version',
        'version.1 better than bare version',
        'Parse with extra info in names',
        'Only match mysql drivers',
    ],
)
def test_find_driver_mysql(monkeypatch, keys, expect):
    assert_driver(monkeypatch, keys, expect, 'mysql')


@pytest.mark.parametrize(
    'keys, expect',
    [
        (['[FreeTDS]', '[SQL Server 18.1]'], '{FreeTDS}'),
        (['[FreeTDS 3]', '[SQL Server 18.1]'], '{FreeTDS 3}'),
        (['[SQL Server 18]', '[SQL Server 13]'], '{SQL Server 18}'),
        (['[SQL Server]', '[SQL Server 1]'], '{SQL Server 1}'),
        (['[SQL Server]', '[MySQL]'], '{SQL Server}'),
    ],
    ids=[
        'FreeTDS over sql server',
        'Versioned FreeTDS over sql server',
        'Pick newest sql server',
        'Version better than no version',
        'Only match sql server drivers',
    ],
)
def test_find_driver_mssql(monkeypatch, keys, expect):
    assert_driver(monkeypatch, keys, expect, 'mssql')


@pytest.mark.parametrize(
    'config',
    [
        {'dsn': 'asdf'},
        {'dsn': 'asdf', 'username': 'asdf'},
        {'dsn': 'asdf', 'password': 'asdf'},
    ],
    ids=['missing username and pwd', 'missing pwd', 'missing username'],
)
def test_dsn_config_error(config):
    with pytest.raises(ModuleError):
        get_config(config)


@pytest.mark.parametrize(
    'config',
    [
        {'dsn': 'asdf', 'password': 'asdf', 'username': 'asdf'},
        {
            'dsn': 'asdf',
            'password': 'asdf',
            'username': 'asdf',
            'servername': 'asdf',
        },
        {
            'dsn': 'what',
            'database': 'asdf',
            'dbtype': 'mssql',
            'password': 'asdf',
            'username': 'asdf',
            'servername': 'asdf',
        },
    ],
)
def test_dsn_config(config):
    parsed = get_config(config)
    connstr = connection_string(parsed).lower() + ';'
    assert 'dsn' in connstr
    for key, value in config.items():
        key = ARG_MAPPING[key]
        assert '{}={};'.format(key, value) in connstr


def assert_in_config(key, value, config):
    parsed = get_config(config)
    assert parsed[key] == value
    connstr = connection_string(parsed).lower() + ';'
    assert ';{}={};'.format(key, value) in connstr


def test_odbc_opts():
    config = PARAM_CONFIG.copy()
    opts = {'ansinpw': 1, 'tds_version': '7.0'}
    config['odbc_opts'] = opts
    assert_in_config('ansinpw', 1, config)
    assert_in_config('tds_version', '7.0', config)


def test_odbc_opts_config():
    config = PARAM_CONFIG.copy()
    opts = {'ansinpw': 1, 'tds_version': '7.0'}
    config['config'] = {'odbc_opts': opts}
    assert_in_config('ansinpw', 1, config)
    assert_in_config('tds_version', '7.0', config)

    config['config'] = {'odbc_opts': {'ansinpw': 1}}
    config['odbc_opts'] = {'ansinpw': 0}
    assert_in_config('ansinpw', 0, config)

    config['config'] = {'odbc_opts': {'ansinpw': 1}}
    config['odbc_opts'] = {'tds_version': '7.0'}
    assert_in_config('tds_version', '7.0', config)
    assert 'ansinpw' not in get_config(config)
