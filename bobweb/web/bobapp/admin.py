from django.contrib import admin

from bobweb.web.bobapp.models import TelegramUser, GitUser, Chat, ChatMember, Proverb, ChatProverb, Reminder


class AdminChatMember(admin.ModelAdmin):
    model = ChatMember
    list_display = ('chat', 'tg_user', 'rank', 'prestige', 'message_count', 'admin', 'latest_weather_city')


admin.site.register(TelegramUser)
admin.site.register(GitUser)
admin.site.register(Chat)
admin.site.register(ChatMember, AdminChatMember)
admin.site.register(Proverb)
admin.site.register(ChatProverb)
admin.site.register(Reminder)
