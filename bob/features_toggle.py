# Features can be toggled on and off per-chat.
# Check the models.py from bobapp to see the db_fields available for toggling.
# Also remember to add the feature mapping to the
# feature_name_vs_db_field_mapping variable when adding new features


import database

feature_name_vs_db_field_mapping = dict([
    ("1337", "leet_enabled"),
    ("ruoka", "ruoka_enabled"),
    ("space", "space_enabled"),
    ("kuulutus", "broadcast_enabled"),
    ("viisaus", "proverb_enabled"),
    ("aika", "time_enabled"),
    ("sää", "weather_enabled"),
    ("vai", "or_enabled"),
])


def toggle(chat_id, feature_name_to_toggle, desired_state=None):
    chat = database.get_chat(chat_id)
    feature_is_on = chat.__dict__[feature_name_vs_db_field_mapping[
                                  feature_name_to_toggle]]

    if desired_state is None:
        if feature_is_on:
            chat.__dict__[feature_name_vs_db_field_mapping[
                              feature_name_to_toggle]] = False
        else:
            chat.__dict__[feature_name_vs_db_field_mapping[
                              feature_name_to_toggle]] = True
    else:
        chat.__dict__[feature_name_vs_db_field_mapping[
            feature_name_to_toggle]] = desired_state
    chat.save()


def get_toggleable_features():
    return feature_name_vs_db_field_mapping
