import json
import logging
from collections import namedtuple

import git
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from django_rollback.consts import DEFAULT_REPO_PATH, COMMIT_MAX_LENGTH, MIGRATE_COMMAND
from django_rollback.models import AppsState
from django_rollback.sql import MIGRATIONS_STATE_SQL

MigrationRecord = namedtuple('MigrationRecord', ['id', 'app', 'name'])


class BaseRollbackCommand(BaseCommand):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._logger = None

    def add_arguments(self, parser):
        parser.add_argument('-p', '--path', type=str, default=DEFAULT_REPO_PATH, help='Git repository path.')
        parser.add_argument('-l', '--logger', type=str, help='Logger name for logging.')
        parser.add_argument('--log-level', type=str, help='Log level for logging. INFO, DEBUG, etc.')

    def configure_logger(self, options):
        if options['logger']:
            logger = logging.getLogger(options['logger'])

            log_level = logging.getLevelName(options['log_level'])
            if isinstance(log_level, int):
                logger.setLevel(log_level)

            self._logger = logger

    def handle(self, *args, **options):
        raise NotImplemented

    def get_current_commit(self, path):
        try:
            repo = git.Repo(path)
            return repo.head.commit.hexsha
        except ValueError as err:
            message = f'An error occurred while working with git repo!'
            self.stdout.write(self.style.ERROR(message))
            if self._logger:
                self._logger.error(message + f'\n{__name__}')
            raise CommandError(err)

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
            message = f'Can not find stored data of migrations state for commit `{commit}`.'
            if self._logger:
                self._logger.warning(message)
            raise CommandError(message)

        if count > 1:
            is_short_commit = len(commit) < COMMIT_MAX_LENGTH
            message = (f'Found more than 1 ({count}) records for selected commit {commit}.'
                       f'{" Please clarify commit hash for more identity." if is_short_commit else ""}')
            if self._logger:
                self._logger.warning(message)
            raise CommandError(message)

        return queryset.first()

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

        if self._logger:
            self._logger.info(f'Migrations diff:\n{result}')

        return result

    def run_rollback(self, migrations_diff_records, fake=False):
        """
        migrations_diff_records: List[MigrationRecord], result of get_migrations_diff()
        sort all migrations by migration.id order from higher to lower and execute migrate command for them
        """

        if not migrations_diff_records:
            message = 'There is no migrations to rollback.'
            self.stdout.write(f'>>> {message}')
            if self._logger:
                self._logger.info(message)
            return

        for migration in sorted(migrations_diff_records, key=lambda r: int(r.id), reverse=True):
            execute_args = (MIGRATE_COMMAND, migration.app, migration.name)
            message = f'Executing command: {" ".join(execute_args)}'
            self.stdout.write(f'>>> {message}')
            if self._logger:
                self._logger.info(message)

            if not fake:
                call_command(*execute_args)

    def make_the_last_state_for_commit(self, commit):
        apps_state = self.get_apps_state_by_commit(commit)
        AppsState.objects.filter(id__gt=apps_state.id).delete()

        message = f'state for commit "{commit}" now is the last state in DB'
        self.stdout.write(f'>>> {message}')
        if self._logger:
            self._logger.info(message)
