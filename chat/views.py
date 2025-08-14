from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_GET, require_POST
from django.db.models import Q
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import ChatRoom, Message, ChatInvite, MessageAttachment
from .forms import ChatRoomForm, MessageForm


@login_required
def room_list(request):
    rooms = ChatRoom.objects.filter(Q(is_private=False) | Q(members=request.user)).distinct().order_by('-created_at')
    return render(request, 'chat/room_list.html', {'rooms': rooms})


@login_required
def room_create(request):
    if request.method == 'POST':
        form = ChatRoomForm(request.POST)
        if form.is_valid():
            room = form.save(commit=False)
            room.owner = request.user
            room.save()
            room.members.add(request.user)
            return redirect('chat:room_detail', pk=room.pk)
    else:
        form = ChatRoomForm()
    return render(request, 'chat/room_create.html', {'form': form})


@login_required
def room_detail(request, pk: int):
    room = get_object_or_404(ChatRoom, pk=pk)
    if room.is_private and request.user not in room.members.all():
        return HttpResponseForbidden('Brak dostępu do tego pokoju')
    form = MessageForm()
    return render(request, 'chat/room_detail.html', {'room': room, 'form': form})


@login_required
@require_GET
def messages_api(request, pk: int):
    room = get_object_or_404(ChatRoom, pk=pk)
    if room.is_private and request.user not in room.members.all():
        return JsonResponse({'error': 'forbidden'}, status=403)
    since_id = request.GET.get('since_id')
    qs = room.messages.filter(is_removed=False).prefetch_related('attachments').order_by('-id')[:50]
    if since_id and since_id.isdigit():
        qs = room.messages.filter(is_removed=False, id__gt=int(since_id)).prefetch_related('attachments').order_by('id')[:100]
    data = [
        {
            'id': m.id,
            'user': m.user.username,
            'text': m.text,
            'created_at': m.created_at.isoformat(),
            'attachments': [
                {
                    'url': a.file.url,
                    'name': a.file.name.split('/')[-1],
                }
                for a in m.attachments.all()
            ],
            'can_delete': (m.user_id == request.user.id) or (room.owner_id == request.user.id),
        }
        for m in qs
    ]
    return JsonResponse({'messages': data})


@login_required
@require_POST
def send_message(request, pk: int):
    room = get_object_or_404(ChatRoom, pk=pk)
    if room.is_private and request.user not in room.members.all():
        return JsonResponse({'error': 'forbidden'}, status=403)
    form = MessageForm(request.POST)
    if form.is_valid():
        msg = form.save(commit=False)
        msg.room = room
        msg.user = request.user
        msg.save()
        # Save attachments if any
        for f in request.FILES.getlist('attachments'):
            MessageAttachment.objects.create(message=msg, file=f)
        # Broadcast over WS
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"chat_{room.id}",
            {
                'type': 'chat.message',
                'id': msg.id,
                'user': msg.user.username,
                'text': msg.text,
                'created_at': msg.created_at.isoformat(),
                'user_id': request.user.id,
                'room_owner_id': room.owner_id,
                'attachments': [
                    {'url': a.file.url, 'name': a.file.name.split('/')[-1]}
                    for a in msg.attachments.all()
                ],
            }
        )
        return JsonResponse({'ok': True, 'id': msg.id})
    return JsonResponse({'ok': False, 'errors': form.errors}, status=400)


@login_required
@require_POST
def delete_message(request, msg_id: int):
    msg = get_object_or_404(Message, pk=msg_id)
    room = msg.room
    if room.is_private and request.user not in room.members.all():
        return JsonResponse({'error': 'forbidden'}, status=403)
    # Only author or room owner can delete
    if msg.user_id != request.user.id and room.owner_id != request.user.id:
        return JsonResponse({'error': 'forbidden'}, status=403)
    msg.is_removed = True
    msg.text = '[wiadomość usunięta]'
    msg.save(update_fields=['is_removed', 'text'])
    # Broadcast removal
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"chat_{room.id}",
        {
            'type': 'chat.message_removed',
            'id': msg.id,
        }
    )
    return JsonResponse({'ok': True})


@login_required
@require_POST
def send_invite(request, pk: int):
    room = get_object_or_404(ChatRoom, pk=pk)
    if room.is_private and request.user not in room.members.all():
        return JsonResponse({'error': 'forbidden'}, status=403)
    user_id = request.POST.get('user_id')
    username = request.POST.get('username')
    from django.contrib.auth import get_user_model
    User = get_user_model()
    invitee = None
    if user_id and user_id.isdigit():
        invitee = get_object_or_404(User, pk=int(user_id))
    elif username:
        invitee = get_object_or_404(User, username=username)
    else:
        return JsonResponse({'error': 'user_id or username required'}, status=400)
    inv, created = ChatInvite.objects.get_or_create(
        room=room, inviter=request.user, invitee=invitee, status='pending'
    )
    return JsonResponse({'ok': True, 'created': created, 'invite_id': inv.id})


@login_required
@require_POST
def accept_invite(request, invite_id: int):
    inv = get_object_or_404(ChatInvite, pk=invite_id, invitee=request.user)
    inv.status = 'accepted'
    inv.save(update_fields=['status'])
    inv.room.members.add(request.user)
    return JsonResponse({'ok': True})


@login_required
@require_POST
def decline_invite(request, invite_id: int):
    inv = get_object_or_404(ChatInvite, pk=invite_id, invitee=request.user)
    inv.status = 'declined'
    inv.save(update_fields=['status'])
    return JsonResponse({'ok': True})
