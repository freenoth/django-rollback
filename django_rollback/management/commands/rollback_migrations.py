import git
from django.core.management.base import CommandError

from django_rollback.management.base import BaseRollbackCommand
from django_rollback.models import AppsState


class Command(BaseRollbackCommand):
    help = 'Rollback migrations state of all django apps to chosen tag or commit if previously saved. ' \
           'Also you may not specify commit or tag to rollback, so the previous tag will be used. ' \
           'Also it can run in fake mode, only to print generated commands for rollback. ' \
           'You also can view current DB state for all saved states using list argument.'

    def add_arguments(self, parser):
        super().add_arguments(parser)

        parser.add_argument('--list', action='store_true', help='Show the sorted list of all stored states.')
        parser.add_argument('-t', '--tag', type=str, help='Git tag to which to rollback migrations.')
        parser.add_argument('-c', '--commit', type=str, help='Git commit hash to which to rollback migrations.')
        parser.add_argument('--fake', action='store_true',
                            help='It allow to only print info about processed actions without execution '
                                 '(no changes for DB).')

    def validate_arguments(self, options):
        list_arg = options['list']
        tag_arg = options['tag']
        commit_arg = options['commit']
        fake_arg = options['fake']

        if list_arg and (tag_arg is not None or commit_arg is not None or fake_arg):
            message = f'--list arg should be used without git args (tag, commit or fake).'
            if self._logger:
                self._logger.warning(message)
            raise CommandError(message)

        if tag_arg is not None and commit_arg is not None:
            message = f'tag and commit args can not used together.'
            if self._logger:
                self._logger.warning(message)
            raise CommandError(message)

    def validate_current_commit(self, commit):
        """
        current commit should be the last commit in DB, otherwise it the migrations state is in inconsistent state,
        so we can`t run rollback because it may be wrong and it can brake DB state
        """
        last_state = self.get_last_apps_state()
        if not last_state:
            message = f'There is no saved states in DB. Rollback procedure impossible.'
            if self._logger:
                self._logger.warning(message)
            raise CommandError(message)

        if last_state.commit != commit:
            message = f'Current commit is not the latest in DB. Migrations state may be in inconsistent state. ' \
                      f'Rollback procedure impossible.'
            if self._logger:
                self._logger.warning(message)
            raise CommandError(message)

    def handle(self, *args, **options):
        self.configure_logger(options)
        self.validate_arguments(options)

        if options['list']:
            return self.print_states_list(path=options['path'])

        current_commit = self.get_current_commit(path=options['path'])
        self.validate_current_commit(current_commit)

        other_commit = self.get_other_commit(options, path=options['path'])
        if not other_commit:
            other_commit = self.get_previous_commit()

        current_data = self.get_migrations_data_by_commit(current_commit)
        other_data = self.get_migrations_data_by_commit(other_commit)

        diff = self.get_migrations_diff(current=current_data, other=other_data)

        message = f'Running rollback from commit "{current_commit}" to commit "{other_commit}".'
        self.stdout.write(message)
        if self._logger:
            self._logger.info(message)

        self.run_rollback(diff, fake=options['fake'])
        if not options['fake']:
            self.make_the_last_state_for_commit(other_commit)

        self.stdout.write(self.style.SUCCESS('Rollback successfully finished.'))

    def get_other_commit(self, options, path):
        commit_arg = options['commit']
        tag_arg = options['tag']

        if commit_arg:
            return commit_arg

        if tag_arg:
            try:
                repo = git.Repo(path)
                if tag_arg not in repo.tags:
                    message = f'Can not find tag `{tag_arg}` in git repository.'
                    if self._logger:
                        self._logger.warning(message)
                    raise CommandError(message)

                return repo.tags[tag_arg].commit.hexsha

            except CommandError as err:
                raise err

            except Exception as err:
                message = f'An error occurred while working with git repo!'
                self.stdout.write(self.style.ERROR(message))
                if self._logger:
                    self._logger.error(message + f'\n{__name__}')
                raise CommandError(err)

        return None

    def get_previous_commit(self):
        """
        current commit should be already validated
        so we are sure that the last state linked to current commit
        need to select previous commit
        """

        if AppsState.objects.count() < 2:
            message = f'There is only one state in DB. Can`t identify previous state. Rollback procedure impossible.'
            if self._logger:
                self._logger.warning(message)
            raise CommandError(message)

        return AppsState.objects.all().order_by('-timestamp')[1].commit

    def get_repo_tags(self, path):
        try:
            repo = git.Repo(path)
            result = {}
            for tag in repo.tags:
                result.setdefault(tag.commit.hexsha, [])
                result[tag.commit.hexsha].append(tag.name)

            return result

        except Exception:
            message = f'An error occurred while working with git repo during getting Tags map.'
            self.stdout.write(self.style.WARNING(message))
            if self._logger:
                self._logger.error(message + f'\n{__name__}')
            return {}

    def print_states_list(self, path):
        format_string = '{:>8}  {:<20}   {:<40}   {}'  # timestamp commit tag

        tags = self.get_repo_tags(path=path)
        current_commit = self.get_current_commit(path=path)

        self.stdout.write(f'Saved states in database sorted from newer to older:')
        self.stdout.write(format_string.format('MARK    ', 'TIMESTAMP v', 'COMMIT', 'TAGS'))

        queryset = AppsState.objects.all().order_by('-timestamp')
        for state in queryset:
            current_mark = 'curr >>>' if state.commit == current_commit else ''
            commit_tags = sorted(tags.get(state.commit, []), reverse=True)
            commit_tags = ', '.join(commit_tags) if commit_tags else ''
            self.stdout.write(
                f'{format_string.format(current_mark, str(state.timestamp)[:19], state.commit, commit_tags)}'
            )
