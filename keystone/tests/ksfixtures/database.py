# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import functools
import os
import shutil

import fixtures

from keystone.common import sql
from keystone.common.sql import migration_helpers
from keystone import config
from keystone.openstack.common.db import options as db_options
from keystone.openstack.common.db.sqlalchemy import migration
from keystone import tests


CONF = config.CONF


def run_once(f):
    @functools.wraps(f)
    def wrapper():
        if not wrapper.already_ran:
            f()
            wrapper.already_ran = True
    wrapper.already_ran = False
    return wrapper


def _setup_database(extensions=None):
    if CONF.database.connection != tests.IN_MEM_DB_CONN_STRING:
        db = tests.dirs.tmp('test.db')
        pristine = tests.dirs.tmp('test.db.pristine')

        if os.path.exists(db):
            os.unlink(db)
        if not os.path.exists(pristine):
            migration.db_sync(sql.get_engine(),
                              migration_helpers.find_migrate_repo())
            for extension in (extensions or []):
                migration_helpers.sync_database_to_version(extension=extension)
            shutil.copyfile(db, pristine)
        else:
            shutil.copyfile(pristine, db)


@run_once
def _initialize_sql_session():
    # Make sure the DB is located in the correct location, in this case set
    # the default value, as this should be able to be overridden in some
    # test cases.
    db_options.set_defaults(
        sql_connection=tests.IN_MEM_DB_CONN_STRING,
        sqlite_db=tests.DEFAULT_TEST_DB_FILE)


@run_once
def _load_sqlalchemy_models():
    """Find all modules containing SQLAlchemy models and import them.

    This will create more consistent, deterministic test runs because the
    database schema will be predictable. The schema is created based on the
    models already imported. This can change during the course of a test run.
    If all models are imported ahead of time then the schema will always be
    the same.

    """
    keystone_root = os.path.normpath(os.path.join(
        os.path.dirname(__file__), '..', '..'))
    for root, dirs, files in os.walk(keystone_root):
        # NOTE(morganfainberg): Slice the keystone_root off the root to ensure
        # we do not end up with a module name like:
        # Users.home.openstack.keystone.assignment.backends.sql
        root = root[len(keystone_root):]
        if root.endswith('backends') and 'sql.py' in files:
            # The root will be prefixed with an instance of os.sep, which will
            # make the root after replacement '.<root>', the 'keystone' part
            # of the module path is always added to the front
            module_name = ('keystone.%s.sql' %
                           root.replace(os.sep, '.').lstrip('.'))
            __import__(module_name)


class Database(fixtures.Fixture):
    """A fixture for setting up and tearing down a database.

    """

    def __init__(self, extensions=None):
        super(Database, self).__init__()
        self._extensions = extensions
        _initialize_sql_session()
        _load_sqlalchemy_models()

    def setUp(self):
        super(Database, self).setUp()
        _setup_database(extensions=self._extensions)

        self.engine = sql.get_engine()
        sql.ModelBase.metadata.create_all(bind=self.engine)
        self.addCleanup(sql.cleanup)
        self.addCleanup(sql.ModelBase.metadata.drop_all, bind=self.engine)
