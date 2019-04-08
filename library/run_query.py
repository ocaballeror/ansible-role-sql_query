#!/usr/bin/python
from contextlib import contextmanager

import pyodbc
from ansible.module_utils.basic import AnsibleModule


ANSIBLE_METADATA = {'metadata_version': '1.0', 'status': ['beta']}

DOCUMENTATION = '''
---
module: run_query

short_description: Set maintenance mode on a target server.

version_added: "2.4"

description:
    - Execute a query on a database

options:
    config:
        description: A dictionary with all the database configuration \
                     parameters described below
    servername:
        description: The hostname of the server to target
        notes:
            - For mssql servers, include the database instance as well
    database:
        description: Database name
    user:
        description: User name
    password:
        description: Database password
    dbtype:
        description: Database technology
        choices:
            - mssql
            - mysql
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
    - The config dictionary can contain as many of the other database
      configuration params as you want. You can mix and match, but the params
      you specify separately will take preference over 'config'.
    - Whether separately, or inside 'config', all parameters are required.

author:
    - Oscar Caballero (ocaballeror@tutanota.com)
'''

EXAMPLES = r'''
# Run a simple query
- name: Execute query
  run_query:
    servername: server.domain.com\instance
    database: db_test
    username: sa
    password: Passw0rd
    dbtype: mssql
    query: 'delete from table where 1 = 1'

# Select data and register the result
- name: Select data
  run_query:
    servername: mysql-server.domain.com
    database: db_test
    username: sa
    password: Passw0rd
    dbtype: mysql
    query: 'select * from table'
  register: query_output

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
    run_query:
      config: "{{ config }}"
      query: 'insert into table values ("a")'

  - name: Execute query
    run_query:
      config: "{{ config }}"
      query: 'insert into table values ("b")'
'''

RETURN = '''
output:
    description: Query results (if applicable)
'''

CONSTR = 'DRIVER={driver};DATABASE={db};UID={user};PWD={pwd};SERVER={server}'
DRIVERS = {
    'mysql': '{MySQL ODBC 8.0 Unicode Driver}',
    'mssql': '{FreeTDS}',
}


@contextmanager
def connect(connection_string, autocommit=True):
    """
    Connect to a database with the given connection string and yield a valid
    cursor to be used in a context.
    """
    with pyodbc.connect(connection_string, autocommit=autocommit) as conn:
        with conn.cursor() as cursor:
            yield cursor


def row_to_dict(row):
    """
    Convert a pyodbc Row object to a dictionary.
    """
    return dict(zip([t[0] for t in row.cursor_description], row))


def run_query(query, values, config):
    """
    Execute the query with the specified config dictionary.
    """
    conn_str = CONSTR.format(**config)
    results = []
    modified = False
    with connect(conn_str) as cur:
        cur.execute(query, *values)
        try:
            # Will raise an exception if the query doesn't return results
            results = list(map(row_to_dict, cur.fetchall()))
            modified = False
        except pyodbc.Error:
            results = []
            modified = cur.rowcount > 0
    return results, modified


def get_config(module):
    """
    Parse the configuration received by the module. Create the necessary
    mappings and fail if any argument is missing.
    """
    result = dict(changed=False, output='')
    config = module.params.get('config', None) or {}
    config = config.copy()
    mapping = {
        'username': 'user',
        'password': 'pwd',
        'database': 'db',
        'servername': 'server',
        'dbtype': 'driver',
    }
    for k, v in mapping.items():
        if k in config:
            config[v] = config.pop(k)
        if module.params.get(k, None):
            config[v] = module.params[k]

    # Find missing or empty configuration values
    r_mapping = {v: k for k, v in mapping.items()}
    missing = [r_mapping[k] for k in r_mapping if not config.get(k, '')]
    if missing:
        result['output'] = str(config)
        result['msg'] = 'Missing configuration parameters: {}'.format(missing)
        module.fail_json(**result)

    if config['driver'].lower() not in DRIVERS:
        result['msg'] = 'DB type must be one of {}'.format(list(DRIVERS))
        module.fail_json(**result)
    config['driver'] = DRIVERS[config['driver'].lower()]
    return config



def run_module():
    # define available arguments/parameters a user can pass to the module
    module_args = dict(
        config=dict(type='dict', required=False),
        servername=dict(type='str', required=False),
        database=dict(type='str', required=False),
        username=dict(type='str', required=False),
        password=dict(type='str', required=False),
        dbtype=dict(type='str', required=False),
        query=dict(type='str', required=True),
        values=dict(type='list', required=False, default=[]),
    )

    result = dict(changed=False, output='')

    # the AnsibleModule object will be our abstraction working with Ansible
    # this includes instantiation, a couple of common attr would be the
    # args/params passed to the execution, as well as if the module
    # supports check mode
    module = AnsibleModule(
        argument_spec=module_args, supports_check_mode=False
    )

    # if the user is working with this module in only check mode we do not
    # want to make any changes to the environment, just return the current
    # state with no modifications
    # if module.check_mode:
    #     return result

    config = get_config(module)
    try:
        query, values = module.params['query'], module.params['values']
        results, modified = run_query(query, values, config)
    except Exception as e:
        msg = '{}: {}'.format(type(e), str(e))
        module.fail_json(msg=msg, **result)

    result['changed'] = modified
    result['output'] = results

    # in the event of a successful module execution, you will want to
    # simple AnsibleModule.exit_json(), passing the key/value results
    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
