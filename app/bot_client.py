import functools
import inspect
import logging
import re
from typing import Callable, Awaitable, Sequence, BinaryIO, Type

import telethon.sessions
from telethon import TelegramClient, events, hints, tl
from telethon.events import StopPropagation
from telethon.events.common import EventCommon, EventBuilder, name_inner_event
from telethon.tl import types, custom

logger = logging.getLogger(__name__)

EventHandler = Callable[[EventCommon], Awaitable[None]]
MiddlewareCallback = Callable[[], Awaitable[None]]
Middleware = Callable[[EventCommon, MiddlewareCallback], Awaitable[None]]


def is_raw(event_builder: EventBuilder | Type[EventBuilder]):
    return event_builder is events.Raw or isinstance(event_builder, events.Raw)


async def _handler_wrapper(
    event: EventCommon, builder: EventBuilder, callback: MiddlewareCallback
):
    try:
        res = await callback()
        if (
            isinstance(builder, CallbackQuery)
            and isinstance(event, CallbackQuery.Event)
            and builder.auto_answer
        ):
            if res is not None and not isinstance(res, str):
                raise ValueError(
                    'CallbackQuery handler should return return a string when auto_answer is True'
                )
            await event.answer(res)
    except Exception:
        if (
            isinstance(builder, CallbackQuery)
            and isinstance(event, CallbackQuery.Event)
            and builder.auto_error_message
        ):
            client: BotClient = event.client
            error_text = client.inline_error_text
            if error_text is None:
                error_text = 'Something went wrong. Please try again later.'
            if callable(error_text):
                error_text = error_text(event)
                if inspect.isawaitable(error_text):
                    error_text = await error_text
            if error_text:
                await event.answer(error_text)
        if isinstance(callback, functools.partial):
            func = callback.func
        else:
            func = callback
        func_name = getattr(func, '__name__', repr(func))
        logger.exception('Unhandled exception on %s', func_name)
    finally:
        stop_propagation = isinstance(builder, Command) and builder.stop_propagation
        if stop_propagation:
            raise StopPropagation


class BotClient(TelegramClient):
    me: types.User
    _middlewares: list[Middleware]
    _handlers_map: dict[EventHandler, EventHandler]

    def __init__(
        self,
        session: str | telethon.sessions.Session,
        api_id: int,
        api_hash: str,
        inline_error_text: 'Callable[[CallbackQuery.Event], Awaitable[str] | str] | str | None' = None,
        **kwargs,
    ):
        self._middlewares = []
        self._handlers_map = {}
        self.inline_error_text = inline_error_text
        super().__init__(session, api_id, api_hash, **kwargs)
        self.parse_mode = 'html'

    async def start(self, bot_token: str):
        await super().start(bot_token=bot_token)
        self.me = await self.get_me()

    async def _handle_event(
        self, handler: EventHandler, builder: EventBuilder, event: EventCommon
    ):
        callback = functools.partial(handler, event)
        callback = functools.partial(_handler_wrapper, event, builder, callback)
        if not is_raw(builder):
            for middleware in reversed(self._middlewares):
                callback = functools.partial(middleware, event, callback)
        await callback()

    def add_event_handler(
        self, callback: EventHandler, event_builder: EventBuilder = None
    ):
        if is_raw(event_builder):
            logger.warning(
                'Handler for events.Raw added. Middlewares will not be applied for that event.'
            )
        handler = self._handlers_map[callback] = functools.partial(
            self._handle_event,
            callback,
            event_builder,
        )
        return super().add_event_handler(handler, event_builder)

    def remove_event_handler(
        self, callback: EventHandler, event_builder: EventBuilder = None
    ) -> int:
        handler = self._handlers_map.pop(callback, None)
        return super().remove_event_handler(handler, event_builder)

    def add_middleware(self, middleware: Middleware):
        self._middlewares.append(middleware)

    def include(self, handler_group: 'BotRouter'):
        # noinspection PyProtectedMember
        for event, callback in handler_group._handlers:
            self.add_event_handler(callback, event)


class BotRouter:
    def __init__(self):
        self._handlers = []

    def add_event_handler(self, callback: EventHandler, event: EventBuilder = None):
        self._handlers.append((event, callback))

    def on(self, event: EventBuilder):
        def decorator(callback: EventHandler):
            self.add_event_handler(callback, event)
            return callback

        return decorator

    def include(self, handler_group: 'BotRouter'):
        self._handlers.extend(handler_group._handlers)


FileLike = (
    hints.LocalPath
    | hints.ExternalUrl
    | hints.BotFileID
    | bytes
    | BinaryIO
    | types.TypeMessageMedia
    | types.TypeInputFile
    | types.TypeInputFileLocation
    | types.Photo
    | types.Document
)


class Message(custom.Message):
    """
    This class only exists to provide type hints
    """

    client: BotClient

    async def reply(
        self,
        message: 'hints.MessageLike' = '',
        *,
        attributes: Sequence[types.TypeDocumentAttribute] = None,
        parse_mode: str | None = (),
        formatting_entities: list[types.TypeMessageEntity] | None = None,
        link_preview: bool = True,
        file: FileLike | Sequence[FileLike] = None,
        thumb: FileLike = None,
        force_document: bool = False,
        clear_draft: bool = False,
        buttons: hints.MarkupLike = None,
        silent: bool = None,
        background: bool = None,
        supports_streaming: bool = False,
        schedule: hints.DateLike = None,
        comment_to: int | types.Message = None,
    ) -> 'Message': ...

    respond = reply

    async def get_reply_message(self) -> 'Message': ...


def filter_pm_group_only(self: 'NewMessage', event: 'NewMessage.Event') -> bool:
    if self.pm_only and not event.message.is_private:
        return False
    if self.group_only and not event.message.is_group:
        return False
    return True


@name_inner_event
class NewMessage(events.NewMessage):
    def __init__(
        self,
        chats=None,
        *,
        blacklist_chats: bool = False,
        func: 'Callable[[NewMessage.Event], bool]' = None,
        incoming: bool = None,
        outgoing: bool = None,
        from_users=None,
        forwards: bool = None,
        pattern: re.Pattern | str = None,
        pm_only: bool = False,
        group_only: bool = False,
    ):
        self.pm_only = pm_only
        self.group_only = group_only
        super().__init__(
            chats,
            blacklist_chats=blacklist_chats,
            func=func,
            incoming=incoming,
            outgoing=outgoing,
            from_users=from_users,
            forwards=forwards,
            pattern=pattern,
        )

    def filter(self, event: 'NewMessage.Event'):
        if not filter_pm_group_only(self, event):
            return False
        return super().filter(event)

    class Event(events.NewMessage.Event):
        client: BotClient
        message: Message
        pattern_match: re.Match


@name_inner_event
class Command(NewMessage):
    def __init__(
        self,
        command: str,
        *,
        prefix: str = '/',
        regex: bool = False,
        stop_propagation: bool = True,
        pm_only: bool = False,
        group_only: bool = False,
        func: 'Callable[[NewMessage.Event], bool]' = None,
    ):
        self.command = command
        self.prefix = prefix
        self.regex = re.compile(command) if regex else None
        self.stop_propagation = stop_propagation
        super().__init__(pm_only=pm_only, group_only=group_only, func=func)

    def filter(self, event: 'Command.Event'):
        if not filter_pm_group_only(self, event):
            return False
        message: Message = event.message
        client: BotClient = event.client
        if message.out or message.fwd_from:
            return
        if isinstance(message.to_id, types.PeerChannel) and message.chat.broadcast:
            return
        try:
            full_command, *args = message.raw_text.split(maxsplit=1)
        except ValueError:
            return
        if full_command[0] != self.prefix:
            return
        command, _, mention = full_command[1:].partition('@')
        if self.regex:
            match = self.regex.fullmatch(command)
            if not match:
                return
            event.pattern_match = match
        elif command.lower() != self.command.lower():
            return
        if mention and mention.lower() != client.me.username.lower():
            return
        event.command = command
        event.args = args[0] if args else ''
        return True

    class Event(NewMessage.Event):
        client: BotClient
        command: str
        args: str

        def __init__(self, message):
            super().__init__(message)
            self.command = None
            self.args = None


@name_inner_event
class SelfAdded(events.ChatAction):
    def filter(self, event: 'SelfAdded.Event'):
        if not event.user_added:
            return
        if event.client.me.id not in [x.id for x in event.users]:
            return
        return super().filter(event)

    class Event(events.ChatAction.Event):
        client: BotClient


@name_inner_event
class SelfDeleted(events.ChatAction):
    def filter(self, event: 'SelfDeleted.Event'):
        if not event.user_kicked and not event.user_left:
            return
        if event.client.me.id not in [x.id for x in event.users]:
            return
        return super().filter(event)

    class Event(events.ChatAction.Event):
        client: BotClient


@name_inner_event
class CallbackQuery(events.CallbackQuery):
    def __init__(
        self,
        pattern=None,
        *,
        chats=None,
        blacklist_chats=False,
        func: 'Callable[[NewMessage.Event], bool]' = None,
        data=None,
        bytes_pattern=False,
        auto_answer=True,
        auto_error_message=True,
    ):
        EventBuilder.__init__(self, chats, blacklist_chats=blacklist_chats, func=func)
        if data is not None and pattern is not None:
            raise ValueError('Only pass either data or pattern not both.')

        self.bytes_pattern = bytes_pattern
        if pattern is not None:
            if bytes_pattern and isinstance(pattern, str):
                pattern = pattern.encode('utf-8')
            self.pattern = re.compile(pattern)
        else:
            self.pattern = None
        if data is not None:
            if bytes_pattern and isinstance(data, str):
                data = data.encode('utf-8')
            self.data = data
        else:
            self.data = None

        self.auto_answer = auto_answer
        self.auto_error_message = auto_error_message

        self._no_check = all(
            x is None
            for x in (
                self.chats,
                self.func,
                self.pattern,
                self.data,
            )
        )

    def filter(self, event: 'CallbackQuery.Event'):
        # We can't call super().filter(...) because it ignores chat_instance
        if self._no_check:
            return event

        if self.chats is not None:
            inside = event.query.chat_instance in self.chats
            if event.chat_id:
                inside |= event.chat_id in self.chats

            if inside == self.blacklist_chats:
                return

        data = (
            event.query.data if self.bytes_pattern else event.query.data.decode('utf-8')
        )
        if self.pattern:
            event.data_match = event.pattern_match = self.pattern.match(data)
            if not event.data_match:
                return
        if self.data is not None:
            if self.data != data:
                return

        if self.func:
            # Return the result of func directly as it may need to be awaited
            return self.func(event)
        return True

    class Event(events.CallbackQuery.Event):
        client: BotClient
        pattern_match: re.Match | None
        data_match: re.Match | None
        query: types.UpdateBotCallbackQuery

        async def get_message(self) -> Message:
            return await self.client.get_messages(self.chat_id, ids=self.message_id)


@name_inner_event
class GroupUpgraded(EventBuilder):
    @classmethod
    def build(cls, update, others=None, self_id=None):
        if (
            isinstance(update, tl.types.UpdateNewChannelMessage)
            and isinstance(update.message, tl.types.MessageService)
            and isinstance(
                update.message.action, tl.types.MessageActionChannelMigrateFrom
            )
        ):
            return cls.Event(update.message, update.message.action.chat_id)

    class Event(EventCommon):
        client: BotClient
        message: tl.types.MessageService
        old_group_id: int

        def __init__(self, message, old_group_id):
            super().__init__(chat_peer=message.peer_id, msg_id=message.id)
            self.message = message
            self.old_group_id = old_group_id

        def _set_client(self, client):
            super()._set_client(client)
            m = self.message
            m._finish_init(client, self._entities, None)


__all__ = [
    'EventHandler',
    'MiddlewareCallback',
    'Middleware',
    'BotClient',
    'BotRouter',
    'Message',
    'NewMessage',
    'Command',
    'SelfAdded',
    'CallbackQuery',
    'GroupUpgraded',
]
