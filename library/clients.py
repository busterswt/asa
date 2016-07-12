#!/usr/bin/env python
# Boilerplate for preparing client objects
import os, sys, logging
from urlparse import urlparse
from keystoneclient import session, exceptions, utils
from keystoneclient.exceptions import AuthorizationFailure, Unauthorized

# v2 client
from keystoneclient.auth.identity import v2
from keystoneclient.v2_0 import client as k2client

# v3 client
from keystoneclient.auth.identity import v3
from keystoneclient.v3 import client as k3client

# Neutron client
from neutronclient.v2_0 import client as nclient
# Instantiate the Keystone client

# Nova client
from novaclient import client as novaclient

def create_session(username,password,auth_url,project_id,user_domain_id,project_domain_id,*args):
    # Creates a new session
    try:
        _keystone_creds['username'] = username
        _keystone_creds['password'] = password
        _keystone_creds['auth_url'] = auth_url
	_keystone_creds['project_id'] = project_id
#        _keystone_creds['project_name'] = project_name
        _keystone_creds['user_domain_id'] = user_domain_id
        _keystone_creds['project_domain_id'] = project_domain_id
    except KeyError, e:
            print e
            sys.exit(1)
    auth = v3.Password(**_keystone_creds)
    sess = session.Session(auth=auth)
    return sess

def get_keystone_creds():
    # v3 only
    try:
        _keystone_creds = {}
        _keystone_creds['username'] = os.environ['OS_USERNAME']
        _keystone_creds['password'] = os.environ['OS_PASSWORD']
	_keystone_creds['auth_url'] = os.environ['OS_AUTH_URL']
#	_keystone_creds['project_name'] = os.environ['OS_PROJECT_NAME']
	_keystone_creds['project_id'] = os.environ['OS_PROJECT_ID']
	_keystone_creds['user_domain_id'] = os.environ['OS_USER_DOMAIN_NAME']
	_keystone_creds['project_domain_id'] = os.environ['OS_PROJECT_DOMAIN_NAME']    
    except KeyError, e:
            print ("Openstack environment variable %s is not set!") % e
            sys.exit(1)

#    print _keystone_creds # Debugging
    return _keystone_creds


# Evaluate the auth URL to determine if user is using v2 or v3 Keystone API
try:
    u = urlparse(os.environ['OS_AUTH_URL'])
except Exception, e:
    print ("Error! Unable to read OS_AUTH_URL. Please source credentials.")
    sys.exit(1)

if "v2.0" in u.path:
    try:
	_keystone_creds = {}
	try:
	    _keystone_creds['username'] = os.environ['OS_USERNAME']
	    _keystone_creds['password'] = os.environ['OS_PASSWORD']
	    _keystone_creds['auth_url'] = os.environ['OS_AUTH_URL']
	    _keystone_creds['tenant_name'] = os.environ['OS_TENANT_NAME']
	except KeyError, e:
	    print ("Openstack environment variable %s is not set!") % e
	    sys.exit(1)
	auth = v2.Password(**_keystone_creds)
	sess = session.Session(auth=auth)
	keystone = k2client.Client(session=sess)
    except AuthorizationFailure as auf:
        print(auf.message)
    except Unauthorized as unauth:
        print(unauth.message)
elif "v3" in u.path:
    try:
        _keystone_creds = get_keystone_creds()
	sess = create_session(**_keystone_creds)
	keystone = k3client.Client(session=sess)
#	print _keystone_creds # Debugging
    except AuthorizationFailure as auf:
        print(auf.message)
    except Unauthorized as unauth:
        print(unauth.message)

# Instantiate Neutron client
try:
    neutron = nclient.Client(session=sess)
except:
    print "Error: Unable to instantiate a Neutron client!"

# Instantiate Nova client
def make_nova_client(session):
    try:
        nova = novaclient.Client('2',session=session)
	return nova
    except:
        print "Error: Unable to instantiate a Nova client!"
