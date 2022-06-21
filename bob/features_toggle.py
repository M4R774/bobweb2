# Features can be toggled on and off per-chat.
# Check the models.py from bobapp to see the db_fields available for toggling.

feature_name_vs_db_field_mapping = ([
    ("1337", "leet_enabled"),
    ("ruoka", "ruoka_enabled"),
    ("space", "space_enabled"),
    ("kuulutus", "broadcast_enabled"),
    ("viisaus", "proverb_enabled"),
    ("aika", "time_enabled"),
    ("sää", "weather_enabled"),
    ("vai", "or_enabled"),
])


def toggle(feature_name_to_toggle, desired_state=None):
    # TODO
    pass


def get_toggleable_features():
    # TODO return all available features for toggling on and off
    # and the status of those features.
    pass
