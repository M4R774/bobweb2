from django.contrib import admin

from .models import TelegramUser, GitUser, Chat, ChatMember, Proverb, ChatProverb, Reminder

admin.site.register(TelegramUser)
admin.site.register(GitUser)
admin.site.register(Chat)
admin.site.register(ChatMember)
admin.site.register(Proverb)
admin.site.register(ChatProverb)
admin.site.register(Reminder)
