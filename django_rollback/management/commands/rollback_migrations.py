import json
from collections import namedtuple

import git
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from django_rollback.models import AppsState

DEFAULT_REPO_PATH = '.'
COMMIT_MAX_LENGTH = 40
MIGRATE_COMMAND = 'migrate'

MigrationRecord = namedtuple('MigrationRecord', ['id', 'app', 'name'])


class Command(BaseCommand):
    help = 'Rollback migrations state of all django apps to chosen tag or commit if previously saved.'

    def add_arguments(self, parser):
        parser.add_argument('-t', '--tag', type=str, help='Git tag to which to rollback migrations.')
        parser.add_argument('-c', '--commit', type=str, help='Git commit hash to which to rollback migrations.')
        parser.add_argument('-p', '--path', type=str, help='Git repository path.')
        parser.add_argument('--fake', action='store_true',
                            help='It allow to only print info about processed actions without execution '
                                 '(no changes for DB).')

    def handle(self, *args, **options):
        repo_path = options.get('path', DEFAULT_REPO_PATH)

        other_commit = self.get_commit_from_options(options, path=repo_path)
        current_commit = self.get_current_commit(path=repo_path)

        current_data = self.get_migrations_data_from_commit(current_commit)
        other_data = self.get_migrations_data_from_commit(other_commit)

        diff = self.get_migrations_diff(current=current_data, other=other_data)

        self.run_rollback(diff, fake=options['fake'])

        self.stdout.write(self.style.SUCCESS('Rollback successfully finished.'))

    def get_commit_from_options(self, options, path):
        if not options['tag'] and not options['commit']:
            raise CommandError('Tag or commit should be described by -t or -c arguments.')

        if options['tag'] and options['commit']:
            raise CommandError('Tag and commit arguments should not be described together.')

        if options['commit']:
            return options['commit']

        tag = options['tag']
        try:
            repo = git.Repo(path)
            if tag not in repo.tags:
                raise CommandError(f'Can not find tag `{tag}` in git repository.')

            return repo.tags[tag].commit.hexsha

        except CommandError as err:
            raise err

        except Exception as err:
            self.stdout.write(self.style.ERROR(f'WARNING: an error occurred while working with git repo!'))
            raise CommandError(err)

    def get_current_commit(self, path):
        try:
            repo = git.Repo(path)
            return repo.head.commit.hexsha

        except ValueError as err:
            self.stdout.write(self.style.ERROR(f'WARNING: an error occurred while working with git repo!'))
            raise CommandError(err)

    def get_migrations_data_from_commit(self, commit):
        queryset = AppsState.objects.filter(commit__istartswith=commit)

        count = queryset.count()

        if count == 0:
            raise CommandError(f'Can not find stored data of migrations state for commit `{commit}`.')

        if count > 1:
            is_short_commit = len(commit) < COMMIT_MAX_LENGTH
            raise CommandError(f'Found more than 1 ({count}) records for selected commit {commit}.'
                               f'{" Please clarify commit hash for more identity." if is_short_commit else ""}')

        instance = queryset.first()
        return json.loads(instance.migrations)

    def get_migrations_diff(self, current, other):
        """
        current and other is type of list of tuples in format:
        [(<id> : int, <app> : str, <name> : str), ...]

        :return dict that indicates what migrations should be executed
        migration_id is useful to detect migration order (from higher to lower)
        {
            <migration_id>: <migrate command args>
        }
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

        return result

    def run_rollback(self, migrations_diff_records, fake=False):
        """
        sort all migrations by migration.id order from higher to lower and execute migrate command for them
        """

        if not migrations_diff_records:
            self.stdout.write(f'>>> There is no migrations to rollback.')
            return

        for migration in sorted(migrations_diff_records, key=lambda r: int(r.id), reverse=True):
            execute_args = (MIGRATE_COMMAND, migration.app, migration.name)
            self.stdout.write(f'>>> Executing command: {" ".join(execute_args)}')

            if not fake:
                call_command(*execute_args)
