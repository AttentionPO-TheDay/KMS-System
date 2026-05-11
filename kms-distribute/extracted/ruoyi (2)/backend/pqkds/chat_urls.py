from django.urls import path
from . import chat_views
urlpatterns = [
    path('', chat_views.chat_page, name='chat_page'),
    path('send-message/', chat_views.send_message, name='send_message'),
    path('messages/', chat_views.get_messages, name='get_messages'),
    path('nodes/', chat_views.get_nodes, name='get_nodes'),
]