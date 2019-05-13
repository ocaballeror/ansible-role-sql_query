Run query
=========

Execute a SQL query on a database.

Supported database types (any reasonably recent version should work):
- MySQL (Tested versions 5 and 8)
- SQL Server (Tested 2012, 2014, 2016 and linux v17)

Requirements
------------

* UnixODBC and pyodbc must be installed.
* The FreeTDS driver is needed for SQL Server connections.
* The MySQL ODBC driver is needed for MySQL connections.

Role Variables
--------------

### Module parameters
- `config`: A dictionary with all the database configuration parameters
  described below

- `dsn`: Use a pre-defined DataSourceName in your odbc configuration

- `database`: Database name

- `dbtype`: Database technology
  (Choices: mssql, mysql)

- `password`: Database password

- `username`: User name

- `servername`: The hostname of the server to target
  note: For mssql servers, include the database instance as well

- `query`: The actual query to run

- `values`: List of variables to substitute in the query

- `delegate`: Specify the host to run the query from. Defaults to localhost.

The `config` dictionary can contain as many of the other database connection
parameters as you want. You can mix and match, but the arguments specified
separately (database, username, etc) will take preference over the ones inside
`config`.

Either way, all connnection parameters are, obviously, required.

### Output

This role sets two variables as output:

- `sql_query_output`: Contains all the information returned by the `sql_query`
  module
- `query_rows`: If the query returns results, contains the list of returned rows
  as `key=value` dictionaries


Notes
-----
**Important Note**
This role delegates the querying task to localhost by default. If you want to run it in the remote machine instead, make sure to set the `delegate` argument when invoking it. Keep in mind that you will need all the ODBC requirements installed on that machine for it to work.


Examples
----------------

```yml
# Run a simple query
- name: Execute query
  include_role:
    name: sql_query
  vars:
    servername: server.domain.com\instance
    database: db_test
    username: rbamouser\itsme
    password: My_AD_Password123
    dbtype: mssql
    query: 'delete from table where 1 = 1'

# Use a pre-defined DSN
- name: Use my DSN
  include_role:
    name: sql_query
  vars:
    dsn: some_server
    query: 'exec dbo.NukeAllTables @force=yes'
    # Username and password are still required
    username: root
    password: root

# Override any DSN preferences
- name: Override my DSN
  include_role:
    name: sql_query
  vars:
    dsn: some_server
    query: 'exec dbo.NukeAllTables @force=yes'
    username: root
    password: root
    # Override any parameters you want
    servername: server.domain.com\INST
    driver: CustomDriver

# Select data and print the result
- name: Select data
  include_role:
    name: sql_query
  vars:
    servername: mysql-server.domain.com
    database: db_test
    username: sa
    password: Passw0rd
    dbtype: mysql
    query: 'select * from table'

# This variable is created automatically by the role
- debug:
    var: query_rows

# Interpolate variables (recommended)
- name: Select with variable escaping
  include_role:
    name: sql_query
  vars:
    config: ...
    query: select * from table where col = ? or col = ?
    values:
      - "{{ variable1 }}"
      - "{{ variable2 }}"

# Run multiple queries with the same configuration
- name: Set config
  set_fact:
    config:
      servername: server.domain.com\instance
      database: db_test
      username: sa
      password: Passw0rd
      dbtype: mssql

- name: Execute query
  include_role:
    name: sql_query
  vars:
    config: "{{ config }}"
    query: 'insert into table values ("a")'

- name: Execute query
  include_role:
    name: sql_query
  vars:
    config: "{{ config }}"
    query: 'insert into table values ("b")'
```

License
-------

BSD

Author Information
------------------

Oscar Caballero `<ocaballeror@tutanota.com>`
