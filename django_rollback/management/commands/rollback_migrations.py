import logging

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
            self.add_log(f'--list arg should be used without git args (tag, commit or fake).',
                         log_level=logging.ERROR)
            raise CommandError()

        if tag_arg is not None and commit_arg is not None:
            self.add_log(f'tag and commit args can not used together.', log_level=logging.ERROR)
            raise CommandError()

    def validate_current_commit(self, commit):
        """
        current commit should be the last commit in DB, otherwise it the migrations state is in inconsistent state,
        so we can`t run rollback because it may be wrong and it can brake DB state
        """
        last_state = self.get_last_apps_state()
        if not last_state:
            self.add_log(f'There is no saved states in DB. Rollback procedure impossible.', log_level=logging.ERROR)
            raise CommandError()

        if last_state.commit != commit:
            message = f'Current commit is not the latest in DB. Migrations state may be in inconsistent state. ' \
                      f'Rollback procedure impossible.'
            self.add_log(message, log_level=logging.ERROR)
            raise CommandError()

    def _handle(self, *args, **options):
        self.validate_arguments(options)

        if options['list']:
            return self.print_states_list()

        if options['fake']:
            self.add_log('Running rollback with --fake option.', style_func=self.style.WARNING,
                         log_level=logging.WARNING)

        current_commit = self.get_current_commit()
        self.validate_current_commit(current_commit)

        other_commit = self.get_other_commit(options)
        if not other_commit:
            other_commit = self.get_previous_commit()
        else:
            other_commit = self.search_commit(other_commit)

        current_data = self.get_migrations_data_by_commit(current_commit)
        other_data = self.get_migrations_data_by_commit(other_commit)

        diff = self.get_migrations_diff(current=current_data, other=other_data)

        self.add_log(f'Running rollback from commit {self.get_commit_info(current_commit)} '
                     f'to commit {self.get_commit_info(other_commit)}.')

        self.run_rollback(diff, fake=options['fake'])
        if not options['fake']:
            self.make_the_last_state_for_commit(other_commit)

        fake_msg = ' with `--fake` option' if options['fake'] else ''
        self.add_log(f'Rollback successfully finished{fake_msg}.', style_func=self.style.SUCCESS)

    def get_other_commit(self, options):
        commit_arg = options['commit']
        tag_arg = options['tag']

        if commit_arg:
            return commit_arg

        if tag_arg:
            try:
                repo = git.Repo(self._repo_path)
                if tag_arg not in repo.tags:
                    self.add_log(f'Can not find tag `{tag_arg}` in git repository.', log_level=logging.ERROR)
                    raise CommandError()

                return repo.tags[tag_arg].commit.hexsha

            except CommandError as err:
                raise err

            except Exception as err:
                self.add_log(f'An error occurred while working with git repo!', style_func=self.style.ERROR,
                             log_level=logging.ERROR, exc_info=True)
                raise CommandError(err)

        return None

    def print_states_list(self,):
        format_string = '{:>8}  {:<20}   {:<40}   {}'  # timestamp commit tag

        current_commit = self.get_current_commit()

        self.stdout.write(f'Saved states in database sorted from newer to older:')
        self.stdout.write(format_string.format('MARK    ', 'TIMESTAMP v', 'COMMIT', 'TAGS'))

        queryset = AppsState.objects.all().order_by('-timestamp')
        for state in queryset:
            current_mark = 'curr >>>' if state.commit == current_commit else ''
            commit_tags = sorted(self.repo_tags.get(state.commit, []), reverse=True)
            commit_tags = ', '.join(commit_tags) if commit_tags else ''
            self.stdout.write(
                f'{format_string.format(current_mark, str(state.timestamp)[:19], state.commit, commit_tags)}'
            )
