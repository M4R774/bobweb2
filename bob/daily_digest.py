import time
import main
import datetime
from datetime import timedelta
import pytz

def daily_digest(updater):
    # time for daily digest is 07:00 UTC daily
    current_time = datetime.datetime.now(pytz.utc)
    current_day_number = datetime.datetime.weekday(current_time)

    next_digest = datetime.datetime.date(current_time)
    next_digest += timedelta(days=1)
    next_digest = str(next_digest) + " 07:00:00"
    date_format = '%Y-%m-%d %H:%M:%S'
    next_digest = datetime.datetime.strptime(next_digest, date_format)
    naive_next_digest_string = str(next_digest.strftime('%Y-%m-%d %H:%M:%S'))
    naive_next_digest = datetime.datetime.strptime(naive_next_digest_string, date_format)

    naive_current_time_string = str(datetime.datetime.now(pytz.utc).strftime('%Y-%m-%d %H:%M:%S'))
    naive_current_time = datetime.datetime.strptime(naive_current_time_string, date_format)
    time_until_next_digest = next_digest - naive_current_time
    time_until_next_digest = naive_next_digest - naive_current_time
    time_until_next_digest = int(round(time_until_next_digest.total_seconds()))

    # for debugging
    # broadcast_message = current_time.strftime('%Y-%m-%d %H:%M:%S') + " " +\
    #             next_digest.strftime('%Y-%m-%d %H:%M:%S') + " " + str(time_until_next_digest)
    #broadcast_message = str(time_until_next_digest)
    #main.broadcast(updater.bot, "Odotan " + broadcast_message +\
    #                            " sekunnin ajan seuraavaa Daily Digestiä.")

    # function needs to be in its own file for time.sleep()
    # otherwise whole bot sleeps
    time.sleep(time_until_next_digest)
    
    # to do suggestions:
    # list sun rise and sun set at Turenki
    # birth days
    # name days
    # things from esmf calendar
    # other important dates
    # wisdom
    # most ranked player and their rank
    if current_day_number == 4:
        broadcast_message = main.free_epic_game()
        # to do: list ranks
    else:
        broadcast_message ="Bobi jyystää apinaa tänäänkin " + "\U0001F412" #monkey emoji
    # broadcast requires kuulutukset ON so it's not ideal
    main.broadcast(updater.bot, broadcast_message)
    daily_digest(updater)