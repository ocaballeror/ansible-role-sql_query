#!/usr/bin/python
from contextlib import contextmanager

import pyodbc
from ansible.module_utils.basic import AnsibleModule


ANSIBLE_METADATA = {'metadata_version': '1.0', 'status': ['stableinterface']}

DOCUMENTATION = '''
---
module: run_query

short_description: Set maintenance mode on a target server.

version_added: "2.4"

description:
    - Execute a query on a database

options:
    servername:
        description:
            - The hostname of the server to target
        notes:
            - For mssql servers, include the database instance as well
        required: true
    database:
        description:
            - Database name
        required: true
    user:
        description: User name
        required: true
    password:
        description: Database password
        required: true
    dbtype:
        description: Database technology
        choices:
            - mssql
            - mysql
    query:
        description: The actual query to run
        required: true

notes:
    - Needs the odbc binary to be installed
    - Needs the appropriate drivers for each database type
    - Needs the pyodbc python package

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
  run_query:
    servername: mysql-server.domain.com
    database: db_test
    username: sa
    password: Passw0rd
    dbtype: mysql
    query: 'select * from table'
  register: query_output
'''

RETURN = '''
output:
    description: Query results (if applicable)
'''

CONSTR = 'DRIVER={driver};DATABASE={db};UID={user};PWD={pwd};SERVER={server}'
DBTYPES = ['mssql', 'mysql']


@contextmanager
def connect(connection_string, autocommit=True):
    """
    Connect to a database with the given connection string and yield a valid
    cursor to be used in a context.
    """
    with pyodbc.connect(connection_string, autocommit=autocommit) as conn:
        with conn.cursor() as cursor:
            yield cursor


def run_query(query, config):
    """
    Execute the query with the specified config dictionary.
    """
    conn_str = CONSTR.format(**config)
    results = []
    modified = False
    with connect(conn_str) as cur:
        res = cur.execute(query)
        # modify operations return the number of modifications in "rowcount",
        # but will raise on .fetchall(). read operations return rowcount = -1,
        # and the results with .fetchall()
        if res.rowcount == -1:
            results = res.fetchall()
        else:
            modified = res.rowcount > 0
    return results, modified


def run_module():
    # define available arguments/parameters a user can pass to the module
    module_args = dict(
        servername=dict(type='str', required=True),
        database=dict(type='str', required=True),
        username=dict(type='str', required=True),
        password=dict(type='str', required=True),
        dbtype=dict(type='str', required=True),
        query=dict(type='str', required=True),
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

    # manipulate or modify the state as needed (this is going to be the
    # part where your module will do what it needs to do)
    if module.params['dbtype'].lower() not in DBTYPES:
        result['msg'] = 'DB type must be one of ' + str(DBTYPES)
        module.fail_json(**result)

    config = {
        'user': module.params['username'],
        'pwd': module.params['password'],
        'db': module.params['database'],
        'server': module.params['servername'],
        'dbtype': module.params['dbtype'],
    }
    try:
        results, modified = run_query(module.params['query'], config)
    except Exception as e:
        msg = '{}: {}'.format(type(e), str(e))
        module.fail_json(msg=msg, **result)

    result['changed'] = modified
    result['output'] = '\n'.join(results)

    # in the event of a successful module execution, you will want to
    # simple AnsibleModule.exit_json(), passing the key/value results
    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
