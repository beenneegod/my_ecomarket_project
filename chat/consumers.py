import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser

from .models import ChatRoom, Message


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_id = self.scope['url_route']['kwargs'].get('room_id')
        self.group_name = f"chat_{self.room_id}"
        user = self.scope.get('user')

        # Auth required
        if isinstance(user, AnonymousUser) or not user.is_authenticated:
            await self.close(code=4401)  # unauthorized
            return

        # Room validation and permission check
        room = await self._get_room(self.room_id)
        if not room:
            await self.close(code=4404)  # not found
            return
        if room.is_private and not await self._is_member(room, user.id):
            await self.close(code=4403)  # forbidden
            return

        # Cache owner id for per-connection permissions
        self.room_owner_id = room.owner_id

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Send last messages as history (oldest first)
        history = await self._get_recent_messages(room_id=self.room_id, user_id=user.id, limit=30)
        if history:
            await self.send(text_data=json.dumps({
                'type': 'history',
                'messages': history,
            }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        try:
            payload = json.loads(text_data or '{}')
        except json.JSONDecodeError:
            return
        action = payload.get('action')
        if action == 'send':
            text = (payload.get('text') or '').strip()
            if not text:
                return
            user = self.scope['user']
            msg = await self._create_message(room_id=self.room_id, user_id=user.id, text=text)
            event = {
                'type': 'chat.message',
                'id': msg['id'],
                'user': msg['user'],
                'text': msg['text'],
                'created_at': msg['created_at'],
                'user_id': user.id,
                'room_owner_id': self.room_owner_id,
                'attachments': [],
            }
            await self.channel_layer.group_send(self.group_name, event)

    async def chat_message(self, event):
        # Compute per-connection deletion rights
        user_id = getattr(self.scope.get('user'), 'id', None)
        can_delete = (event.get('user_id') == user_id) or (event.get('room_owner_id') == user_id)
        await self.send(text_data=json.dumps({
            'type': 'message',
            'id': event['id'],
            'user': event['user'],
            'text': event['text'],
            'created_at': event['created_at'],
            'can_delete': can_delete,
            'attachments': event.get('attachments', []),
        }))

    async def chat_message_removed(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message_removed',
            'id': event['id'],
        }))

    # DB helpers
    @database_sync_to_async
    def _get_room(self, room_id):
        try:
            return ChatRoom.objects.get(pk=room_id)
        except ChatRoom.DoesNotExist:
            return None

    @database_sync_to_async
    def _is_member(self, room, user_id: int) -> bool:
        return room.members.filter(id=user_id).exists()

    @database_sync_to_async
    def _get_recent_messages(self, room_id: int, user_id: int, limit: int = 30):
        qs = (
            Message.objects.filter(room_id=room_id, is_removed=False)
            .order_by('-id')[:limit]
        )
        data = [
            {
                'id': m.id,
                'user': m.user.username,
                'text': m.text,
                'created_at': m.created_at.isoformat(),
                'can_delete': (m.user_id == user_id) or (m.room.owner_id == user_id),
                'attachments': [],
            }
            for m in reversed(list(qs))
        ]
        return data

    @database_sync_to_async
    def _create_message(self, room_id: int, user_id: int, text: str):
        msg = Message.objects.create(room_id=room_id, user_id=user_id, text=text)
        return {
            'id': msg.id,
            'user': msg.user.username,
            'text': msg.text,
            'created_at': msg.created_at.isoformat(),
        }
