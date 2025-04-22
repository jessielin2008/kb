# Implementing RBAC on 23.2 using Default Privileges

[**Introduction**](#introduction)	**[0](#introduction)**

[**Implementation Overview**](#implementation-overview)	**[0](#implementation-overview)**

[Default Privileges](#default-privileges)	[0](#default-privileges)

[Example Default Privileges Implementation](#example-default-privileges-implementation)	[1](#example-default-privileges-implementation)

[Additional considerations](#additional-considerations)	[6](#additional-considerations)

# 

# Revision Notes

| Release | Contents | Author | Date |
| :---- | :---- | :---- | :---- |
| 23.2 | Refine ownership & access for public schema | Jessie Lin | 04/16/2024 |
| 22.1 | Refine access for public | Jessie Lin | 03/09/2023 |
| 21.2 | Migrating to Default Privilege | Matt Gardner | ‘2021 |

# Introduction {#introduction}

This document aims to give an example to implement RBAC ( role based access control) on databases  using  default privileges.  This document is an update on the previous “Migration to 22.1 Privilege” document. It targets new customers and the implementation sets more restricted access to readonly and unauthorized users.

# Implementation Overview {#implementation-overview}

## Default Privileges {#default-privileges}

The key part is to understand that they apply only objects created by a specific user or role, this will in fact be a migration to a roles based access model. In this document, an example implementation will be shown that will provide a similar but different experience as seen with grants at the database level.

For the example implementation, there will be 3 custom roles in addition to the admin role in CRDB

* Admin role. This role is used to create users, roles, database objects. Ownership of database will be transferred to db\_owner later.  
* db\_owner. This role will only be used for altering privileges, creation of databases/tables  and ownership of the objects. The primary driver for the creation of this role is to prevent users from granting access via default privileges, avoiding access management policies and  therefore preventing propagation of privileges.   
* db\_readwrite. This role will be used to read/write to tables.  
* db\_readonly. This role will be used to read tables.

Caveats:

* Users/roles cannot be dropped until all default privileges are revoked.  
* The db\_readwrite role will no longer be able to create tables or change zone configurations.  
* Public/unauthorized users will no longer be able to view objects ( custom schema, tables, types )  
* Users will need to set their role to db\_owner before creating tables. This will ensure that the tables are in fact owned by the role db\_owner. Tables that are not owned by db\_owner, cannot be interacted with by users that have been granted the db\_readwrite or db\_readonly roles.   
1. **SET ROLE db\_owner;**  
2. **CREATE TABLE my\_table ( key string);**

Gotchas:

* **USE database;**  When granting default  privileges for a given database, it is necessary to **USE db;** before running the **ALTER DEFAULT PRIVILEGES** statement. This ensures that the privileges are only granted for the current database.  
* **ALTER DEFAULT PRIVILEGES** will only apply to objects created **after** the command has been executed. Any tables created before execution, will not be accessible to users **ALTER DEFAULT PRIVILEGES** have been executed.  Therefore it's important to provide default privileges, before users create tables.   
* **GRANT CONNECT ON DATABASE** must be executed for all users to run commands such as **SHOW TABLES.**

### Example Default Privileges Implementation {#example-default-privileges-implementation}

Below, is an example implementation where the roles as suggested above will be created. The  statements shown in the example below have been verified against 22.1.16.

In this example:

* lin with admin role  
* Albert with role db\_test\_owner  
* Elise with role db\_test\_readwrite  
* Rick with role db\_test\_readonly  
* Jessie with no role assigned  
* Database name will be db\_test

Setup:  
\# login as a user lin  w/ Admin role  
./cockroach sql  
\> show role;  
  role  
\--------  
  none  
(1 row)

lin@\<cluster\>:26257/defaultdb\> create user albert with password ‘albert’;  
lin@\<cluster\>:26257/defaultdb\> create user appuser with password 'application';  
lin@\<cluster\>:26257/defaultdb\> create user rick with password ‘rick’;  
lin@\<cluster\>:26257/defaultdb\>create user jessie with password  'jessie';

Create Roles and grant them to the applicable users :  
lin@\<cluster\>:26257/defaultdb\> create role db\_test\_owner;  
lin@\<cluster\>:26257/defaultdb\> create role db\_test\_readwrite;  
lin@\<cluster\>:26257/defaultdb\> create role db\_test\_readonly;

lin@\<cluster\>:26257/defaultdb\> grant db\_test\_owner to albert;  
lin@\<cluster\>:26257/defaultdb\> grant db\_test\_readwrite to appuser;  
lin@\<cluster\>:26257/defaultdb\> grant db\_test\_readonly to rick;

\# validate users and roles granted  
lin@\<cluster\>:26257/defaultdb\>show users;  
      username      | options |      member\_of  
\--------------------+---------+----------------------  
  admin             |         | {}  
  appuser            |         | {db\_test\_readwrite}  
 backupper          |                                                      | {admin}  
  db\_test\_owner     | NOLOGIN | {}  
  db\_test\_readonly  | NOLOGIN | {}  
  db\_test\_readwrite | NOLOGIN | {}  
  jessie            |         | {}  
 lin            |         | {admin}  
 liquid            |         | {db\_test\_owner}  
 managed-db-console | CONTROLJOB, VIEWACTIVITYREDACTED, VIEWCLUSTERSETTING | {}  
 managed-service    |                                                      | {admin}  
 managed-sql-prober |                                                      | {admin}  
 rick              |         | {db\_test\_read\_only}  
 root              |         | {admin}  
(9 rows)  
\# before creating database, set role to admin  
\> set role admin;  
SET  
lin@\<cluster\>:26257/defaultdb\> create database db\_test;

lin@\<cluster\>:26257/defaultdb\> show databases;                                                                     
  database\_name | owner | primary\_region | secondary\_region | regions | survival\_goal  
\----------------+-------+----------------+------------------+---------+----------------  
  db\_test       | admin | NULL           | NULL             | {}      | NULL  
 defaultdb     | root  | NULL           | NULL             | {}      | NULL  
  postgres      | root  | NULL           | NULL             | {}      | NULL  
  system        | node  | NULL           | NULL             | {}      | NULL

\>use db\_test;  
lin@\<cluster\>:26257/db\_test\> show schemas;                                                                   
     schema\_name     | owner  
\---------------------+--------  
  crdb\_internal      | node  
  information\_schema | node  
  pg\_catalog         | node  
  pg\_extension       | node  
  public             | admin  
(5 rows)

\# Prevent unauthorized users to see the database / tables in the database;  
lin@\<cluster\>:26257/db\_test\> show grants on database db\_test;   
 database\_name | grantee | privilege\_type | is\_grantable  
\----------------+---------+----------------+---------------  
 db\_ test          | admin   | ALL            |      t  
 db\_test          | public  | CONNECT        |      f  
 db\_test          | root    | ALL            |      t  
(3 rows)  
lin@\<cluster\>:26257/db\_test\>revoke all on database db\_test from public;

\# Prevent unauthorized users to create objects in/ use public schema  
\# Due to postgres compatibility, public has CREATE & USAGE on public schema  
\# Can change cluster setting sql.auth.public\_schema\_create\_privilege.enabled to avoid giving public role CREATE privilege on public schema  
lin@\<cluster\>:26257/db\_test\> show grants on schema db\_test.public;                                                
  database\_name | schema\_name | grantee | privilege\_type | is\_grantable  
\----------------+-------------+---------+----------------+---------------  
  db\_test     | public      | admin   | ALL            |      t  
  db\_test     | public      | public  | CREATE         |      f  
  db\_test     | public      | public  | USAGE          |      f  
  db\_test     | public      | root    | ALL            |      t  
(4 rows)

lin@\<cluster\>:26257/db\_test\>revoke all on schema db\_test.public from public;

\# Change owner from admin to db\_test\_owner  
lin@\<cluster\>:26257/db\_test\> alter database db\_test owner to db\_test\_owner;

\# Change owner from admin to db\_test owner   
lin@\<cluster\>:26257/db\_test\>alter schema db\_test.public owner to db\_test\_owner;

The user Albert with the db\_test\_owner role will now alter default privileges for read write and read only roles:

albert@\<cluster\>:26257/defaultdb\>set role db\_test\_owner;  
albert@\<cluster\>:26257/defaultdb\>use db\_test;  
albert@\<cluster\>:26257/defaultdb\>show default privileges;  
     role      | for\_all\_roles | object\_type |    grantee    | privilege\_type | is\_grantable  
\----------------+---------------+-------------+---------------+----------------+---------------  
  db\_test\_owner |       f       | routines    | db\_test\_owner | ALL            |      t  
  db\_test\_owner |       f       | routines    | public        | EXECUTE        |      f  
  db\_test\_owner |       f       | schemas     | db\_test\_owner | ALL            |      t  
  db\_test\_owner |       f       | sequences   | db\_test\_owner | ALL            |      t  
  db\_test\_owner |       f       | tables      | db\_test\_owner | ALL            |      t  
  db\_test\_owner |       f       | types       | db\_test\_owner | ALL            |      t  
  db\_test\_owner |       f       | types       | public        | USAGE          |      f  
(7 rows)

\# Readwrite role  
albert@\<cluster\>:26257/db\_test\> grant connect on database db\_test to db\_test\_readwrite;  
\# if plan to use public schema, grant connect. It’s created at database creation time, default privilege doesn’t apply  
albert@\<cluster\>:26257/db\_test\> grant usage on schema public to db\_test\_readwrite;  
\# if plan to use custom schema   
albert@\<cluster\>:26257/db\_test\> ALTER DEFAULT PRIVILEGES FOR ROLE db\_test\_owner  GRANT USAGE ON SCHEMAS TO db\_test\_readwrite;  
albert@\<cluster\>:26257/db\_test\> ALTER DEFAULT PRIVILEGES FOR ROLE db\_test\_owner  GRANT SELECT,INSERT,UPDATE,DELETE ON TABLES TO db\_test\_readwrite;  
albert@\<cluster\>:26257/db\_test\> ALTER DEFAULT PRIVILEGES FOR ROLE db\_test\_owner  GRANT SELECT,UPDATE ON SEQUENCES TO db\_test\_readwrite;

\# prevent unauthorized users to use TYPES & FUNCTIONS created by db\_test\_owner  
albert@\<cluster\>:26257/db\_test\>ALTER DEFAULT PRIVILEGES FOR ROLE db\_test\_owner REVOKE USAGE ON TYPES FROM public;  
albert@\<cluster\>:26257/db\_test\> ALTER DEFAULT PRIVILEGES FOR ROLE db\_test\_owner  GRANT USAGE  ON TYPES TO db\_test\_readwrite;

\# prevent unauthorized users to execute functions and procedures  
albert@\<cluster\>:26257/db\_test\> ALTER DEFAULT PRIVILEGES FOR ROLE  db\_test\_owner REVOKE EXECUTE ON FUNCTIONS from  public;  
albert@\<cluster\>:26257/db\_test\> ALTER DEFAULT PRIVILEGES FOR ROLE  db\_test\_owner GRANT EXECUTE ON FUNCTIONS TO  db\_test\_readwrite;

\# Readonly role  
albert@\<cluster\>:26257/db\_test\> grant connect on database db\_test to db\_test\_readonly;  
albert@\<cluster\>:26257/db\_test\> grant usage on schema public to db\_test\_readonly;

albert@\<cluster\>:26257/db\_test\> ALTER DEFAULT PRIVILEGES FOR ROLE db\_test\_owner  GRANT USAGE ON SCHEMAS TO db\_test\_readonly;  
albert@\<cluster\>:26257/db\_test\> ALTER DEFAULT PRIVILEGES FOR ROLE db\_test\_owner  GRANT SELECT ON TABLES TO db\_test\_readonly;  
albert@\<cluster\>:26257/db\_test\> ALTER DEFAULT PRIVILEGES FOR ROLE db\_test\_owner  GRANT SELECT ON SEQUENCES TO db\_test\_readonly;  
albert@\<cluster\>:26257/db\_test\> ALTER DEFAULT PRIVILEGES FOR ROLE db\_test\_owner  GRANT USAGE  ON TYPES TO db\_test\_readonly;  
albert@\<cluster\>:26257/db\_test\> ALTER DEFAULT PRIVILEGES FOR ROLE db\_test\_owner  GRANT EXECUTE  ON FUNCTIONS TO db\_test\_readonly;

\# Validate the default privilege changes  
albert@\<cluster\>:26257/db\_test\> show default privileges;  
     role      | for\_all\_roles | object\_type |      grantee      | privilege\_type | is\_grantable  
\----------------+---------------+-------------+-------------------+----------------+---------------  
  db\_test\_owner |       f       | routines    | db\_test\_owner     | ALL            |      t  
  db\_test\_owner |       f       | routines    | db\_test\_readonly  | EXECUTE        |      f  
  db\_test\_owner |       f       | routines    | db\_test\_readwrite | EXECUTE        |      f  
  db\_test\_owner |       f       | schemas     | db\_test\_owner     | ALL            |      t  
  db\_test\_owner |       f       | schemas     | db\_test\_readonly  | USAGE          |      f  
  db\_test\_owner |       f       | schemas     | db\_test\_readwrite | USAGE          |      f  
  db\_test\_owner |       f       | sequences   | db\_test\_owner     | ALL            |      t  
  db\_test\_owner |       f       | sequences   | db\_test\_readonly  | SELECT         |      f  
  db\_test\_owner |       f       | sequences   | db\_test\_readwrite | SELECT         |      f  
  db\_test\_owner |       f       | sequences   | db\_test\_readwrite | UPDATE         |      f  
  db\_test\_owner |       f       | tables      | db\_test\_owner     | ALL            |      t  
  db\_test\_owner |       f       | tables      | db\_test\_readonly  | SELECT         |      f  
  db\_test\_owner |       f       | tables      | db\_test\_readwrite | DELETE         |      f  
  db\_test\_owner |       f       | tables      | db\_test\_readwrite | INSERT         |      f  
  db\_test\_owner |       f       | tables      | db\_test\_readwrite | SELECT         |      f  
  db\_test\_owner |       f       | tables      | db\_test\_readwrite | UPDATE         |      f  
  db\_test\_owner |       f       | types       | db\_test\_owner     | ALL            |      t  
  db\_test\_owner |       f       | types       | db\_test\_readonly  | USAGE          |      f  
  db\_test\_owner |       f       | types       | db\_test\_readwrite | USAGE          |      f  
(19 rows)

Now,  let's confirm the behavior of the default privileges by executing  SQL statements. 

Albert as db\_test\_owner will create a table, appuser (readwrite) will be able to select/insert data and  Rick (readonly) will be able to select.   
\#make sure to set role as db\_test\_owner before creating objects  
albert@\<cluster\>:26257/defaultdb\> set role db\_test\_owner;  
\# make sure objects are created in the same database  
albert@\<cluster\>:26257/defaultdb\> use db\_test;  
albert@\<cluster\>:26257/db\_test\> create schema test;  
albert@\<cluster\>:26257/db\_test\>create type test.status as enum ('open','closed');    
albert@\<cluster\>:26257/db\_test\> create table test.accounts(                                        
                                                       id UUID PRIMARY KEY DEFAULT gen\_random\_uuid(),  
                                                       balance DECIMAL,  
                                                       status test.status  
                                                   );  
albert@\<cluster\>:26257/db\_test\>insert into test.accounts (balance, status) values (500, 'open');  
INSERT 0 1

albert@\<cluster\>:26257/db\_test\>create sequence test.seq;  
abert@\<cluster\>:26257/db\_test\>select nextval('test.seq');  
  nextval  
\-----------  
        1  
(1 row)

albert@\<cluster\>:26257/db\_test\> create function test.insertfunc() returns uuid as $$ insert into test.accounts(balance, status)  values (100, ‘open’) returning id $$ language sql;                                                  
CREATE FUNCTION  
albert@\<cluster\>:26257/db\_test\>select insertfunc();  
              insertfunc  
\----------------------------------------  
  50b3fd1f-e76b-41e9-ad3c-5ce52f70a9c0  
(1 row)  
\# You can create type, table, sequence, and functions in public schema. It works the same.  
 Log in as appuser (readwrite), and appuser will be able to select/insert data../cockroach sql 

appuser@:26257/db\_test\> insert into test.accounts (balance, status) values (1000, 'closed');  
INSERT 0 1

appuser@\<cluster\>:26257/db\_test\>  select \* from test.accounts;  
                   id                  | balance | status  
\---------------------------------------+---------+---------  
  25680df0-96cb-46f2-a366-cb5c532ec84a |    1000 | closed  
  66b95ca2-4cce-4eba-87e1-bf8e4f3444d7 |     500 | open  
(2 rows)  
appuser@\<cluster\>:26257/db\_test\>SELECT nextval('test.seq');  
  nextval  
\-----------  
        2  
(1 row)

appuser@\<cluster\>:26257/db\_test\> select test.insertfunc();                                                                
               insertfunc  
\----------------------------------------  
  b6a6a26d-bbe5-48e1-a8e1-f44c88ff9ab1  
(1 row)

Log in as  Rick (readonly), and Rick will be able to select.   
\# Readonly user can’t insert.  
rick@\<cluster\>:26257/defaultdb\>  insert into test.accounts (balance, status) values (1500, 'closed');  
ERROR: user rick does not have INSERT privilege on relation accounts  
SQLSTATE: 42501

rick@\<cluster\>:26257/db\_test\> select \* from test.accounts;  
                   id                  | balance | status  
\---------------------------------------+---------+---------  
  25680df0-96cb-46f2-a366-cb5c532ec84a |    1000 | closed  
  66b95ca2-4cce-4eba-87e1-bf8e4f3444d7 |     500 | open  
(2 rows)

rick@\<cluster\>t:26257/db\_test\> select nextval('test.seq');  
ERROR: nextval(): user rick does not have UPDATE privilege on relation seq  
SQLSTATE: 42501

rick@\<cluster\>:26257/db\_test\> select \* from test.seq;  
  last\_value | log\_cnt | is\_called  
\-------------+---------+------------  
           2 |       0 |     t

rick@jessie-demo-n3r.aws-us-west-2.cockroachlabs.cloud:26257/db\_test\> select test.insertfunc();                                                                   
ERROR: user rick does not have INSERT privilege on relation accounts  
SQLSTATE: 42501

Log in as  Jessie unauthorized user and will not able to select. 

\# Unauthorized users cannot see objects in the database  
 jessie@\<cluster\>:26257/defaultdb\> show databases;  
  database\_name | owner | primary\_region | regions | survival\_goal  
\----------------+-------+----------------+---------+----------------  
  defaultdb     | root  | NULL           | {}      | NULL  
  postgres      | root  | NULL           | {}      | NULL  
(2 rows)  
\# See below regarding “improve CONNECT privilege”  
jessie@localhost:26257/defaultdb\> use db\_test;  
SET

jessie@localhost:26257/db\_test\> show schemas;  
     schema\_name     | owner  
\---------------------+--------  
  crdb\_internal      | NULL  
  information\_schema | NULL  
  pg\_catalog         | NULL  
  pg\_extension       | NULL  
(4 rows)

jessie@\<cluster\>:26257/db\_test\> show tables;  
SHOW TABLES 0  
jessie@\<cluster\>:26257/db\_test\> show sequences;  
SHOW SCHEMAS 0  
jessie@\<cluster\>:26257/db\_test\> show types;  
SHOW TYPES 0  
jessie@\<cluster\>:26257/db\_test\> show functions;                                                                           
SHOW FUNCTIONS 0

### Additional considerations {#additional-considerations}

**Grant db\_owner temporarily** \- After object creation, revoke the db\_owner role from users to prevent privilege scope creep. Without access to the db\_owner role, only superusers such as admin/root will be able to create tables and grant privileges to existing objects. None of the readwrite/readonly users would own tables and therefore without ownership or the db\_owner role, they won’t be able to alter privileges. The intention  is that in production, schema changes are not a regular occurrence and therefore strict control over ownership and the CREATE privilege shouldn’t hinder workloads. 

**Admin account and default privileges.** Admin accounts will be rejected from modifying default privileges  unless the set role statement is used.   
adminuser@:26257/db\_test\> ALTER DEFAULT PRIVILEGES FOR ROLE db\_test\_owner  GRANT SELECT ON TABLES TO db\_test\_readonly;  
ERROR: must be a member of db\_test\_owner  
SQLSTATE: 42501

adminuser@:26257/db\_test\> set role db\_test\_owner;  
SET

adminuser@:26257/db\_test\> ALTER DEFAULT PRIVILEGES FOR ROLE …  GRANT ALL  ON TABLES TO …;

**CREATE object by Public role**    
For compatibility with Postgres, public role has CREATE and USAGE privilege  in public schema. In 23.2 turning Cluster setting sql.auth.public\_schema\_create\_privilege.enabled to FALSE to remove CREATE privilege from public in public schema. 

**CONNECT grant** \- Below is an example when CONNECT grant isn’t given, users are prevented from performing metadata operations like show tables, but may be able to perform dml changes when given readonly/readwrite roles: 

appuser@\<cluster\>:26257/db\_test\> show tables;  
SHOW TABLES 0

admin@:26257/defaultdb\> grant connect on database db\_test to db\_test\_readwrite;

appuser@\<cluster\>:26257/db\_test\> show tables;  
  schema\_name | table\_name | type  |     owner     | estimated\_row\_count | locality  
\--------------+------------+-------+---------------+---------------------+-----------  
  public      | test1      | table | albert        |                   0 | NULL  
  public      | test2      | table | db\_test\_owner |                   0 | NULL

**Improve the CONNECT privilege**  
Another consideration is to improve the behavior of the CONNECT privilege, using this grant as a way to only allow users access to the database in the event they have been granting CONNECT, currently the behavior has diverged from postgres.   
[https://github.com/cockroachdb/cockroach/issues/59875](https://github.com/cockroachdb/cockroach/issues/59875)

Show default privilege for grantee   
[https://cockroachlabs.atlassian.net/browse/CRDB-25481](https://cockroachlabs.atlassian.net/browse/CRDB-25481)   
Search Path and Name Resolution  
[https://www.cockroachlabs.com/docs/v22.2/sql-name-resolution](https://www.cockroachlabs.com/docs/v22.2/sql-name-resolution) 