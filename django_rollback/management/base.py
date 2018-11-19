import io
import json
import logging
import traceback
from collections import namedtuple

import git
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils.encoding import force_str

from django_rollback.consts import DEFAULT_REPO_PATH, COMMIT_MAX_LENGTH, MIGRATE_COMMAND
from django_rollback.models import AppsState
from django_rollback.sql import MIGRATIONS_STATE_SQL

MigrationRecord = namedtuple('MigrationRecord', ['id', 'app', 'name'])


class BaseRollbackCommand(BaseCommand):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._repo_path = DEFAULT_REPO_PATH
        self._repo_tags = None
        self._commits_info = {}
        self._out = io.StringIO()
        self._logger = None
        self._result_log_level = logging.DEBUG

    def add_arguments(self, parser):
        parser.add_argument('-p', '--path', type=str, default=DEFAULT_REPO_PATH, help='Git repository path.')
        parser.add_argument('-l', '--logger', type=str, help='Logger name for logging.')
        parser.add_argument('--log-level', type=str, help='Log level for logging. INFO, DEBUG, etc.')

    def configure_repo_path(self, options):
        self._repo_path = options.get('path', DEFAULT_REPO_PATH)

    def configure_logger(self, options):
        if options['logger']:
            logger = logging.getLogger(options['logger'])

            log_level = logging.getLevelName(options['log_level'])
            if isinstance(log_level, int):
                logger.setLevel(log_level)

            self._logger = logger

    def add_log(self, message, style_func=None, ending='\n', log_level=logging.INFO, exc_info=False):
        if isinstance(message, str) and not message.endswith(ending):
            message += ending

        if style_func is None:
            style_func = lambda x: x

        if log_level > self._result_log_level:
            self._result_log_level = log_level

        if exc_info:
            message += traceback.format_exc()
            if not message.endswith(ending):
                message += ending

        self._out.write(force_str(style_func(message)))

    def write_log(self):
        message = self._out.getvalue()

        self.stdout.write(message)

        if self._logger:
            self._logger.log(self._result_log_level, message)

    def close_log(self):
        self._out.close()

    def handle(self, *args, **options):
        try:
            self.configure_repo_path(options)
            self.configure_logger(options)
            self._handle(*args, **options)

        finally:
            self.write_log()
            self.close_log()

    def _handle(self, *args, **options):
        raise NotImplementedError('subclasses of BaseRollbackCommand must provide a _handle() method')

    def get_current_commit(self):
        try:
            repo = git.Repo(self._repo_path)
            return repo.head.commit.hexsha
        except ValueError as err:
            self.add_log(f'An error occurred while working with git repo!', style_func=self.style.ERROR,
                         log_level=logging.ERROR, exc_info=True)
            raise CommandError(err)

    def get_previous_commit(self, raise_exception=True):
        """
        current commit should be already validated
        so we are sure that the last state linked to current commit
        need to select previous commit
        """

        if AppsState.objects.count() < 2:
            message = f'There is only one state in DB. Can`t identify previous state. Rollback procedure impossible.'
            self.add_log(message, style_func=self.style.ERROR, log_level=logging.WARNING)
            if raise_exception:
                raise CommandError()

            return None

        return AppsState.objects.all().order_by('-timestamp')[1].commit

    @property
    def repo_tags(self):
        if not self._repo_tags:
            try:
                repo = git.Repo(self._repo_path)
                result = {}
                for tag in repo.tags:
                    result.setdefault(tag.commit.hexsha, [])
                    result[tag.commit.hexsha].append(tag.name)

                self._repo_tags = result

            except Exception:
                message = f'An error occurred while working with git repo during getting Tags map.'
                self.add_log(message, style_func=self.style.WARNING)
                self._repo_tags = {}

        return self._repo_tags

    def get_commit_info(self, commit):
        if commit not in self._commits_info:
            self._commits_info[commit] = f'"{commit}" {self.repo_tags.get(commit, [])}'
        return self._commits_info[commit]

    @staticmethod
    def get_last_apps_state():
        return AppsState.objects.all().order_by('timestamp').last()

    @staticmethod
    def get_current_migrations_state():
        """
        return a data in format:
        [(<id> : int, <app> : str, <name> : str), ...]
        """
        with connection.cursor() as cursor:
            cursor.execute(MIGRATIONS_STATE_SQL)
            return cursor.fetchall()

    def get_apps_state_by_commit(self, commit):
        queryset = AppsState.objects.filter(commit__istartswith=commit)

        count = queryset.count()

        if count == 0:
            message = f'Cant find stored data of migrations state for commit {self.get_commit_info(commit)}.'
            self.add_log(message, style_func=self.style.ERROR, log_level=logging.WARNING)
            raise CommandError()

        if count > 1:
            is_short_commit = len(commit) < COMMIT_MAX_LENGTH
            message = (f'Found more than 1 ({count}) records for selected commit {self.get_commit_info(commit)}.'
                       f'{" Please clarify commit hash for more identity." if is_short_commit else ""}')
            self.add_log(message, style_func=self.style.ERROR, log_level=logging.WARNING)
            raise CommandError()

        return queryset.first()

    def search_commit(self, commit):
        apps_state = self.get_apps_state_by_commit(commit)
        return apps_state.commit

    def get_migrations_data_by_commit(self, commit):
        apps_state = self.get_apps_state_by_commit(commit)
        return json.loads(apps_state.migrations)

    def get_migrations_diff(self, current, other):
        """
        current and other has type list of tuples in format:
        [(<id> : int, <app> : str, <name> : str), ...]
        it gets from get_migrations_data_from_commit()

        :return list that indicates what migrations should be executed
        migration_id is useful to detect migration order (from higher to lower)
        [
            namedtuple('MigrationRecord', ['id', 'app', 'name']),
            ...
        ]
        """
        result = []

        current = [MigrationRecord(*rec) for rec in current]
        other = [MigrationRecord(*rec) for rec in other]
        other_apps = {migration.app for migration in other}

        # find what is changed in current relative to other
        diff = set(current) - set(other)
        for migration in diff:
            is_new_app = migration.app not in other_apps
            result.append(MigrationRecord(
                migration.id,
                migration.app,
                'zero' if is_new_app else list(filter(lambda x: x.app == migration.app, other))[0].name,
            ))

        if result:
            self.add_log(f'Found migrations diff. In case of rollback need migrate to:\n{result}',
                         log_level=logging.WARNING)
        else:
            self.add_log(f'Diff not found. There is no migrations to rollback.')
        return result

    def run_rollback(self, migrations_diff_records, fake=False):
        """
        migrations_diff_records: List[MigrationRecord], result of get_migrations_diff()
        sort all migrations by migration.id order from higher to lower and execute migrate command for them
        """

        if not migrations_diff_records:
            self.add_log('There is no migrations to rollback.')
            return

        for migration in sorted(migrations_diff_records, key=lambda r: int(r.id), reverse=True):
            execute_args = (MIGRATE_COMMAND, migration.app, migration.name)
            self.add_log(f'Executing command: `{" ".join(execute_args)}`' + (' (executing faked)' if fake else ''))
            if not fake:
                call_command(*execute_args, stdout=self._out)

    def make_the_last_state_for_commit(self, commit):
        apps_state = self.get_apps_state_by_commit(commit)
        AppsState.objects.filter(id__gt=apps_state.id).delete()
        self.add_log(f'state for commit {self.get_commit_info(commit)} now is the last state in DB')
