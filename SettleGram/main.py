from telethon import TelegramClient, events
from telethon.tl.custom import Button
from telethon.errors.rpcerrorlist import PeerIdInvalidError
from telethon.events import NewMessage, CallbackQuery, ChatAction
import os
import spacy
from spacy.matcher import Matcher
import logging
from models import Expense, ExpenseGroup, TelegramUser
from parsing import *
from crud import *
from internal import *
from errors import MalformedMessage, TelegramUserNotActive, ClosedGroup
from database import expense_groups, pending_expenses

# SET UP LOGGING
logging.basicConfig(format='[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# SET UP NLP Processing
nlp = spacy.load("it_core_news_sm")
matcher = Matcher(nlp.vocab)
matcher.add('nuova_spesa', None, nuova_spesa)
# Group management
matcher.add('disable_member', None, disable_member)
matcher.add('enable_member', None, enable_member)
matcher.add('open_group', None, open_group)
matcher.add('close_group', None, close_group)
# Settlement
matcher.add('get_balance', None, get_balance)
matcher.add('get_payments', None, get_payments)

# SET UP Telegram Client
token_key = os.getenv('TOKEN_KEY')
api_id = os.getenv('API_ID')
api_hash = os.getenv('API_HASH')
tg_client = TelegramClient('bot', api_id, api_hash).start(bot_token=token_key)


# Assumptions to start:
# - At every chat there is a corresponding expense sharing group
# - All members of the expense sharing group are in the chat (no external members)
# - Since Telegram enforces unique username, i.e username is a digital identity (actual it can change..),
#   we will username as unique member identity as well

# ToDo
# -
# - Fix handling of group closure and payments
# - NLP has many problem..
# - Add set reminder function in parsing
# - Add reminder function and send payment reminder message
# - Add payments handling via private message (paid/settled)
# - Create new repo, clean all secrets and develop it in the open without UI, with docker-compose deployment


@tg_client.on(events.NewMessage(incoming=True, forwards=False))
async def new_message(event: NewMessage):
    chat_id = event.chat_id
    bot_called = event.message.mentioned
    try:
        # Check if group exist ... if not, it is a one to one chat or an error!
        group = get_group(expense_groups, chat_id)
        if group:
            msg = event.message
            doc = nlp(msg.raw_text)
            matches = matcher(doc)
            for match_id, start, end in matches:
                string_id = nlp.vocab.strings[match_id]

                if string_id in {'add_expense', 'nuova_spesa'}:
                    # Create new expense
                    new_expense = crea_nuova_spesa(doc)

                    # find who_paid by name or by username
                    username_members = list(filter(lambda x: x.username == new_expense["who_paid"], group.members))
                    name_members = list(filter(lambda x: new_expense["who_paid"] == x.name, group.members))

                    if len(username_members) == 1 and len(name_members) == 0:
                        if username_members[0].active_groups[str(group.id)]:
                            who_paid = username_members[0]
                        else:
                            raise TelegramUserNotActive
                    elif len(name_members) == 1 and len(username_members) == 0:
                        if name_members[0].active_groups[str(group.id)]:
                            who_paid = name_members[0]
                        else:
                            raise TelegramUserNotActive
                    elif new_expense['who_paid'] == 'MSG_SENDER':
                        member = group.__get_member_from_id__(event.from_id)
                        who_paid = member
                    else:
                        raise MalformedMessage('Impossible to determine who paid')

                    # find list of for_whom by name or by username
                    for_whom = list()
                    for string_id in new_expense['for_whom']:
                        if string_id in {'everyone', 'everybody', 'tutti'}:
                            for_whom = list(filter(lambda x: x.active_groups[str(group.id)], group.members))
                            break
                        username_members = list(filter(lambda x: x.username == string_id, group.members))
                        name_members = list(filter(lambda x: x.name == string_id, group.members))

                        if len(username_members) == 1 and len(name_members) == 0:
                            if username_members[0].active_groups[str(group.id)]:
                                for_whom.append(username_members[0])
                            else:
                                raise TelegramUserNotActive
                        elif len(name_members) == 1 and len(username_members) == 0:
                            if name_members[0].active_groups[str(group.id)]:
                                for_whom.append(name_members[0])
                            else:
                                raise TelegramUserNotActive
                        else:
                            raise MalformedMessage('Impossible to determine for who it was paid')

                    expense = Expense(who_paid=who_paid,
                                      for_whom=for_whom,
                                      amount=new_expense['amount'],
                                      currency=new_expense['currency'],
                                      purpose=new_expense['purpose'])

                    # Confirm or Deny
                    chat = await event.get_input_chat()
                    cb_result = await tg_client.send_message(chat, str(expense), buttons=[
                        [Button.inline('Confirm', data=None), Button.inline('Deny', data=None)]
                    ])
                    # Global queue for pending msg
                    create_pending_expense(pending_expenses, expense, event.message.id, cb_result.id, chat_id)
                elif string_id == 'disable_member' and bot_called:
                    name_or_username = remove_member_from_group(doc)
                    member = find_user(name_or_username, group)
                    group.disable_chat_member(member.id)
                    update_group(expense_groups, group)
                    await event.reply('User disabled')
                elif string_id == 'enable_member' and bot_called:
                    name_or_username = add_member_to_group(doc[1:])
                    print(name_or_username)
                    member = find_user(name_or_username, group)
                    group.enable_chat_member(member.id)
                    update_group(expense_groups, group)
                    await event.reply('User enabled')
                elif string_id == 'get_balance' and bot_called:
                    await tg_client.send_message(chat_id, group.get_balance())
                    pass
                elif string_id == 'open_group' and bot_called:
                    group.open_group()
                    update_group(expense_groups, group)
                elif string_id == 'close_group' and bot_called:
                    chat = await event.get_input_chat()
                    cb_result = await tg_client.send_message(chat,
                                                             'Are you sure you want to close the expense group?',
                                                             buttons=[
                                                                 [Button.inline('Close', data=None),
                                                                  Button.inline('Do not close', data=None)]
                                                             ])
                elif string_id == 'get_payments' and bot_called:
                    #ToDo
                    pass

    except MalformedMessage:
        await tg_client.send_message(chat_id, "The message was malformed: retry")
    except TelegramUserNotActive:
        await tg_client.send_message(chat_id, "One of the involved user is not anymore active in this group")
    except ClosedGroup:
        await tg_client.send_message(chat_id, "The group is closed to new expenses")
    except KeyError:
        await tg_client.send_message(chat_id, "The message was malformed, retry")


@tg_client.on(events.CallbackQuery)
async def answer(event: CallbackQuery):
    chat_id = event.chat_id
    msg_id = event.message_id
    if event.data == b'Confirm':
        pending_expense = get_pending_expense(pending_expenses, msg_id, chat_id)
        expense = Expense(**pending_expense['expense'])
        original_msg_id = pending_expense['original_msg_id']
        group = get_group(expense_groups, chat_id)
        group.add_expense(expense)
        update_group(expense_groups, group)
        await event.answer(message='Expense added')
        await event.delete()
        await tg_client.send_message(chat_id, '**Expense Added**\n' + str(expense))

    elif event.data == b'Deny':
        pending_expense = get_pending_expense(pending_expenses, msg_id, chat_id)
        original_msg_id = pending_expense['original_msg_id']
        await event.answer(message='Expense not added')
        await event.delete()
        await tg_client.send_message(chat_id, '**Expense not Added**', reply_to=original_msg_id)

    elif event.data == b'Close':
        group = get_group(expense_groups, chat_id)
        group.close_group()
        update_group(expense_groups, group)
        await event.delete()
        await tg_client.send_message(chat_id, group.get_payments())
        for payment in group.payments:
            try:
                receiver = await tg_client.get_input_entity(payment.from_whom.username)
                receiver = await tg_client.get_entity(receiver)
                await tg_client.send_message(receiver,
                                         message='Hi {}! You should send a payment of {} {} to {} to settle the expenses of {}'.format(
                                             payment.from_whom.name,
                                             payment.amount,
                                             payment.currency,
                                             payment.to_whom.name,
                                             group.name
                                         ))
            except PeerIdInvalidError:
                continue
    elif event.data == b'Do not close':
        await tg_client.send_message(chat_id, '**Group not closed**')
        await event.delete()

    del_pending_expense(pending_expenses, msg_id, chat_id)


@tg_client.on(events.ChatAction)
async def on_action(event: ChatAction.Event):
    chat_id = event.chat_id
    print(event)
    user = await event.get_user()
    if event.action_message is None:
        pass
    elif event.created:
        # New chat! Let's add all user but the bot
        # Let's create a new group and add all members of the channel who aren't bots
        group = ExpenseGroup(id=chat_id, name=event.chat.title)
        users = await event.get_users()
        for chat_member in users:
            if not chat_member.bot:
                telegram_user = TelegramUser(id=chat_member.id,
                                             username=chat_member.username,
                                             name=chat_member.first_name)
                group.add_chat_member(telegram_user)
        create_group(expense_groups, group)
    elif not user.is_self and not user.bot:
        group = get_group(expense_groups, chat_id)
        # If the user exited the chat, remove it from the expense group
        if event.user_left or event.user_kicked:
            user = event.user
            group.disable_chat_member(user.id)
            update_group(expense_groups, group)
        # If a new user joined the chat, either alone or by being added:
        if event.user_joined or event.user_added:
            chat_member = event.user
            telegram_user = TelegramUser(id=chat_member.id,
                                         username=chat_member.username,
                                         name=chat_member.first_name)
            group.add_chat_member(telegram_user)
        update_group(expense_groups, group)
    elif user.is_self and event.user_added:
        # the bot was added to the chat
        # Let's create a new group and add all members of the channel who aren't bots
        # Check if group exist?
        group = get_group(expense_groups, chat_id)
        if not group:
            group = ExpenseGroup(id=chat_id, name=event.chat.title)
            async for chat_member in tg_client.iter_participants(entity=chat_id):
                if not chat_member.bot:
                    telegram_user = TelegramUser(id=chat_member.id,
                                                 username=chat_member.username,
                                                 name=chat_member.first_name)
                    group.add_chat_member(telegram_user)
            create_group(expense_groups, group)
    elif event.new_title:
        group = get_group(expense_groups, chat_id)
        if group:
            group.name = event.new_title
            update_group(expense_pattern, group)


tg_client.start()

tg_client.run_until_disconnected()
