from pymongo.collection import Collection
from models import TelegramUser, ExpenseGroup, Expense


# CRUD: Create, Read, Update, Delete
# CREATE

def create_group(db: Collection, group: ExpenseGroup):
    result = db.insert_one(group.dict())


def create_pending_expense(db: Collection, expense: Expense, original_msg_id: int, callback_msg_id: int, group_id: int):
    pending = {'original_msg_id': original_msg_id,
               'callback_msg_id': callback_msg_id, 'expense': expense.dict(), 'group_id': group_id}
    result = db.insert_one(pending)


def create_user(db: Collection, user: TelegramUser):
    result = db.insert_one(user)


# READ
def get_user(db: Collection, user_id: int) -> TelegramUser:
    result = db.find_one({'id': user_id})
    return TelegramUser(**result) if result else None


def get_pending_expense(db: Collection, callback_msg_id: int, group_id: int):
    return db.find_one({'callback_msg_id': callback_msg_id, 'group_id': group_id})


def get_group(db: Collection, group_id: int) -> ExpenseGroup:
    result = db.find_one({'id': group_id})
    return ExpenseGroup(**result) if result else None


# UPDATE
def update_group(db: Collection, group: ExpenseGroup):
    db.delete_one({'id': group.id})
    db.insert_one(group.dict())
    result = db.find_one({'id': group.id})


# DELETE
def del_pending_expense(db: Collection, callback_msg_id: int, group_id: int):
    db.delete_one({'callback_msg_id': callback_msg_id, 'group_id': group_id})
