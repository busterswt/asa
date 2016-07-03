import os
import hashlib
from clients import keystone
from keystoneclient import utils
import random

def generate_password(len):
    random_data = os.urandom(128)
    password = hashlib.md5(random_data).hexdigest()[:len]

    return password

def generate_random_device():
    range_start = 10**(6-1)
    range_end = (10**6)-1
    return str(random.randint(range_start, range_end))

def verify_project(project_name_or_id):
    # Verify the existence of a project based on project name or ID
    # For Moonshine, project name == CORE account number

    try:
        project = utils.find_resource(keystone.projects,project_name_or_id)

        if project is not None:
            return project
        else:    
            project = keystone.projects.get(project_name_or_id)
            if project is not None:
                return project
    except: # Did not find project
	return None

def create_project(project_name):
    project = keystone.projects.create(name=project_name,
                        domain='Default',
			description="Account %s created by Moonshine" % project_name,
                        enabled=True,
			parent=None)
    return project

def create_user(account_number,tenant_id,password):
    user_name = "User_" + str(account_number)
    new_user = keystone.users.create(name=user_name,
                password=password,
                email="moonshine@learningneutron.com", tenant_id=tenant_id)
    return new_user

