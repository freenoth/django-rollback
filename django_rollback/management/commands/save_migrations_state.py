import json
import logging

from django_rollback.management.base import BaseRollbackCommand
from django_rollback.models import AppsState


class Command(BaseRollbackCommand):
    help = 'Save migrations state for current commit. It also check if commit already exists and ' \
           'print warning if it`s not the latest state that may be a symptom of inconsistent state for migrations.'

    def add_arguments(self, parser):
        super().add_arguments(parser)

        parser.add_argument('--log-full-data', action='store_true',
                            help='Log full data for migrations state when created.')
        parser.add_argument('--log-diff', action='store_true', help='Log current diff for current and previous state.')

    def _handle(self, *args, **options):
        commit = self.get_current_commit()
        state_data = self.get_current_migrations_state()

        obj, created = AppsState.objects.get_or_create(commit=commit, defaults={'migrations': json.dumps(state_data)})
        last_state = self.get_last_apps_state()
        if created:
            message = f'State successfully created for commit {self.get_commit_info(commit)}.'
            if options['log_full_data']:
                message += f'\nData = {state_data}'
            self.add_log(message, style_func=self.style.SUCCESS)

        else:
            if commit == last_state.commit:
                message = (f'State for current commit {self.get_commit_info(commit)} already exists. '
                           f'Created {obj.timestamp}\n'
                           f'This is the latest state for this service. So all is fine.'
                           )
                if options['log_full_data']:
                    message += f'\nData = {last_state.migrations}'
                self.add_log(message, style_func=self.style.SUCCESS)

            else:
                message = (
                    f'State for current commit {self.get_commit_info(commit)} already exists. Created {obj.timestamp}\n'
                    f'This is NOT the latest state for this service.\n'
                    f'Latest: commit {self.get_commit_info(last_state.commit)}, created {last_state.timestamp}.\n'
                    f'Did you forget to perform rollback before changing service version? '
                    f'So migrations may be in inconsistent state, please check it!'
                )
                self.add_log(message, style_func=self.style.WARNING, log_level=logging.WARNING)

        if options['log_diff']:
            other_commit = self.get_previous_commit(raise_exception=False)  # it will log if only one state in DB
            if other_commit:
                other_data = self.get_migrations_data_by_commit(other_commit)
                self.get_migrations_diff(current=state_data, other=other_data)  # it has diff log inside
