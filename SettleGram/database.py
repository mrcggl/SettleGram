from pymongo import MongoClient

client_db = MongoClient('mongodb', 27017)
db = client_db.settlegram
expense_groups = db.expense_groups
pending_expenses = db.pending_expenses
