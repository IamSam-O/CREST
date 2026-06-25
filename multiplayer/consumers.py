import random
import secrets

from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer

from .models import MultiplayerParticipant, MultiplayerSession


class MultiplayerConsumer(JsonWebsocketConsumer):
    """Host-paced lockstep protocol: the host explicitly advances the room
    ('start'/'next'/'end'); guests just answer the current question. No
    login required for guests - the passcode is the only gate."""

    def connect(self):
        self.room_code = self.scope['url_route']['kwargs']['room_code']
        self.group_name = f'mp_{self.room_code}'
        self.session_obj = None
        self.participant = None
        self.role = None
        async_to_sync(self.channel_layer.group_add)(self.group_name, self.channel_name)
        self.accept()

    def disconnect(self, close_code):
        async_to_sync(self.channel_layer.group_discard)(self.group_name, self.channel_name)
        if self.role == 'host' and self.session_obj:
            # self.session_obj is cached from host_join and never updated by
            # handle_start/handle_next/handle_resume (they fetch their own local
            # copy) - re-query so we check the session's real current status.
            try:
                session = self._get_session()
            except ValueError:
                return
            if session.status == MultiplayerSession.ACTIVE:
                session.status = MultiplayerSession.PAUSED
                session.save(update_fields=['status'])
                self._broadcast({'type': 'host_disconnected'})
        elif self.role == 'guest' and self.participant:
            self.participant.connected = False
            self.participant.save(update_fields=['connected'])
            self._broadcast({'type': 'participant_left', 'displayName': self.participant.display_name})
            try:
                session = self._get_session()
            except ValueError:
                return
            if session.status == MultiplayerSession.ACTIVE and session.questions_json:
                question_id = str(session.questions_json[session.current_index]['id'])
                self._maybe_auto_advance(session, session.current_index, question_id)

    def receive_json(self, content, **kwargs):
        handler = getattr(self, f'handle_{content.get("type")}', None)
        if not handler:
            self.send_json({'type': 'error', 'error': 'Unknown message type.'})
            return
        try:
            handler(content)
        except ValueError as exc:
            self.send_json({'type': 'error', 'error': str(exc)})

    # ---- message handlers ----

    def handle_host_join(self, content):
        session = self._get_session()
        if content.get('hostSecret') != session.host_secret:
            raise ValueError('Not authorized as host for this session.')
        self.role = 'host'
        self.session_obj = session
        self.send_json({
            'type': 'host_ready',
            'roomCode': session.room_code,
            'passcode': session.passcode,
            'status': session.status,
            'leaderboard': self._leaderboard(session),
        })

    def handle_guest_join(self, content):
        session = self._get_session()
        if content.get('passcode') != session.passcode:
            raise ValueError('Incorrect passcode.')

        display_name = (content.get('displayName') or '').strip()[:64] or 'Player'
        client_id = content.get('clientId') or secrets.token_urlsafe(8)
        participant, _created = MultiplayerParticipant.objects.update_or_create(
            session=session, client_id=client_id,
            defaults={'display_name': display_name, 'connected': True},
        )
        self.role = 'guest'
        self.session_obj = session
        self.participant = participant
        self.send_json({'type': 'joined', 'clientId': client_id, 'status': session.status, 'displayName': participant.display_name})
        self._broadcast({'type': 'participant_joined', 'displayName': display_name})
        if session.status == MultiplayerSession.ACTIVE and session.questions_json:
            question = dict(session.questions_json[session.current_index])
            question.pop('correctOptionIds', None)
            self.send_json({
                'type': 'question',
                'index': session.current_index,
                'total': len(session.questions_json),
                'question': question,
                'bonusWindowSeconds': session.exam.bonus_window_seconds,
            })

    def handle_start(self, content):
        session = self._require_host()
        questions = list(session.exam.questions.order_by('sort_order'))
        if not questions:
            raise ValueError('This exam has no questions.')
        random.shuffle(questions)

        snapshot = []
        for q in questions:
            opts = list(q.options.all())
            random.shuffle(opts)
            snapshot.append({
                'id': q.id,
                'questionText': q.question_text,
                'questionType': q.question_type,
                'imageLink': q.image_link,
                'points': q.points,
                'correctOptionIds': [o.id for o in opts if o.is_correct],
                'correctCount': sum(1 for o in opts if o.is_correct),
                'options': [{'id': o.id, 'text': o.option_text} for o in opts],
            })

        time_limit = content.get('timeLimitSeconds', 0)
        try:
            time_limit = max(0, int(time_limit))
        except (TypeError, ValueError):
            time_limit = 0

        session.questions_json = snapshot
        session.current_index = 0
        session.status = MultiplayerSession.ACTIVE
        session.time_limit_seconds = time_limit
        session.save(update_fields=['questions_json', 'current_index', 'status', 'time_limit_seconds'])
        self._broadcast_question(session)

    def handle_answer(self, content):
        if self.role != 'guest' or not self.participant:
            raise ValueError('Join the session before answering.')
        session = self._get_session()
        if session.status != MultiplayerSession.ACTIVE or session.current_index >= len(session.questions_json):
            raise ValueError('No active question to answer.')

        question_idx = session.current_index
        question = session.questions_json[question_idx]
        question_id = str(question['id'])
        selected = {int(i) for i in (content.get('selectedOptionIds') or [])}
        is_correct = selected == set(question['correctOptionIds'])
        if is_correct:
            client_claim = content.get('pointsAwarded')
            try:
                points = max(0, int(client_claim)) if client_claim is not None else question['points']
            except (TypeError, ValueError):
                points = question['points']
        else:
            points = 0

        answers = self.participant.answers_json or {}
        answers[question_id] = {
            'selectedOptionIds': list(selected),
            'isCorrect': is_correct,
            'pointsAwarded': points,
        }
        self.participant.answers_json = answers
        if is_correct:
            self.participant.score += points
        self.participant.save(update_fields=['answers_json', 'score'])
        self.send_json({'type': 'answer_ack', 'isCorrect': is_correct, 'pointsAwarded': points, 'correctOptionIds': question['correctOptionIds']})
        self._maybe_auto_advance(session, question_idx, question_id)

    def handle_resume(self, content):
        session = self._require_host()
        if session.status != MultiplayerSession.PAUSED:
            raise ValueError('Session is not paused.')
        session.status = MultiplayerSession.ACTIVE
        session.save(update_fields=['status'])
        self._broadcast_question(session)

    def handle_next(self, content):
        session = self._require_host()
        if session.status != MultiplayerSession.ACTIVE:
            raise ValueError('Session is not active.')
        self._advance(session)

    def handle_end(self, content):
        session = self._require_host()
        self._finish(session)

    # ---- helpers ----

    def _get_session(self):
        try:
            return MultiplayerSession.objects.select_related('exam', 'host').get(room_code=self.room_code)
        except MultiplayerSession.DoesNotExist as exc:
            raise ValueError('Session not found.') from exc

    def _require_host(self):
        if self.role != 'host' or not self.session_obj:
            raise ValueError('Host only.')
        return self._get_session()

    def _leaderboard(self, session):
        participants = session.participants.order_by('-score')
        return [{'displayName': p.display_name, 'score': p.score, 'connected': p.connected} for p in participants]

    def _advance(self, session):
        self._broadcast_reveal(session)
        session.current_index += 1
        if session.current_index >= len(session.questions_json):
            self._finish(session)
        else:
            session.save(update_fields=['current_index'])
            self._broadcast_question(session)

    def _finish(self, session):
        leaderboard = self._leaderboard(session)
        # filter().delete() is atomic - if a concurrent final answer already deleted this
        # session, deleted_count is 0 and we skip broadcasting a stale/empty leaderboard.
        deleted_count, _ = MultiplayerSession.objects.filter(pk=session.pk).delete()
        if deleted_count:
            self._broadcast({'type': 'leaderboard', 'final': True, 'leaderboard': leaderboard})

    def _maybe_auto_advance(self, session, question_idx, question_id):
        try:
            session.refresh_from_db()
        except MultiplayerSession.DoesNotExist:
            return  # session was just deleted (ended/finished) by another answer's race
        if session.current_index != question_idx or session.status != MultiplayerSession.ACTIVE:
            return  # another answer already triggered advance
        connected = list(session.participants.filter(connected=True))
        if not connected:
            return
        if all((p.answers_json or {}).get(question_id) is not None for p in connected):
            self._advance(session)

    def _broadcast(self, payload):
        async_to_sync(self.channel_layer.group_send)(
            self.group_name, {'type': 'broadcast.message', 'payload': payload}
        )

    def _broadcast_question(self, session):
        question = dict(session.questions_json[session.current_index])
        question.pop('correctOptionIds', None)
        self._broadcast({
            'type': 'question',
            'index': session.current_index,
            'total': len(session.questions_json),
            'question': question,
            'bonusWindowSeconds': session.exam.bonus_window_seconds,
            'timeLimit': session.time_limit_seconds,
        })

    def _broadcast_reveal(self, session):
        question = session.questions_json[session.current_index]
        self._broadcast({
            'type': 'reveal',
            'correctOptionIds': question['correctOptionIds'],
            'leaderboard': self._leaderboard(session),
        })

    # Channel-layer event entrypoint (group_send target).
    def broadcast_message(self, event):
        self.send_json(event['payload'])
