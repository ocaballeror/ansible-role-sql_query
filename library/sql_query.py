#!/usr/bin/python
from __future__ import unicode_literals
import re
import os
import sys
import warnings
from contextlib import contextmanager

if sys.version_info >= (3,):
    from configparser import ConfigParser
else:
    from ConfigParser import ConfigParser


import pyodbc
from ansible.module_utils.basic import AnsibleModule


ANSIBLE_METADATA = {'metadata_version': '1.0', 'status': ['beta']}

DOCUMENTATION = '''
---
module: sql_query

short_description: Execute a query on a database

version_added: "2.4"

description:
    - Execute a query on a database

options:
    config:
        description: A dictionary with all the database configuration \
                     parameters described below

    dsn:
        description: Use a pre-defined DataSourceName in your odbc config
        notes:
            - Any other parameters you specify will override your config
    servername:
        description: The hostname of the server to target
        notes:
            - For mssql servers, include the database instance as well
    port:
        description: Server port number
        type: int
    database:
        description: Database name
    username:
        description: User name
    password:
        description: Database password
    dbtype:
        description: Database technology
        choices:
            - mssql
            - mysql
    odbc_opts:
        description: Extra odbc options to include in the connection string
        type: dict
    query:
        description: The actual query to run
        required: true
    values:
        description: List of variables to substitute in the query
        type: list
        required: false

notes:
    - Needs the odbc binary to be installed
    - Needs the appropriate drivers for each database type
    - Needs the pyodbc python package
    - Username and password are required for now, even if you use a pre-defined
      dsn. You shouldn't have your plain-text credentials in those files anyway
    - The config dictionary can contain as many of the other database
      configuration params as you want. You can mix and match, but the params
      you specify separately will take preference over 'config'.
    - Whether separately, or inside 'config', all parameters are required.
    - It is recommended that you use the "values" keyword to interpolate
      variables rather than placing them in the query string yourself. This
      ensures they are properly quoted and protects you against sql injection
      attacks.

author:
    - Oscar Caballero (ocaballeror@tutanota.com)
'''

EXAMPLES = r'''
# Run a simple query
- name: Execute query
  sql_query:
    servername: server.domain.com\instance
    database: db_test
    username: rbamouser\itsme
    password: My_AD_Password123
    dbtype: mssql
    query: 'delete from table where 1 = 1'

# Select data and register the result
- name: Select data
  sql_query:
    servername: mysql-server.domain.com
    database: db_test
    username: sa
    password: Passw0rd
    dbtype: mysql
    query: 'select * from table'
  register: query_output

# Interpolate variables (recommended)
- name: Select with variable escaping
  sql_query:
    config: ...
    query: select * from table where col = ? or col = ?
    values:
      - "{{ variable1 }}"
      - "{{ variable2 }}"

# Run multiple queries with the same configuration
- block:
  - name: Set config
    set_fact:
      config:
        servername: server.domain.com\instance
        database: db_test
        username: sa
        password: Passw0rd
        dbtype: mssql

  - name: Execute query
    sql_query:
      config: "{{ config }}"
      query: 'insert into table values ("a")'

  - name: Execute query
    sql_query:
      config: "{{ config }}"
      query: 'insert into table values ("b")'

# Use a pre-defined DSN
- name: Use my DSN
  sql_query:
    dsn: some_server
    query: 'exec dbo.NukeAllTables @force=yes'
    # Username and password are still required
    username: root
    password: root

# Override any DSN preferences
- name: Override my DSN
  sql_query:
    dsn: some_server
    query: 'exec dbo.NukeAllTables @force=yes'
    username: root
    password: root
    # Override any parameters you want
    servername: server.domain.com\INST
    driver: CustomDriver
'''

RETURN = '''
output:
    description: Query results (if applicable)
'''

ODBCINST = ['/etc/odbcinst.ini', '/usr/local/etc/odbcinst.ini', '~/.odbc.ini']
DRIVERS = {'mysql': '', 'mssql': '', 'oracle': ''}
ARG_MAPPING = {
    'dsn': 'dsn',
    'username': 'uid',
    'password': 'pwd',
    'database': 'database',
    'servername': 'server',
    'dbtype': 'driver',
    'port': 'port',
    'odbc_opts': 'odbc_opts',
}


class ModuleError(Exception):
    pass


def normalize_version(v):
    "Return a proper version number"
    if not v:
        return [0]
    return [int(x) for x in re.sub(r'(\.0+)*$', '', v).split('.')]


def best_driver(parser, search):
    """
    Find the newest driver whose name matches a search regex.
    """
    drivers = [
        s for s in parser.sections() if re.search(search, s, flags=re.I)
    ]
    versions = []
    for section in drivers:
        version = normalize_version(re.sub(r'[^\d\.]', '', section))
        versions.append((version, section))

    if not versions:
        return ''
    best = sorted(versions, reverse=True)[0][-1]
    return '{{{}}}'.format(best)


def find_drivers():
    """
    Fill the DRIVERS dictionary with the best driver for every db type.
    """
    files = [os.path.expanduser(f) for f in ODBCINST]
    parser = ConfigParser()
    good_files = parser.read(files)
    if not good_files:
        warnings.warn('No ODBC configuration could be read')
        return

    DRIVERS['mysql'] = best_driver(parser, 'mysql')
    DRIVERS['oracle'] = best_driver(parser, 'oracle')
    DRIVERS['mssql'] = best_driver(parser, 'freetds')
    if not DRIVERS['mssql']:
        DRIVERS['mssql'] = best_driver(parser, 'sql server')


@contextmanager
def connect(config, autocommit=True):
    """
    Connect to a database with the given connection string and yield a valid
    cursor to be used in a context.
    """
    conn_str = connection_string(config)
    with pyodbc.connect(conn_str, autocommit=autocommit) as conn:
        with conn.cursor() as cursor:
            yield cursor


def connection_string(config):
    has_driver = bool(config.get('driver', '') or config.get('dsn', ''))
    assert has_driver, 'No driver specified'

    driver = config.get('driver', '').lower()
    if driver and driver == DRIVERS.get('oracle', '').lower():
        template = oracle_string(config)
    else:
        mssql = DRIVERS.get('mssql', '').lower()
        if driver == mssql and '\\' in config.get('uid', ''):
            config['Disable loopback check'] = 'yes'
        template = ";".join(
            '{}={}'.format(k.upper(), v) for k, v in config.items()
        )
    return template


def oracle_string(config):
    """
    Build and return an Oracle connection string.
    """
    config['port'] = config.get('port', 1521)
    dbq = '(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST={server})(PORT={port}))'
    dbq += '(CONNECT_DATA=(SID={database})))'
    template = 'DRIVER={driver};DBQ=%s;UID={uid};PWD={pwd};' % dbq
    return template.format(**config)


def row_to_dict(row):
    """
    Convert a pyodbc Row object to a dictionary.
    """
    if row is None:
        return None
    return dict(zip([t[0] for t in row.cursor_description], row))


def run_query(query, values, config):
    """
    Execute the query with the specified config dictionary.
    """
    results = []
    modified = False
    with connect(config) as cur:
        cur.execute(query, *values)
        try:
            # Will raise an exception if the query doesn't return results
            results = list(map(row_to_dict, cur.fetchall()))
            modified = False
        except pyodbc.Error:
            results = []
            modified = cur.rowcount > 0
    return results, modified


def require_args(config, args):
    """
    Check that all the arguments are present in a config dictionary or raise a
    ModuleError.
    """
    r_mapping = {v: k for k, v in ARG_MAPPING.items()}
    missing = [r_mapping[k] for k in args if not config.get(k, '')]
    if missing:
        msg = 'Missing configuration parameters: {}'.format(missing)
        raise ModuleError(msg)


def get_config(params):
    """
    Parse the configuration received by the module. Create the necessary
    mappings and fail if any argument is missing.
    """
    config = params.get('config', None) or {}
    config = config.copy()
    for k, v in ARG_MAPPING.items():
        if config.get(k, None):
            config[v] = config.pop(k)
        if params.get(k, None):
            config[v] = params[k]
    config.update(config.pop('odbc_opts', {}))

    require_args(config, ['uid', 'pwd'])

    if config.get('dsn', False):
        return config

    # Find missing or empty configuration values
    require_args(config, ['database', 'server', 'driver'])

    if config['driver'].lower() not in DRIVERS:
        msg = 'DB type must be one of {}'.format(list(DRIVERS))
        raise ModuleError(msg)
    config['driver'] = DRIVERS[config['driver'].lower()]
    if not config['driver']:
        msg = 'No driver found for dbtype in {}'.format(ODBCINST)
        raise ModuleError(msg)
    return config


def setup_module():
    # define available arguments/parameters a user can pass to the module
    module_args = dict(
        config=dict(type='dict', required=False, no_log=True),
        dsn=dict(type='str', required=False),
        servername=dict(type='str', required=False),
        port=dict(type='int', required=False),
        database=dict(type='str', required=False),
        username=dict(type='str', required=False),
        password=dict(type='str', required=False, no_log=True),
        dbtype=dict(type='str', required=False),
        odbc_opts=dict(type='dict', required=False),
        query=dict(type='str', required=True),
        values=dict(type='list', required=False, default=[]),
    )

    # the AnsibleModule object will be our abstraction working with Ansible
    # this includes instantiation, a couple of common attr would be the
    # args/params passed to the execution, as well as if the module
    # supports check mode
    module = AnsibleModule(argument_spec=module_args, supports_check_mode=True)
    return module


def run_module():
    result = dict(changed=False, output='')
    module = setup_module()

    # if the user is working with this module in only check mode we do not
    # want to make any changes to the environment, just return the current
    # state with no modifications
    if module.check_mode:
        module.exit_json(**result)

    find_drivers()
    try:
        config = get_config(module.params)
        query, values = module.params['query'], module.params['values']
        results, modified = run_query(query, values, config)
    except ModuleError as e:
        module.fail_json(msg=str(e), **result)
    except Exception as e:
        msg = '{}: {}'.format(type(e), str(e))
        module.fail_json(msg=msg, **result)

    result['changed'] = modified
    result['output'] = results
    result['ansible_facts'] = {'query_rows': results}

    # in the event of a successful module execution, you will want to
    # simple AnsibleModule.exit_json(), passing the key/value results
    module.exit_json(**result)


if __name__ == '__main__':
    run_module()
