import os
import hashlib
from clients import keystone
import random

def generate_password(len):
    random_data = os.urandom(128)
    password = hashlib.md5(random_data).hexdigest()[:len]

    return password

def generate_random_account():
    range_start = 10**(6-1)
    range_end = (10**6)-1
    return random.randint(range_start, range_end)

def create_project(account_number):
    account_name = "Account_" + str(account_number)
    new_project = keystone.projects.create(name=account_name,
                        domain='Default',
			description="Created by ASA script",
                        enabled=True,
			parent=None)
    return new_project

def create_user(account_number,tenant_id,password):
    user_name = "User_" + str(account_number)
    new_user = keystone.users.create(name=user_name,
                password=password,
                email="cloudmaster@learningneutron.com", tenant_id=tenant_id)
    return new_user

