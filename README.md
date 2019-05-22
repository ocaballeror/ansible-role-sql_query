Run query
=========

Execute a SQL query on a database.

Supported database types (any reasonably recent version should work):
- MySQL (Tested versions 5 and 8)
- SQL Server (Tested 2012, 2014, 2016 and linux v17)
- Oracle (experimental. Only version 18 tested)

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

- `odbc_opts`: Extra odbc options to include in the connection string

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
This role delegates the querying task to localhost by default. If you want to
run it in the remote machine instead, make sure to set the `delegate` argument
when invoking it. Keep in mind that you will need all the ODBC requirements
installed on that machine for it to work.

FAQ
---
##### What databases are supported?
Right now, only MySQL, SQL Server and Oracle (experimental)

##### I want to run this locally
If you want to run this role locally you will need these packages from your
distro's repos:
* CentOS / RedHat
  * unixODBC-devel
  * freetds-devel (for SQL server)
  * mysql-connector-odbc (for MySQL)
* Debian / Ubuntu
  * unixodbc-dev
  * tdsodbc (for SQL server)
  * libmyodbc (download from MySQL's website)

For Oracle support you will need to install the instantclient driver from
[Oracle's website](https://www.oracle.com/technetwork/database/database-technologies/instant-client/downloads/index.html)

Then you you must install `pyodbc` using pip. It is important that you do this
AFTER installing the odbc binaries or pip will fail.

If you are having trouble connecting to SQL Server databases with your
ActiveDirectory user, find a newer package or compile freetds from source.
Older versions won't work well for this case, especially before v1.0.

##### How do I avoid SQL injections?
Do not use ansible's string interpolation for your SQL queries. Instead, put a
`?` wherever you want to substitute a variable, and then pass the list of
values with the `values: ` keyword. So instead of this:
```yml
...
  query: "select * from users where name={{ username }}"
```
use this:
```yml
...
  query: "select * from users where name=?"
  values:
    - "{{ username }}"
```

##### How can I run queries in an ansible loop?
Unfortunately, as of version 2.7, ansible doesn't support including roles in a
loop. For performance reasons, I suggest you rethink your query and see if you
can use SQL cursors to do everything with a single role include.

If you find that confusing or you really need to run queries in an ansible
loop, you will need to invoke the `sql_query` module directly, instead of
including the role. Here's an example:
```yml
- name: Insert multiple things
  delegate_to: localhost  # This is important!
  sql_query:
    servername: ...
    # username, pasword and all that
    query: 'insert into table values (?)'
  loop:
    - value1
    - value2
    - value3
```

Keep in mind that, by invoking the module directly you lose the `query_rows`
variable, and you will need to manually `register: ` the result yourself. Also,
don't forget to `delegate_to: localhost` to run the actual module code in your
local machine instead of the remote server.

##### Can I use a custom ODBC DSN?
Yes, just use the `dsn:` argument. There is no need to specify dbtype,
servername or any other parameters that you may have defined in your
`odbcinst.ini`.

##### I want to pass extra ODBC options
Of course. Just use the `odbc_opts` argument to pass a dictionary with any
extra ODBC parameters. They will all be appended to the connection string in
the end.

Examples
----------------
Here's a list of complete invocation examples, for all your copying and pasting needs.
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
```

License
-------

BSD

Author Information
------------------

Oscar Caballero `<ocaballeror@tutanota.com>`
