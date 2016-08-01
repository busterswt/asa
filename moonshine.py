#!/usr/bin/env python

import sqlite3, os
import netaddr, base64
import requests, json, sys
import argparse, time, logging
from prettytable import PrettyTable
import library.neutron as neutronlib
from library.database import *
#import library.config as configlib
import library.nova as novalib
import library.keystone as keystonelib
from library.printf import printf
# Config libraries
import library.config.asa as asa
import library.config.ltm as ltm
import library.config.netscaler as netscaler
import library.config.srx as srx
import library.config.csr as csr
import library.config.adx as adx

# Initialize global variables that will be used throughout
# Best practice? Dunno.
_networks = {}
_ports = {}
_metadata = {}
db_filename = './moonshine_db.sqlite'
schema_filename = './moonshine_db.schema'

def create_project(account_number):
    # (todo) Only create project when one doesn't exist for the account number being passed.
    # All devices associated with account will exist under respective project
    global _metadata

    # Check for existance of project
    os_project = keystonelib.verify_project(account_number)
    if os_project is not None:
	print "Existing project/account found! Associating devices with existing project %s..." % os_project.id
    else:
	print "Creating new project! Associating devices with new project..."
	try:
	     os_project = keystonelib.create_project(account_number)
	     quotas = novalib.set_quotas(os_project) # Set quotas
        except Exception, e:
    	    logging.exception("Unable to create project in Keystone! %s" % e)
    	    # (todo) rollback and exit gracefully

	# Set quotas for the new project
	try:
	    response = novalib.set_quotas(os_project)
	except Exception, e:
	    logging.exception("Unable to set quotas! %s" % e)

    _metadata.update({"account_number": account_number})
    # Return the project that will be used when creating resources
    return os_project

def create_networks(db_filename,payload):
    dbmgr = DatabaseManager(db_filename)

    network_blob = json.loads(payload)
    # Initialize json response
    response = {}
    response['data'] = []

    # Iterate through the networks to see if they exist
    for m_network in network_blob["networks"]:
	# Finds the true CIDR (bit boundary) for given CIDR/IP/Address
	real_cidr = str(netaddr.IPNetwork(m_network["cidr"]).cidr)

	# Validates a network matching env and cidr doesn't already exist.
	# (todo) How do we also validate the network name isn't used yet
	result = dbmgr.query("select count(*) from networks where cidr=? and environment_number=?", 
				(real_cidr,network_blob["environment_number"]))

	count = result.fetchone()
	if count[0] > 0: # If we encounter the network, do not create another one
	    response['message'] = "Error"
            response['error'] = "Network with CIDR %s already exists in environment %s. Not creating!" % (real_cidr,network_blob["environment_number"])
	    return response

	# Check to see if network name already exists
	result = dbmgr.query("select count(*) from networks where network_name=? and environment_number=?",
                                (m_network['network_name'],network_blob["environment_number"]))

        count = result.fetchone()
        if count[0] > 0: # If we encounter the network, do not create another one
            response['message'] = "Error"
            response['error'] = "Network with name %s already exists in environment %s. Not creating!" % (m_network['network_name'],network_blob["environment_number"])
            return response

	else: # Network does not exist in database. Create new network.
    	    try:
		network_args = {}
		# Use the network type set by user
		if m_network.get("network_type") is not None:
		    network_args["network_type"] = m_network["network_type"]
		# Use the segmentation id set by user
		if m_network.get("segmentation_id") is not None:
		    network_args["segmentation_id"] = m_network["segmentation_id"]

		# Creates the network in Neutron
                q_network = neutronlib.create_network(network_name=m_network["network_name"],
						**network_args) # need to set tenant id?

		# Creates the subnet in Neutron
		q_subnet = neutronlib.create_subnet(network_id=q_network["network"]["id"],
							cidr=real_cidr) # Need to set tenant id?

	        # Update sqlite database
	        try:
	    	    dbmgr.query("insert into networks (network_id,tenant_id,account_number,environment_number, \
					network_name,cidr,segmentation_id,network_type,subnet_id) values (?,?,?,?,?,?,?,?,?)", 
					([q_network["network"]["id"],q_network["network"]["tenant_id"],
					network_blob["account_number"],network_blob["environment_number"],
					m_network["network_name"],real_cidr,q_network["network"]["provider:segmentation_id"],
					q_network["network"]["provider:network_type"],q_subnet["subnet"]["id"]]))

		except Exception, e:
                    response['message'] = "Error"
                    response['error'] = "Unable to update local database. Moonshine and Neutron could be out of sync! %s" % e
                    return response

		network = {}
		network['account_number'] = network_blob["account_number"]
		network['environment_number'] = network_blob["environment_number"]
		network['network_name'] = m_network["network_name"]
		network['cidr'] = real_cidr
		network['network_id'] = q_network["network"]["id"]
		network['subnet_id'] = q_subnet["subnet"]["id"]
		network['network_type'] = q_network["network"]["provider:network_type"]
		network['segmentation_id'] = q_network["network"]["provider:segmentation_id"]
		response['data'].append(network)    

	    except Exception, e:
	        # (todo) Rollback neutron net-create, too?
		response['message'] = "Error"
                response['error'] = "%s" % e
		return response

    response['message'] = "Success"
    return response
	
def create_ports(db_filename,payload):
    dbmgr = DatabaseManager(db_filename)
    port_blob = json.loads(payload)

    # Initialize json response
    response = {}
    response['data'] = []

    for m_port in port_blob["ports"]:

        # Validates a port matching device number and network name doesn't already exist
        data = dbmgr.query("select count(*) from ports where device_number=? and environment_number=? and network_name=?",
                                (port_blob["device_number"],port_blob["environment_number"],m_port["network_name"]))

        count = data.fetchone()
        if count[0] > 0:
	    response['message'] = "Error"
            response['error'] = "Device '%s' already has a port on the '%s' network in environment %s! Not creating!" % (port_blob["device_number"],m_port["network_name"],port_blob["environment_number"])
            return response
        else:
	    try:
		# Let's see if using the generic outside or management network. If so, those aren't bound to environments
		# (todo) Find a better way to do this
		if m_port["network_name"] in ('outside', 'management'):
		    data = dbmgr.query("select network_id from networks where network_name=?",
                                ([m_port["network_name"]]))
		else:
		    # Get the network id based on environment number and network name
		    data = dbmgr.query("SELECT network_id FROM networks WHERE account_number=? AND environment_number=? AND network_name=?",
                                ([port_blob["account_number"],port_blob["environment_number"],m_port["network_name"]]))

		# Validate a network ID is returned
	        network_id = data.fetchone() # How to return none if not found
		if network_id is None:	
		    response['message'] = "Error"
		    response['error'] = "Error! Network '%s' in environment '%s' does not exist in the database. Please create the network and try again." % \
                                (m_port["network_name"],port_blob["environment_number"])
#		    continue # Break out and process next port
		    return response

                port_args = {}
                # Use the fixed ip set by user
		# (todo) validate the fixed IP matches a subnet cidr of the network
                if m_port.get("ip_address") is not None:
                    port_args["ip_address"] = m_port["ip_address"]

		# Use port security boolean set by user
		if m_port.get("port_security_enabled") is not None:
		    port_args["port_security_enabled"] = m_port["port_security_enabled"]

                # Creates the port in Neutron
                q_port = neutronlib.create_port(network_id=network_id[0],**port_args) # need to set tenant id

                # Update sqlite database
                try:
                    dbmgr.query("insert into ports (port_id,network_id,tenant_id,account_number,environment_number, \
                                        network_name,fixed_ip,device_number,port_name) values (?,?,?,?,?,?,?,?,?)",
                                        ([q_port["port"]["id"],q_port["port"]["network_id"],q_port["port"]["tenant_id"],
                                        port_blob["account_number"],port_blob["environment_number"],
                                        m_port["network_name"],q_port["port"]["fixed_ips"][0]["ip_address"],
                                        port_blob["device_number"],m_port["network_name"]]))
                except Exception, e:
                    response['message'] = "Error"
                    response['error'] = "Unable to update local database. Moonshine and Neutron could be out of sync! %s" % e
                    return response

                port = {}
                port['account_number'] = port_blob["account_number"]
                port['environment_number'] = port_blob["environment_number"]
		port['device_number'] = port_blob["device_number"]
		port['port_id'] = q_port["port"]["id"]
                port['port_name'] = m_port["network_name"]
		port['network_id'] = q_port["port"]["network_id"]
		port['tenant_id'] = q_port["port"]["tenant_id"]
		port['network_name'] = m_port["network_name"]
		port['fixed_ip'] = q_port["port"]["fixed_ips"][0]["ip_address"]
                response['data'].append(port)
            except Exception, e:
                # (todo) Rollback neutron port-create, too?
                response['message'] = "Error"
                response['error'] = "%s" % e
                return response

    response['message'] = "Success"
    return response

def create_instance(db_filename,payload):
    dbmgr = DatabaseManager(db_filename)
    instance_blob = json.loads(payload)

    # Initialize json response
    response = {}
    response['data'] = []

    # (todo) Check to see if an instance with that device number exists!

    # Validates a port matching device number and network name exists
    # Otherwise, kick back to the user to create the port first
    port_exists = True # Initialize value
    for m_port in instance_blob["ports"]:
        data = dbmgr.query("select count(*) from ports where device_number=? and environment_number=? and network_name=?",
                                (instance_blob["device_number"],instance_blob["environment_number"],m_port["network_name"]))

        count = data.fetchone()
        if count[0] < 1:
            response['message'] = "Error"
            response['error'] = "Device '%s' does not have a port in the '%s' network in environment %s! Please create the port and try again." % \
					(instance_blob["device_number"],m_port["network_name"],instance_blob["environment_number"])
	    status_code = "400"
	    port_exists = False
            return response, status_code
#	continue # Continue the loop

    # If we're here, it should mean all ports are accounted for.
    # (todo) ensure that we also check for peer ports, too, above. Those will be needed to generate the configuration. 
    if port_exists:
        try:
            # Find the corresponding port IDs and build a list
            # (todo) optimize this
            ports = []
            for m_port in instance_blob["ports"]:
    	        data = dbmgr.query("select port_id from ports where device_number=? and environment_number=? and network_name=?",
        	                      	(instance_blob["device_number"],instance_blob["environment_number"],m_port["network_name"]))
	        port = data.fetchone()
	        ports.append(port[0])
	except Exception, e:
	    response['message'] = "error"
            response['error'] = "Unable to gather ports for instance!"
            status_code = "400"
	    return response, status_code

    # Load additional config options like image IDs and flavor IDs
    try:
        config = load_config()
	image_id = config[instance_blob['device_type']][instance_blob['device_model']]['image']
	flavor_id = config[instance_blob['device_type']][instance_blob['device_model']]['flavor']
    except Exception, e:
	response['message'] = "error"
        response['error'] = "Unable to determine image or flavor id!"
        status_code = "400"
        logging.exception("Unable to load configuration file! %s" % e)
	return response, status_code

    # Generate device configuration
    device_config = generate_configuration(db_filename,instance_blob)

    # Determine availability zone
    if 'secondary' in instance_blob["device_priority"]:
	zone = 'ZONE-B'
    else:
	zone = 'ZONE-A'

    # Boot the instance
    try:
        hostname = instance_blob["environment_number"] + '-' + instance_blob["account_number"] + '-' + instance_blob["device_number"]

	# Due to Nova bug, we need to update the hostnames on the ports
	for port_id in ports:
	    neutronlib.update_port_dns_name(port_id,hostname)

        if 'asav' in instance_blob['device_model']:
	    instance = novalib.boot_instance(name=hostname,image=image_id,flavor=flavor_id,config_drive='True',
					file_path='day0',file_contents=device_config,ports=ports,
                                        az=zone)
	elif 'csrv' in instance_blob['device_model']:
	    instance = novalib.boot_instance(name=hostname,image=image_id,flavor=flavor_id,config_drive="True",
                                        file_path='iosxe_config.txt',file_contents=device_config,ports=ports,
                                        az=zone)
        elif 'srx' in instance_blob['device_model']:
            print 'srx'
        elif 'netscaler' in instance_blob['device_model']:
            print 'citrix'
        elif 'ltm' in instance_blob['device_model']:
            instance = novalib.boot_instance(name=hostname,image=image_id,flavor=flavor_id,
                                        ports=ports,userdata=device_config,az=zone)
        elif 'vadx' in instance_blob['device_model']:
            instance = novalib.boot_instance(name=hostname,image=image_id,flavor=flavor_id,
                                        ports=ports,userdata=device_config,az=zone)

	# Update sqlite database
        try:
            dbmgr.query("insert into instances (instance_id,account_number,environment_number,device_number,device_name,device_type,device_model,device_priority) values (?,?,?,?,?,?,?,?)",
                         ([instance.id,instance_blob["account_number"],instance_blob["environment_number"],instance_blob["device_number"],hostname,
			instance_blob["device_type"],instance_blob['device_model'],instance_blob["device_priority"]]))

	    # Find the management port in local DB
            result = dbmgr.query("select port_id from ports where device_number=? and account_number=? and port_name='management'", 
				([instance_blob['device_number'],instance_blob['account_number']]))
            port_id = result.fetchone()[0]
            management_ip = neutronlib.get_fixedip_from_port(port_id)

        except Exception, e:
            response['message'] = "error"
            response['error'] = "Unable to update local database while booting the instance. Moonshine and Nova could be out of sync! %s" % e
            status_code = "400"
            return response, status_code

	server= {}
        server['account_number'] = instance_blob["account_number"]
        server['environment_number'] = instance_blob["environment_number"]
	server['device_number'] = instance_blob["device_number"]
	server['device_type'] = instance_blob["device_type"]
	server['device_model'] = instance_blob['device_model']
        server['hostname'] = hostname
        server['id'] = instance.id
	server['host'] = novalib.get_hypervisor_from_id(instance.id)
	server['management_ip'] = management_ip
	server['image_id'] = image_id
	server['flavor_id'] = flavor_id

        response['data'].append(server)
	response['message'] = 'success'
	status_code = "200"

	return response, status_code

    except Exception, e:
	response['message'] = 'error'
	response['error'] = "Unable to boot instance! %s" % e
	status_code = "400"
	return response, status_code

def generate_configuration(db_filename,instance_blob):
    """
    :desc: Generates device configuration. Not really pluggable. Only works with certain device types/models.
    """
    dbmgr = DatabaseManager(db_filename)

    # Determine if standalone, primary, secondary 
    # Generate port ids. Send to the individual device functions
    
    # Generate the list of ports needed to build config
    # Must be in exact order passed from user!
    self_ports = []
    peer_ports = []

    try:
        for m_port in instance_blob["ports"]:
            data = dbmgr.query("select port_id from ports where device_number=? and environment_number=? and network_name=?",
                                (instance_blob["device_number"],instance_blob["environment_number"],m_port["network_name"]))
            port = data.fetchone()
            self_ports.append(port[0])
#        print self_ports # Debug
    except Exception, e:
        logging.exception("Unable to build self port list when generating config! %s" % e)

    # Generate the list of peer port IDs (if applicable)
    if instance_blob.get("peer_device") is not None:
	try:
	    # Validate the peer has ports defined
	    data = dbmgr.query("select count(*) from ports where device_number=? and environment_number=?",
                                (instance_blob["peer_device"],instance_blob["environment_number"]))

            count = data.fetchone()
	    # (todo) Need to actually match the ports between devices. This is good enough for now.
	    # This ought to match the networks between devices
            if count[0] < 1:
                print "Device '%s' does not have any ports defined in environment %s! Please create the port and try again." % \
                                        (instance_blob["peer_device"],instance_blob["environment_number"])
	    else:
		for m_port in instance_blob["ports"]:
		    data = dbmgr.query("select port_id from ports where device_number=? and environment_number=? and network_name=?",
                               	        (instance_blob["peer_device"],instance_blob["environment_number"],m_port["network_name"]))
	            port = data.fetchone()
		    peer_ports.append(port[0]) 
                #print peer_ports # Debug
        except Exception, e:
	    logging.exception("Unable to build peer port list when generating config! %s") % e

    # If we're here, it means we're ready to generate the config for the device
    # Test for various devices
    if 'asav' in instance_blob['device_model']:
	device_config = asa.generate_configuration(db_filename,instance_blob,self_ports,peer_ports)
    elif 'csrv' in instance_blob['device_model']:
        device_config = csr.generate_configuration(db_filename,instance_blob,self_ports,peer_ports)
    elif 'srx' in instance_blob['device_model']:
	device_config = ""
    elif 'netscaler' in instance_blob['device_model']:
	device_config = ""
    elif 'ltm' in instance_blob['device_model']:
	device_config = ltm.generate_configuration(db_filename,instance_blob,self_ports,peer_ports)
    elif 'vadx' in instance_blob['device_model']:
        device_config = adx.generate_configuration(db_filename,instance_blob,self_ports,peer_ports)

    return device_config


def delete_environment(db_filename,environment_number):
    dbmgr = DatabaseManager(db_filename)

    # Initialize json response
    response = {}
    response['data'] = []

    # Delete all resources related to an environment
    # instances, ports, then networks

    # Instances
    try: 
        result = dbmgr.query("select instance_id from instances where environment_number=?",
                                ([environment_number]))
	instances = result.fetchall()

	for instance in instances:
	    novalib.delete_instance(instance['instance_id'])
	    dbmgr.query("delete from instances where instance_id=?",
                         ([instance['instance_id']]))
    except Exception, e:
	response['message'] = "Error"
        response['error'] = "Unable to delete instance. Moonshine and Nova could be out of sync! %s" % e
        status_code = "400"
        return response, status_code

    # Ports
    try:
        result = dbmgr.query("select port_id from ports where environment_number=?",
                                ([environment_number]))
        ports = result.fetchall()

        for port in ports:
	    neutronlib.delete_port(port['port_id'])
            dbmgr.query("delete from ports where port_id=?",
                             ([port['port_id']]))
    except Exception, e:
        response['message'] = "Error"
        response['error'] = "Unable to delete ports. Moonshine and Nova could be out of sync! %s" % e
        status_code = "400"
        return response, status_code

    # Networks
    try:
        result = dbmgr.query("select network_id from networks where environment_number=?",
                                ([environment_number]))
        networks = result.fetchall()

        for network in networks:
            neutronlib.delete_network(network['network_id'])
            dbmgr.query("delete from networks where network_id=?",
                             ([network['network_id']]))
    except Exception, e:
        response['message'] = "Error"
        response['error'] = "Unable to delete networks. Moonshine and Nova could be out of sync! %s" % e
        status_code = "400"
        return response, status_code

    # If we're here, all was successful
    response['message'] = "Success"
    status_code = "200"
    return response, status_code


def delete_device(device_number):
    dbmgr = DatabaseManager(db_filename)
    # Delete all resources related to an environment
    # instances, ports, then networks

    # Instances
    try:
        result = dbmgr.query("select instance_id from instances where device_number=?",
                                ([device_number]))
        instances = result.fetchall()

        for instance in instances:
            novalib.delete_instance(instance['instance_id'])
            dbmgr.query("delete from instances where instance_id=?",
                         ([instance['instance_id']]))
            print "Deleted instance %s" % instance['instance_id']

    except Exception, e:
        logging.exception('Unable to delete instance! Check sync. %s' % e)

    # Ports
    try:
        result = dbmgr.query("select port_id from ports where device_number=?",
                                ([device_number]))
        ports = result.fetchall()

        for port in ports:
            neutronlib.delete_port(port['port_id'])
            dbmgr.query("delete from ports where port_id=?",
                             ([port['port_id']]))
            print "Deleted port %s" % port['port_id']

    except Exception, e:
        logging.exception('Unable to delete port! Check sync. %s' % e)


def load_config():
    # Load local config file
    with open('config.json') as config_file:
        config = json.load(config_file)

    return config

def list_devices(db_filename,environment_number=None,device_number=None):
    # Returns a list of instances known to Moonshine
    dbmgr = DatabaseManager(db_filename)
    response = {}
    response['data'] = []

    try:
        # Return instances in the local DB
	if environment_number is not None:
	    result = dbmgr.query("select * from instances where environment_number=?",([environment_number]))
	elif device_number is not None:
            result = dbmgr.query("select * from instances where device_number=?",([device_number]))
	else:        
	    result = dbmgr.query("select * from instances")
        servers = result.fetchall()
	
	# Return 404 if no results found
    	if not servers:
	    response['message'] = "No results found"
	    status_code = "404"
	    return response,status_code

        # Build a dict that we will convert to json for output later
        for server in servers:
	    device = {}
            device['device_number'] = server['device_number']
            device['environment_number'] = server['environment_number']
            device['account_number'] = server['account_number']
            device['device_name'] = server['device_name']
            device['instance_id'] = server['instance_id']
            device['device_type'] = server['device_type']
	
    	    # Find the management port in local DB
 	    result = dbmgr.query("select port_id from ports where device_number=? and account_number=? and port_name='management'",
                                ([server['device_number'],server['account_number']]))
	    port_id = result.fetchone()[0]
	    management_ip = neutronlib.get_fixedip_from_port(port_id)
 	    device['management_ip'] = management_ip

	    # Return compute node hosting instance
	    device['hypervisor'] = novalib.get_hypervisor_from_id(server['instance_id'])	    
	    response['data'].append(device)

    except Exception, e:
	response['message'] = "Error"
	response['error'] = "%s" % e
	status_code = "400"
        return response,status_code
#        details.add_row([id,env,account,device,name,type,management_ip])
#    print details
    response['message'] = "Success"
    status_code = "200"
    return response,status_code


def find_devices(**keys):
    servers = novalib.find_instances(**keys)

    details = PrettyTable(["id", "environment", "account", "device", "name", "type", "management address"])
    details.align["id"] = "l" # left

    for server in servers:
        if server.metadata.get('hostname') is not None:
            id = server.id
            env = server.metadata.get('env')
            account = server.metadata.get('account_number')
            device = server.metadata.get('device')
            name = server.metadata.get('hostname')
            type = server.metadata.get('type')
	    mgmt = ''

            ports = neutronlib.list_ports(device_id=server.id,type='management')
            for port in ports["ports"]:
                mgmt = port["fixed_ips"][0]["ip_address"]
            details.add_row([id,env,account,device,name,type,mgmt])

    print details

def build_db(db_filename,schema_filename):
    db_is_new = not os.path.exists(db_filename)

    with sqlite3.connect(db_filename) as conn:
        if db_is_new:
            print 'Creating local database'
            with open(schema_filename, 'rt') as f:
                schema = f.read()
            conn.executescript(schema)

	    print 'Populating local database'
	    dbmgr = DatabaseManager(db_filename)
		
	    dbmgr.query("INSERT INTO networks (network_id,network_name,cidr,segmentation_id,network_type) VALUES (?,?,?,?,?)",
                                ('1545bdef-87c7-47e9-9c7c-bb63f8fe1f57','outside','204.232.157.96/27','71','vlan'))
	    dbmgr.query("INSERT INTO networks (network_id,network_name,cidr,segmentation_id,network_type) VALUES (?,?,?,?,?)",
                                ('9d87197c-77f9-49e2-bf5a-d90f3d64d9ea','management','10.4.130.96/27','72','vlan'))
	    return True
        else:
	    return False


if __name__ == "__main__":
    # Build the local database used to keep track of resources
    # Should only be done on first execution
    build_db(db_filename,schema_filename)

    # Open DB connection
    dbmgr = DatabaseManager(db_filename)

    parser = argparse.ArgumentParser(prog='moonshine',description='Proof of concept instance deployment \
						tool used to bootstrap and deploy virtual network devices, \
						including firewalls and load balancers')
    subparsers = parser.add_subparsers(help='commands',dest='command')

    # A list command
    list_parser = subparsers.add_parser('list', help='List all virtual network instances')

    # A find command
    find_parser = subparsers.add_parser('find', help='Find virtual network instances')    
    find_parser.add_argument('-e','--env', action='store', dest='env', help='Find instance based on environment number', required=False)
    find_parser.add_argument('-a','--account', action='store', dest='account_number', help='Find instance based on account number', required=False)

    # A create-ports command
    # Moving to creating ports first, then can create instances at-will
    # (todo) use description of the port (with dict) to associate with device and account number
    createports_parser = subparsers.add_parser('create-ports', help='Create virtual network port(s)')
    createports_parser.add_argument('-j','--json',type=json.loads,
				dest='port_blob',help='Specifies a list of dict key/value pairs for ports using net-id and fixed-ip')

    createnetworks_parser = subparsers.add_parser('create-networks', help='Create virtual network(s)')
    createnetworks_parser.add_argument('-j','--json',type=json.loads,
                                dest='network_blob',help='Specifies a list of dict key/value pairs for network using name and cidr')

    createinstance_parser = subparsers.add_parser('create-instance', help='Create virtual instance')
    createinstance_parser.add_argument('-j','--json',type=json.loads,
                                dest='instance_blob',help='Specifies json for instance')

    delete_parser = subparsers.add_parser('delete', help='Remove all resources related to an object')
    del_group = delete_parser.add_mutually_exclusive_group()    
    del_group.add_argument('-d','--device_number',
                                dest='device_number',help='Specify DCX device number', required=False)
    del_group.add_argument('-e','--environment',
                                dest='environment_number',help='Specify DCX environment number', required=False)

    # Array for all arguments passed to script
    args = parser.parse_args()

    # Validate that there is an image and flavor for each specified option
    # (todo) build validator

    # create-networks
    # Takes JSON blob consisting of environment_number, account_number, and networks (name/cidr)
    try:
        if args.command == 'create-networks':
	    create_networks(db_filename,args.network_blob)
#            print json.dumps(args.networks)
#            sys.exit(1)
    except Exception, e:
        logging.exception("Error: Unable to create networks! %s" % e)

    # create-ports
    try:
	if args.command == 'create-ports':
	    create_ports(db_filename,args.port_blob)
    except Exception, e:
	logging.exception("Error: Unable to create ports! %s" % e)

    # create-instance
    try:
        if args.command == 'create-instance':
            create_instance(db_filename,args.instance_blob)
    except Exception, e:
        logging.exception("Error: Unable to create instance! %s" % e)    

    # Delete resources
    try:
	if args.command == 'delete':
	    if args.environment_number is not None:
		delete_environment(db_filename,args.environment_number)
	    elif args.device_number is not None:
		delete_device(args.device_number)
	    else:
		print 'Nothing to delete!'
    except Exception, e:
	logging.exception("Error deleting: %s" % e)







    # Work through the parser.
    # First up, the FIND parser
    try:
        if args.command == 'find':
	    keys = vars(args)
	    keys.pop('command') # Remove the command arg. Only send the legit ones.
            find_devices(**keys)
            sys.exit(1)
    except Exception, e:
	logging.exception("Oops! Unable to find: %s" % e)

    # The LIST parser
    try:
	if args.command == 'list':
	    data = list_devices(db_filename, None)
	    print json.dumps(data)
	    sys.exit(1)
    except Exception, e:
	logging.exception("Oops! Unable to list! %s" % e)

    # The CREATE parser
    # (todo) Build it so that an individual device can be created and added to an environment
    # For now, all devices are created at launch
#    try:
#	if args.command == 'create':
#	    # (todo) Tie environments into Keystone tenants.
#	    # Check for tenant/project before proceeding. Maybe notify user?
#	    print "Creating devices for environment %s in account %s" % (args.env,args.account_number)
#	    create(args)
# #   except Exception, e:
#	logging.exception("Oops! Unable to create! %s" % e)
