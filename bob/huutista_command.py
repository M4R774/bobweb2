from abstract_command import AbstractCommand

class HuutistaCommand(AbstractCommand):
    def __init__(self):
        super().__init__(
            'huutista',
            r'(?i)huutista',  # (?i) => case insensitive
            ('huutista', '😂')
        )

    def handle_update(self, update):
        update.message.reply_text('...joka tuutista! 😂')

    def is_enabled_in(self, chat):
        return chat.huutista_enabled
