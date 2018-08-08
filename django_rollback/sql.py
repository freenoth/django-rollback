"""
Raw sql to extract migrations state for all apps in django projects (retrieve only last migration for every app)
from django core table 'django_migrations'.
"""

MIGRATIONS_STATE_SQL = """
with migrations AS (select
                      t.id,
                      t.app,
                      t.name
                    from django_migrations t
), max_migrations as (
    select
      t.app,
      max(t.id) as id
    from migrations t
    group by t.app
)
select
  t.id,
  t.app,
  t.name
from migrations t
where exists(
    select 1
    from max_migrations tt
    where tt.app = t.app and tt.id = t.id
)
order by t.app;
"""
