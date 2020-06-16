import emoji
from pydantic import BaseModel, validator
from errors import ClosedGroup
from typing import List, Optional, DefaultDict
from collections import defaultdict, namedtuple


# REMEMBER: pydantic is a parsing library, not a validation one. It aims to have the correct output type.
# TelegramUser


class TelegramUser(BaseModel):
    # Properties common to all groups from Telegram
    id: int = 0
    username: str = None
    name: Optional[str] = None
    last_name: Optional[str] = None

    # Properties of the application:
    # paymentType: paypal, revolut, satispay, PSD2 auth or manual, IBAN
    payment_type: str = None
    default_currency: str = None

    # Property of a group
    active_groups: DefaultDict[str, bool] = defaultdict(bool)


class Payment(BaseModel):
    from_whom: TelegramUser
    to_whom: TelegramUser
    amount: float
    currency: str

    @validator('amount')
    def amount_check(cls, v):
        return round(v, 2)

    def __str__(self) -> str:
        msg: str = ''
        if self.from_whom.name:
            msg += "**From**: {} ".format(self.from_whom.name)
        elif self.from_whom.username:
            msg += "**From**: {} ".format(self.from_whom.username)
        else:
            msg += "**From**: {} ".format(self.from_whom.id)
        if self.to_whom.name:
            msg += " **To**: {} ".format(self.to_whom.name)
        elif self.to_whom.username:
            msg += " **To**: {} ".format(self.to_whom.username)
        else:
            msg += " **To**: {} ".format(self.to_whom.id)
        msg += " **Amount**: {} {} ".format(self.amount, self.currency)
        return msg


class Expense(BaseModel):
    who_paid: TelegramUser
    for_whom: List[TelegramUser]
    amount: float
    currency: str
    purpose: str

    @validator('amount')
    def amount_check(cls, v):
        return round(v, 2)

    def __str__(self) -> str:
        msg: str = ''
        msg += "**Payer**: {}\n".format(self.who_paid.name)
        msg += "**Amount**: {} {}".format(self.amount, self.currency)
        msg += "\n**Purpose**: "
        msg += emoji.emojize(":{}:".format(self.purpose))
        msg += "\n**For whom**: "
        for member in self.for_whom:
            msg += "{} ".format(member.name)
        return msg


class ExpenseGroup(BaseModel):
    id: int = id
    name: str = ''
    members: List[TelegramUser] = []
    expenses: List[Expense] = []
    payments: List[Payment] = []
    balance: DefaultDict[str, float] = defaultdict(float)

    def add_chat_member(self, new_member: TelegramUser):
        member = self.__get_member_from_id__(new_member.id)
        if member:
            self.members.remove(member)
            member.active_groups[str(self.id)] = True
            self.members.append(member)
        else:
            new_member.active_groups[str(self.id)] = True
            self.members.append(new_member)

    def disable_chat_member(self, user_id: int):
        member = next(filter(lambda x: x.id == user_id, self.members), None)
        if member:
            self.members.remove(member)
            member.active_groups[str(self.id)] = False
            self.members.append(member)

    def enable_chat_member(self, user_id: int):
        member = next(filter(lambda x: x.id == user_id, self.members), None)
        if member:
            self.members.remove(member)
            member.active_groups[str(self.id)] = True
            self.members.append(member)

    def add_expense(self, expense: Expense):
        self.expenses.append(expense)
        self.__update_balance__()

    def open_group(self):
        for member in self.members:
            self.enable_chat_member(member.id)

    def close_group(self):
        for member in self.members:
            self.disable_chat_member(member.id)
        self.__generate_payments__()

    def __update_balance__(self):
        balance = defaultdict(float)
        for expense in self.expenses:
            debt = round(expense.amount / len(expense.for_whom), 2)
            for debtor in expense.for_whom:
                balance[str(debtor.id)] -= debt
            creditor = expense.who_paid
            credit = expense.amount
            balance[str(creditor.id)] += round(credit, 2)
        self.balance = balance

    def get_balance(self):
        msg = '** Expense Group Balance**\n'
        for member_id, balance in self.balance.items():
            member = self.__get_member_from_id__(member_id)
            if member.name:
                msg += '{} '.format(member.name)
            elif member.username:
                msg += '{}'.format(member.username)
            else:
                msg += '{}'.format(member.id)
            # ToDo fix with proper currency handling
            msg += '{} {}\n'.format(round(balance, 2), '$')

        return msg

    def mark_paid(self, idx):
        payment = self.payments.pop(idx)
        new_expense = Expense(who_paid=payment.from_whom,
                amount=payment.amount,
                purpose='settlement',
                currency=payment.currency,
                for_whom=payment.to_whom)
        self.expenses.append(new_expense)

    def get_payments(self):
        msg = '** Expense Group Settlement Payments**\n'
        for i, payment in enumerate(self.payments):
            msg += '{}. '.format(i) + str(payment) + '\n'
        return msg

    def __get_member_from_id__(self, member_id):
        return next(filter(lambda x: str(x.id) == str(member_id), self.members), None)

    def __generate_payments__(self):
        self.payments = []
        self.__update_balance__()
        list_member_balance_tuple = []

        for member_id, balance in self.balance.items():
            member = self.__get_member_from_id__(member_id)

            list_member_balance_tuple.append(Packaged(member, balance))
        list_member_balance_tuple.sort(key=lambda x: x.balance, reverse=True)

        while True:
            try:
                first = list_member_balance_tuple.pop(0)
                last = list_member_balance_tuple.pop()

                if abs(first.balance) > abs(last.balance):
                    first.balance += last.balance
                    payment = \
                        Payment(from_whom=last.member, to_whom=first.member, amount=-last.balance, currency='$')
                    self.payments.append(payment)
                    list_member_balance_tuple.append(first)

                elif abs(first.balance) == abs(last.balance):
                    payment = \
                        Payment(from_whom=last.member, to_whom=first.member, amount=-last.balance, currency='$')
                    self.payments.append(payment)
                else:
                    last.balance += first.balance
                    payment = \
                        Payment(from_whom=last.member, to_whom=first.member, amount=first.balance, currency='$')
                    self.payments.append(payment)
                    list_member_balance_tuple.append(last)
                list_member_balance_tuple.sort(key=lambda x: x.balance, reverse=True)
            except IndexError:
                break

class Packaged:

    def __init__(self, member, balance):
        self.member = member
        self.balance = round(balance, 2)

    def __repr__(self):
        return '{} {}'.format(self.member, self.balance)