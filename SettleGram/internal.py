from errors import *


def find_user(name_or_username, group):
    username_member = next(filter(lambda x: x.username == name_or_username, group.members), None)
    name_member = next(filter(lambda x: x.name == name_or_username, group.members), None)

    if username_member:
        return username_member
    elif name_member:
        return name_member
    else:
        raise MalformedMessage('Impossible to determine who paid')
