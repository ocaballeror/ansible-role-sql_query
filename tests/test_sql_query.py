from __future__ import unicode_literals

import os
import sys
import json
import warnings
from io import StringIO
from tempfile import NamedTemporaryFile

import yaml
import pyodbc
import pytest
from ansible.module_utils.basic import AnsibleModule

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
from library.sql_query import oracle_string
from library.sql_query import row_to_dict


if sys.version_info >= (3,):
    unicode = str
    from configparser import Error as ConfigError
else:
    from ConfigParser import Error as ConfigError


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


def raise_error(*args, **kwargs):
    raise pyodbc.Error('pyodbc error')


class FakeCursor:
    def __init__(self, rowcount=1):
        self.rowcount = rowcount

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def cursor(self):
        return self

    def execute(self, query, *args):
        if query.lower().startswith('select'):
            self.fetchall = lambda: []
        else:
            self.fetchall = raise_error


class FakeModule:
    def __init__(self, params=None, check_mode=False):
        params = params or {}
        self.params = params
        self.check_mode = check_mode

    def exit_json(self, **kwargs):
        kwargs['changed'] = kwargs.get('changed', False)
        print(json.dumps(kwargs))
        sys.exit(0)

    def fail_json(self, **kwargs):
        kwargs['changed'] = kwargs.get('changed', False)
        kwargs['failed'] = True
        print(json.dumps(kwargs))
        sys.exit(1)


@pytest.fixture
def drivers(monkeypatch):
    drivers = {k: k for k in DRIVERS}
    monkeypatch.setattr(sql_query, 'DRIVERS', drivers)


def test_docs():
    assert yaml.safe_load(StringIO(DOCUMENTATION))
    assert yaml.safe_load(StringIO(EXAMPLES))
    assert yaml.safe_load(StringIO(RETURN))


def test_connect(monkeypatch, drivers):
    """
    Check that the connection function returns a "valid" cursor.

    Sadly, there is no way to test the actual connection.
    """

    def fake_connect(conn_str, *args, **kwargs):
        cur = FakeCursor()
        cur.connection_string = conn_str
        cur.__dict__.update(kwargs)
        return cur

    config = INTERNAL_CONFIG.copy()
    monkeypatch.setattr(pyodbc, 'connect', fake_connect)
    with sql_query.connect(config) as conn:
        assert conn
        assert conn.connection_string == connection_string(config)


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


@pytest.mark.parametrize('key', ['port'])
def test_key_not_required(drivers, key):
    """
    Check that the port is not required, even though it can be passed as part
    of the config dictionary.
    """
    config = PARAM_CONFIG.copy()
    expect = INTERNAL_CONFIG.copy()
    expect['driver'] = sql_query.DRIVERS['mysql']

    # Specify the port directly
    config[key] = expect[key] = key
    assert get_config(config) == expect

    # Specify the port in config dict
    assert get_config({'config': config}) == expect

    # Specify the port in config and override it
    assert get_config({'config': config, key: key}) == expect

    # Try a config with no port number
    config.pop(key, None)
    expect.pop(key, None)
    assert get_config({'config': config}) == expect

    # Try with direct arguments and no port number
    assert get_config(config) == expect


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


def test_get_config_invalid_driver(monkeypatch):
    """
    Check that get_config raises an error when using a dbtype that has no
    associated driver.
    """
    monkeypatch.setitem(sql_query.DRIVERS, 'mssql', '')
    with pytest.raises(ModuleError) as error:
        get_config(PARAM_CONFIG.copy())
        assert 'no driver' in str(error.value).lower()


def assert_driver(monkeypatch, keys, expect, driver):
    with NamedTemporaryFile(mode='w+') as tmp:
        for key in keys:
            tmp.write('{}\nkey=value\n'.format(key))
        tmp.flush()
        monkeypatch.setattr(sql_query, 'ODBCINST', [tmp.name])
        find_drivers()
        assert sql_query.DRIVERS[driver] == expect


def test_find_driver_error(tmp_path, monkeypatch, recwarn):
    warnings.simplefilter("always")
    ini = tmp_path / 'odbc.ini'
    monkeypatch.setattr(sql_query, 'ODBCINST', [str(ini)])
    find_drivers()
    assert all(not value for key, value in sql_query.DRIVERS.items())
    assert recwarn.pop(UserWarning)

    ini.write_text("this is not valid ini format")
    with pytest.raises(ConfigError):
        find_drivers()
    assert all(not value for key, value in sql_query.DRIVERS.items())
    assert len(recwarn) == 0


@pytest.mark.parametrize(
    'dbtype, keys, expect',
    [
        ('mysql', ['[MySQL 5]', '[MySQL]'], '{MySQL 5}'),
        ('mysql', ['[MySQL 5.1]', '[MySQL 5]'], '{MySQL 5.1}'),
        ('mysql', ['[MySQL 8 Driver]', '[ODBC MySQL 5]'], '{MySQL 8 Driver}'),
        ('mysql', ['[MySQL 5]', '[ODBC Driver 5]'], '{MySQL 5}'),
        ('oracle', ['[Oracle 18]', '[Oracle 12.2g]'], '{Oracle 18}'),
        (
            'oracle',
            ['[Oracle 19 ODBC driver]', '[Oracle 18]'],
            '{Oracle 19 ODBC driver}',
        ),
    ],
    ids=[
        'Version better than no version',
        'version.1 better than bare version',
        'Parse with extra info in names',
        'Only match mysql drivers',
        'Oracle 18',
        'Oracle 19',
    ],
)
def test_find_driver(monkeypatch, dbtype, keys, expect):
    assert_driver(monkeypatch, keys, expect, dbtype)


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
def test_dsn_config(config, drivers):
    parsed = get_config(config)
    connstr = connection_string(parsed).lower() + ';'
    assert 'dsn' in connstr
    for key, value in config.items():
        key = ARG_MAPPING[key]
        assert '{}={};'.format(key, value) in connstr


def assert_in_config(key, value, config):
    parsed = get_config(config)
    assert parsed[key] == value
    connstr = ';' + connection_string(parsed).lower() + ';'
    assert ';{}={};'.format(key, value) in connstr


def test_odbc_opts(drivers):
    config = PARAM_CONFIG.copy()
    opts = {'ansinpw': 1, 'tds_version': '7.0'}
    config['odbc_opts'] = opts
    assert_in_config('ansinpw', 1, config)
    assert_in_config('tds_version', '7.0', config)


def test_odbc_opts_config(drivers):
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


def test_oracle_string(drivers):
    config = PARAM_CONFIG.copy()
    config['dbtype'] = 'oracle'
    parsed = get_config(config)
    for key, value in config.items():
        assert parsed[ARG_MAPPING[key]] == value

    connstr = connection_string(parsed).lower()
    arg_mapping = ARG_MAPPING.copy()
    arg_mapping['database'] = 'sid'
    arg_mapping['servername'] = 'host'
    for key, value in config.items():
        key = arg_mapping[key]
        assert '{}={}'.format(key, value) in connstr
    assert 'port=1521' in connstr


def test_oracle_string_port(drivers):
    config = PARAM_CONFIG.copy()
    config['dbtype'] = 'oracle'
    config['port'] = 12345

    parsed = get_config(config)
    assert parsed['port'] == 12345
    connstr = connection_string(parsed).lower()
    assert 'port=12345' in connstr


def test_connection_string_nodriver():
    """
    Check that connection_string() raises an AssertionError when no driver is
    specified (which shouldn't happen, by the way).
    """
    with pytest.raises(AssertionError):
        connection_string({})

    with pytest.raises(AssertionError):
        connection_string({'server': 's', 'username': 'u'})


def test_connection_string_emptydrivers():
    """
    Check that connection_string() doesn't fail when the driver list is empty.
    """
    string = connection_string({'driver': 'd', 'server': 's'})
    string = string.lower()
    assert string in ('driver=d;server=s', 'server=s;driver=d')


def test_connection_string_mssql(drivers):
    """
    Check that some keys are present in a mssql connection string.
    """
    driver = sql_query.DRIVERS['mssql']
    string = connection_string({'driver': driver, 'uid': 'someuser'}).lower()
    assert 'driver={}'.format(driver) in string
    assert 'uid=someuser' in string
    assert 'disable loopback check' not in string

    string = connection_string({'driver': driver, 'uid': 'dom\\user'}).lower()
    assert 'driver={}'.format(driver) in string
    assert 'uid=dom\\user' in string
    assert 'disable loopback check=yes' in string


def test_row_to_dict():
    class Row:
        def __init__(self, values):
            self.values = values
            self._iter = iter(self.values)

        def __iter__(self):
            return iter(self.values)

    row = Row(['value1', 'value2'])
    row.cursor_description = (('col1', ''), ('col2', ''))

    assert row_to_dict(None) is None
    assert row_to_dict(row) == {'col1': 'value1', 'col2': 'value2'}


def assert_run_module(capsys, changed, output=None, msg=None):
    """
    Invoke run_module() and check its output. It should write a JSON object to
    stdout with specific values for results and changed.
    """
    failure = msg is None
    with pytest.raises(SystemExit) as exit_code:
        sql_query.run_module()
        assert int(exit_code.value) == failure

    captured = capsys.readouterr()
    out = json.loads(captured.out)
    assert out['changed'] is changed
    if output is not None:
        assert out['output'] == output
        if output:
            assert out['ansible_facts']['query_rows'] == output
    elif msg is not None:
        assert out['msg'] == msg
        assert out['failed']


def test_setup_module(monkeypatch, tmp_path):
    """
    Write the input configuration to a JSON file and append it to the argv list
    so run_module() can find it.
    """
    module_args = {'query': 'drop table where name like ?', 'values': ['%%']}
    module_args.update(PARAM_CONFIG)
    args = {'ANSIBLE_MODULE_ARGS': module_args}

    in_file = tmp_path.absolute() / 'json.json'
    in_file.write_text(unicode(json.dumps(args)))
    new_argv = [__file__, str(in_file)]
    monkeypatch.setattr(sys, 'argv', new_argv)

    module = sql_query.setup_module()
    assert module
    assert isinstance(module, AnsibleModule)
    assert not module.check_mode
    parsed = {
        k: v
        for k, v in module.params.items()
        if v is not None or k in module_args
    }
    assert parsed == module_args


def test_run_module(monkeypatch, tmp_path, capsys):
    changed = True
    results = ['results']
    call_log = []

    def fake_run_query(query, values, config):
        call_log.append((query, values, config))
        return results, changed

    config = {'query': 'drop table where name like ?', 'values': ['%%']}
    config.update(PARAM_CONFIG)
    monkeypatch.setattr(sql_query, 'setup_module', lambda: FakeModule(config))
    monkeypatch.setattr(sql_query, 'run_query', fake_run_query)
    assert_run_module(capsys, changed, output=results)

    expect_config = INTERNAL_CONFIG.copy()
    expect_config['driver'] = sql_query.DRIVERS[config['dbtype']]
    assert call_log == [(config['query'], config['values'], expect_config)]


def test_run_module_check_mode(monkeypatch, tmp_path, capsys):
    config = {
        'query': 'drop table where name like ?',
        'values': ['%%'],
        '_ansible_check_mode': True,
    }
    config.update(PARAM_CONFIG)
    module = FakeModule(config)
    module.check_mode = True
    monkeypatch.setattr(sql_query, 'setup_module', lambda: module)
    assert_run_module(capsys, False, output='')


def test_run_module_exception(monkeypatch, tmp_path, capsys):
    """
    Test run_module() when an exception is raised.
    """
    changed = False
    error_msg = 'this is an error'

    def fake_run_query(query, values, config):
        raise ModuleError(error_msg)

    config = {'query': 'drop table where name like ?', 'values': ['%%']}
    config.update(PARAM_CONFIG)
    monkeypatch.setattr(sql_query, 'setup_module', lambda: FakeModule(config))

    # Raising a ModuleError should only print the error msg
    monkeypatch.setattr(sql_query, 'run_query', fake_run_query)
    assert_run_module(capsys, changed, msg=error_msg)

    # Raising any other kind of error should print both the error type and its
    # message
    expect_msg = '{}: {}'.format(pyodbc.Error, 'pyodbc error')
    monkeypatch.setattr(sql_query, 'run_query', raise_error)
    assert_run_module(capsys, changed, msg=expect_msg)
