import json

from django_rollback.management.base import BaseRollbackCommand
from django_rollback.models import AppsState


class Command(BaseRollbackCommand):
    help = 'Save migrations state for current commit. It also check if commit already exists and ' \
           'print warning if it`s not the latest state that may be a symptom of inconsistent state for migrations.'

    def handle(self, *args, **options):
        self.configure_logger(options)

        commit = self.get_current_commit(path=options['path'])
        state_data = self.get_current_migrations_state()

        obj, created = AppsState.objects.get_or_create(commit=commit, defaults={'migrations': json.dumps(state_data)})
        last_state = self.get_last_apps_state()
        if created:
            message = f'Data = {state_data}.\n Successfully created for commit "{commit}".'
            self.stdout.write(self.style.SUCCESS(message))
            if self._logger:
                self._logger.info(message)

        else:
            if commit == last_state.commit:
                message = (f'State for current commit "{commit}" already exists with data:\n'
                           f'{last_state.migrations}\nCreated {obj.timestamp}\n'
                           f'This is the latest state for this service. So all is fine.')
                self.stdout.write(self.style.SUCCESS(message))
                if self._logger:
                    self._logger.info(message)

            else:
                message = (f'State for current commit "{commit}" already exists.\n'
                           f'Created {obj.timestamp}\n'
                           f'This is NOT the latest state for this service.\n'
                           f'Latest: commit "{last_state.commit}", created {last_state.timestamp}.\n'
                           f'Did you forget to perform rollback before changing service version?\n'
                           f'So migrations may be in inconsistent state, please check it!')
                self.stdout.write(self.style.WARNING(message))
                if self._logger:
                    self._logger.warning(message)
