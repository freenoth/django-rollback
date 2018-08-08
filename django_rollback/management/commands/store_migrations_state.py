import json

import git
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from django_rollback.models import AppsState
from django_rollback.sql import MIGRATIONS_STATE_SQL


class Command(BaseCommand):
    help = 'Store migrations state for current commit.'

    def handle(self, *args, **options):
        commit = self.get_current_commit()
        state_data = self.get_current_migrations_state()

        obj, created = AppsState.objects.update_or_create(commit=commit,
                                                          defaults={'migrations': json.dumps(state_data)})

        self.stdout.write(self.style.SUCCESS(f'Data = {state_data}.\n'
                                             f'Successfully {"created" if created else "updated"} '
                                             f'for commit "{commit}".\n'))

    def get_current_commit(self):
        try:
            repo = git.Repo('.')
            return repo.head.commit.hexsha
        except ValueError as err:
            self.stdout.write(self.style.ERROR(f'WARNING: an error occurred while working with git repo!'))
            raise CommandError(err)

    @staticmethod
    def get_current_migrations_state():
        """
        return a data in format:
        [(<id> : int, <app> : str, <name> : str), ...]
        """
        with connection.cursor() as cursor:
            return cursor.execute(MIGRATIONS_STATE_SQL).fetchall()
