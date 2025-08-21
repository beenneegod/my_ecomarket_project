from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_GET, require_POST
from django.db.models import Q
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import ChatRoom, Message, ChatInvite, MessageAttachment
from .forms import ChatRoomForm, MessageForm

# Chat attachments validation settings
ALLOWED_MIME_PREFIXES = ['image/']
ALLOWED_MIME_TYPES = ['application/pdf']
MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB per file
MAX_TOTAL_BYTES = 40 * 1024 * 1024  # 40 MB per message


@login_required
def room_list(request):
    rooms = ChatRoom.objects.filter(Q(is_private=False) | Q(members=request.user)).distinct().order_by('-created_at')
    pending_invites = ChatInvite.objects.filter(invitee=request.user, status='pending').select_related('room', 'inviter')
    return render(request, 'chat/room_list.html', {'rooms': rooms, 'pending_invites': pending_invites})


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
        iterable = qs
    else:
        # Initial load: reverse newest-first slice to oldest→newest
        iterable = list(reversed(list(qs)))
    data = [
        {
            'id': m.id,
            'user': m.user.username,
            'text': m.text,
            'created_at': m.created_at.isoformat(),
            'reply_to': (
                {
                    'id': m.reply_to_id,
                    'user': getattr(m.reply_to.user, 'username', '') if m.reply_to_id else '',
                    'text': (m.reply_to.text[:120] if m.reply_to and m.reply_to.text else ''),
                } if m.reply_to_id else None
            ),
            'attachments': [
                {
                    'url': a.file.url,
                    'name': a.file.name.split('/')[-1],
                }
                for a in m.attachments.all()
            ],
            'can_delete': (m.user_id == request.user.id) or (room.owner_id == request.user.id),
        }
    for m in iterable
    ]
    return JsonResponse({'messages': data})


@login_required
@require_POST
def send_message(request, pk: int):
    room = get_object_or_404(ChatRoom, pk=pk)
    if room.is_private and request.user not in room.members.all():
        return JsonResponse({'error': 'forbidden'}, status=403)
    form = MessageForm(request.POST)
    reply_to_id = request.POST.get('reply_to')
    files = request.FILES.getlist('attachments')
    # Server-side validation for attachments
    total_size = 0
    invalid = []
    for f in files:
        ct = getattr(f, 'content_type', '') or ''
        size = getattr(f, 'size', 0) or 0
        if size > MAX_FILE_BYTES:
            invalid.append(f"Plik '{f.name}' przekracza {MAX_FILE_BYTES // (1024*1024)} MB")
        allowed = any(ct.startswith(p) for p in ALLOWED_MIME_PREFIXES) or ct in ALLOWED_MIME_TYPES
        if not allowed:
            invalid.append(f"Niedozwolony typ pliku dla '{f.name}'")
        total_size += size
    if total_size > MAX_TOTAL_BYTES:
        invalid.append(f"Łączny rozmiar przekracza {MAX_TOTAL_BYTES // (1024*1024)} MB")
    if invalid:
        return JsonResponse({'ok': False, 'errors': invalid}, status=400)
    if form.is_valid():
        msg = form.save(commit=False)
        msg.room = room
        msg.user = request.user
        if reply_to_id and str(reply_to_id).isdigit():
            try:
                from .models import Message as Msg
                msg.reply_to = Msg.objects.filter(room=room).get(pk=int(reply_to_id))
            except Msg.DoesNotExist:
                pass
        msg.save()
    else:
        # Allow image-only (or file-only) messages: create an empty-text message if files provided
        if files:
            msg = Message.objects.create(room=room, user=request.user, text='')
        else:
            return JsonResponse({'ok': False, 'errors': form.errors}, status=400)

    # Save attachments if any (cap to first N to prevent abuse)
    for f in files[:10]:
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
            'reply_to': (
                {
                    'id': msg.reply_to_id,
                    'user': getattr(msg.reply_to.user, 'username', '') if msg.reply_to_id else '',
                    'text': (msg.reply_to.text[:120] if msg.reply_to and msg.reply_to.text else ''),
                } if msg.reply_to_id else None
            ),
        }
    )
    return JsonResponse({'ok': True, 'id': msg.id})


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
    # Mark as removed; do not overwrite text to keep a single source of truth.
    msg.is_removed = True
    msg.save(update_fields=['is_removed'])
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
    # Use only the unique fields in the lookup; set inviter via defaults to avoid duplicates
    inv, created = ChatInvite.objects.get_or_create(
        room=room,
        invitee=invitee,
        status='pending',
        defaults={'inviter': request.user},
    )
    return JsonResponse({'ok': True, 'created': created, 'invite_id': inv.id})


@login_required
@require_POST
def accept_invite(request, invite_id: int):
    inv = get_object_or_404(ChatInvite, pk=invite_id, invitee=request.user)
    inv.status = 'accepted'
    inv.save(update_fields=['status'])
    inv.room.members.add(request.user)
    # If regular form post (not AJAX), redirect back to room list
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'ok': True})
    return redirect('chat:room_list')


@login_required
@require_POST
def decline_invite(request, invite_id: int):
    inv = get_object_or_404(ChatInvite, pk=invite_id, invitee=request.user)
    inv.status = 'declined'
    inv.save(update_fields=['status'])
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'ok': True})
    return redirect('chat:room_list')
