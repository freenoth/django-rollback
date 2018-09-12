# Django auto rollback
This package allow to easy manage apps migrations based on GIT repository (it use commits to save apps state).
So you can return to any previous state that is saved in DB by one command.

## Version
Current version is `0.3.1`

It works with:
- django >= 1.11.3
- GitPython >= 2.1.8
- PostgreSQL

## Installing

First you need to install package with pip:
```bash
pip install git+https://github.com/freenoth/django-rollback.git@0.3.1
```

Then install it to your `INSTALLED_APPS`
```python
INSTALLED_APPS = [
    # ...
    'django_rollback',
]
```

You are also should run `./manage.py migrate` before using additional management commands.

## Using
There are two commands to manage migrations state.

Both commands have common arguments:
```bash
  -p PATH, --path PATH  Git repository path.
  -l LOGGER, --logger LOGGER
                        Logger name for logging.
  --log-level LOG_LEVEL
                        Log level for logging. INFO, DEBUG, etc.

```
`PATH` argument used to specify path to git repository directory (local). Default path is current dir : `'.'`.

`LOGGER` and `LOG_LEVEL` arguments can be used to setup internal logging. For example, you can use one of django_logging loggers (to push it to slack, write console, file, etc.). There is no default value, so by default additional logging disabled.

### Saving current state
```bash
./manage.py save_migrations_state
```
Help message below:
```bash
usage: manage.py save_migrations_state [-p PATH] [-l LOGGER]
                                       [--log-level LOG_LEVEL]

Save migrations state for current commit. It also check if commit already
exists and print warning if it`s not the latest state that may be a symptom of
inconsistent state for migrations.

optional arguments:
  -p PATH, --path PATH  Git repository path.
  -l LOGGER, --logger LOGGER
                        Logger name for logging.
  --log-level LOG_LEVEL
                        Log level for logging. INFO, DEBUG, etc.

```
This command used to save apps migrations state of current commit to DB. It try to create new state, but if already exists it checks is this state the latest.
If state for current commit is not the latest - it may be a symptom of problems and rollback from current commit will not work for it.

Successful output example below:
```bash
Data = [(4, 'admin', '0002_logentry_remove_auto_add'), (12, 'auth', '0008_alter_user_username_max_length'), (5, 'contenttypes', '0002_remove_content_type_name'), (16, 'django_auto_rollback', '0001_initial'), (17, 'django_rollback', '0001_initial'), (14, 'sessions', '0001_initial')].
Successfully created for commit "84e47461a95fa325d9e933bbe8cca8c52bbea203".
```

### Return to previous state (rollback)
```bash
./manage.py rollback_migrations
```
Help message below:
```bash
usage: manage.py rollback_migrations [-p PATH] [-l LOGGER] [--log-level LOG_LEVEL]
                                     [--list] [-t TAG] [-c COMMIT] [--fake]

Rollback migrations state of all django apps to chosen tag or commit if
previously saved. Also you may not specify commit or tag to rollback, so the
previous tag will be used. Also it can run in fake mode, only to print
generated commands for rollback. You also can view current DB state for all
saved states using list argument.

optional arguments:
  -p PATH, --path PATH  Git repository path.
  -l LOGGER, --logger LOGGER
                        Logger name for logging.
  --log-level LOG_LEVEL
                        Log level for logging. INFO, DEBUG, etc.
  --list                Show the sorted list of all stored states.
  -t TAG, --tag TAG     Git tag to which to rollback migrations.
  -c COMMIT, --commit COMMIT
                        Git commit hash to which to rollback migrations.
  --fake                It allow to only print info about processed actions
                        without execution (no changes for DB).
```

You can use git commit hash (hex) directly. And you don`t need to specify full commit hash, you just can use first letters.
The commands below are equal:
```bash
./manage.py rollback_migrations -c 0e02e741c5953212428adc1cac9060b2a0b8626b
./manage.py rollback_migrations -c 0e02e74
./manage.py rollback_migrations --commit 0e02e74
```
Or you can use git tag (it will be translated to related commit).
```bash
./manage.py rollback_migrations -t v.0.0.1
./manage.py rollback_migrations --tag v.0.0.2
```

Successful output example below:
```bash
./manage.py rollback_migrations -c c257a23
>>> Executing command: migrate django_rollback zero
Operations to perform:
  Unapply all migrations: django_rollback
Running migrations:
  Rendering model states... DONE
  Unapplying django_rollback.0001_initial... OK
Rollback successfully finished.
```

As you can see above, apps can be rollbacked to `zero` state too, if in previous state this app not used.

After successful rollback, selected state will be selected as current, so all older states will be deleted.
That`s way current state all the time should be the latest in DB and correspond to current service state.

### Successful rollback conditions
So rollback will be successfully finished if two conditions are satisfied:
- state for current commit was saved (if not - use `./manage.py save_migrations_state` command)
- state for specified commit, commit which relates to specified tag was saved in the past
- if commit not specified, just the previous state should exists 
