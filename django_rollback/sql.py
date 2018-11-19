"""
Raw sql to extract migrations state for all apps in django projects (retrieve only last migration for every app)
from django core table 'django_migrations'.
"""

MIGRATIONS_STATE_SQL = """
with migrations AS (select
                      dm.id,
                      dm.app,
                      dm.name
                    from django_migrations dm
), max_migrations as (
    select
      ms.app,
      max(ms.id) as id
    from migrations ms
    group by ms.app
)
select
  ms.id,
  ms.app,
  ms.name
from migrations ms
where exists(
    select 1
    from max_migrations mms
    where mms.app = ms.app and mms.id = ms.id
)
order by ms.app;
"""
