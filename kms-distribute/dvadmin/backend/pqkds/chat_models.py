from django.db import models
class ChatMessage(models.Model):
    sender_id = models.CharField(max_length=100, db_index=True)
    receiver_id = models.CharField(max_length=100, db_index=True)
    message_content = models.TextField()
    encrypted_message = models.TextField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    is_read = models.BooleanField(default=False)
    class Meta:
        db_table = 'chat_messages'
        indexes = [
            models.Index(fields=['sender_id', 'receiver_id', '-timestamp']),
        ]
    def __str__(self):
        return f"{self.sender_id} -> {self.receiver_id}: {self.message_content[:50]}"
class ChatSession(models.Model):
    node_id_1 = models.CharField(max_length=100)
    node_id_2 = models.CharField(max_length=100)
    session_key = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    class Meta:
        db_table = 'chat_sessions'
        unique_together = ('node_id_1', 'node_id_2')
    def __str__(self):
        return f"Session: {self.node_id_1} <-> {self.node_id_2}"
class ChatNotification(models.Model):
    receiver_id = models.CharField(max_length=100, db_index=True)
    sender_id = models.CharField(max_length=100)
    message_id = models.ForeignKey(ChatMessage, on_delete=models.CASCADE)
    notification_type = models.CharField(
        max_length=20,
        choices=[
            ('new_message', '新消息'),
            ('message_read', '消息已读'),
            ('typing', '正在输入'),
        ]
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    class Meta:
        db_table = 'chat_notifications'
        indexes = [
            models.Index(fields=['receiver_id', '-created_at']),
        ]
    def __str__(self):
        return f"{self.notification_type}: {self.sender_id} -> {self.receiver_id}"