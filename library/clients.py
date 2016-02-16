#!/usr/bin/env python
# Boilerplate for preparing client objects
import os, sys
from keystoneclient import session as ksession
from keystoneclient.auth.identity import v3
from keystoneclient.v3 import client as kclient
from neutronclient.v2_0 import client as nclient
from novaclient import client as novaclient

_keystone_creds = {}
try:
    _keystone_creds['username'] = os.environ['OS_USERNAME']
    _keystone_creds['password'] = os.environ['OS_PASSWORD']
    _keystone_creds['auth_url'] = os.environ['OS_AUTH_URL']
    _keystone_creds['project_name'] = os.environ['OS_TENANT_NAME']
    _keystone_creds['project_id'] = os.environ['OS_PROJECT_ID']
    _keystone_creds['user_domain_id'] = os.environ['OS_USER_DOMAIN_ID']
except KeyError, e:
    print ("Openstack environment variable %s is not set!") % e
    sys.exit(1)

auth = v3.Password(**_keystone_creds)
session = ksession.Session(auth=auth)
keystone = kclient.Client(session=session)
neutron = nclient.Client(session=session)
nova = novaclient.Client("2.9",session=session)
