from datetime import datetime


# Parses date and returns it. If parameter is not valid date, None is returned
def parse_date(text: str) -> str | None:
    for date_format in ('%Y-%m-%d', '%d.%m.%Y', '%m/%d/%Y'):  # 2022-01-31, 31.01.2022, 01/31/2022
        try:
            return str(datetime.strptime(text, date_format))
        except ValueError:
            pass
    return None
