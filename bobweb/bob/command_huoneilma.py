import io

from telegram import Update
from telegram.ext import CallbackContext


def is_raspberrypi():
    try:
        with io.open(r'/model', 'r') as m:
            if 'raspberry pi' in m.read().lower():
                return True
    except Exception as e:
        print(e)
    return False


if is_raspberrypi():
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    import Adafruit_DHT

from bobweb.bob.command import ChatCommand, regex_simple_command

DHTSensor = 11  # same as 11
humidity_sensor_gpio_pin_number = 17


class HuoneilmaCommand(ChatCommand):
    def __init__(self):
        super().__init__(
            name='huoneilma',
            regex=regex_simple_command('huoneilma'),
            help_text_short=('huoneilma', 'Näyttää sisälämpötilan ja ilmankosteuden "serverihuoneessa"')
        )

    async def handle_update(self, update: Update, context: CallbackContext = None):
        if is_raspberrypi():
            try:
                relative_humidity_percentage, room_temperature_celsius = Adafruit_DHT.read_retry(
                    DHTSensor, humidity_sensor_gpio_pin_number)
                reply_text = interpret_measurement(relative_humidity_percentage, room_temperature_celsius)
            except Exception as e:
                print(e)
                reply_text = "Jokin meni vikaan antureita lukiessa."
        else:
            reply_text = "Anturit ovat käytettävissä vain Raspberry Pi alustalla"
        await update.effective_message.reply_text(reply_text)

    def is_enabled_in(self, chat):
        return True


def interpret_measurement(relative_humidity_percentage, room_temperature_celsius):
    if relative_humidity_percentage is not None and room_temperature_celsius is not None:
        return "Ilmankosteus: " + str(int(relative_humidity_percentage)) + " %.\n" + \
               "Lämpötila: " + str(int(room_temperature_celsius)) + " C°."
    else:
        return "Anturiin ei saatu yhteyttä. Anturia " + str(DHTSensor) + \
               " yritettiin lukea pinnistä " + str(humidity_sensor_gpio_pin_number) + "."
