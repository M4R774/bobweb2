-- query, that prints daily_questions between given range or in a season
with recursive
  -- set query variables
  -- To modify query with parameters, replace 'null' with wanted value
  vars(var_season_id, var_start_date, var_end_date) as (
    select null as var_season_id,
           null as var_start_date,
           null as var_end_date
  ),
  -- intermediate table that contains all dates in range. recursive call that carries all parameters
  dates(date, param_season_id, param_end_date) as (
    select
        -- given var, or star_datetime of the season
        date(coalesce(var_start_date, start_datetime)),
        -- given var, or last added season
        coalesce(var_season_id, (select max(id) from bobapp_daily_question_season)) as param_season_id,
        -- given var, or end_datetime of the season or today
        coalesce(var_end_date, end_datetime, date('now')) as param_end_date
    from bobapp_daily_question_season, (select * from vars) -- add vars to be easily accessible
    where id = param_season_id
    union all
    -- select rolling date and all parameters to the recursive query
    select date(date, '+1 day'), param_season_id, param_end_date
    from dates
    where date < param_end_date
  )
-- the query that wraps all together
-- selects date and content
select
  case strftime('%w', dates.date)
    when '0' then 'sunday'
    when '6' then 'saturday'
    else dates.date
  end as date,
    u.first_name,
    dq.content
from dates left outer join bobapp_daily_question dq on dates.date = date(dq.date_of_question)
    left outer join bobapp_telegramuser u on dq.question_author_id = u.id
where dq.id is null or dates.param_season_id = dq.season_id
order by dates.date;
