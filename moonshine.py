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

def create_networks(network_blob):
    dbmgr = DatabaseManager(db_filename)

    details = PrettyTable(["account", "environment", "name", "cidr", "network_id", "subnet_id"])

    for m_network in network_blob["networks"]:
	# Finds the true CIDR (bit boundary) for given CIDR/IP/Address
	real_cidr = str(netaddr.IPNetwork(m_network["cidr"]).cidr)

	# Validates a network matching env and cidr doesn't already exist.
	# (todo) How do we also validate the network name isn't used yet
	data = dbmgr.query("select count(*) from networks where cidr=? and environment_number=?", 
				(real_cidr,network_blob["environment_number"]))

	count = data.fetchone()
	if count[0] > 0:
	    print "Network with CIDR %s already exists as part of environment %s! Not creating" % (real_cidr,network_blob["environment_number"])

	else:
#            print "Network does not exist in database. Creating new network."
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
						**network_args) # need to set tenant id

#                print "Created network %s in Neutron" % (q_network["network"]["id"])

		# Creates the subnet in Neutron
		q_subnet = neutronlib.create_subnet(network_id=q_network["network"]["id"],
							cidr=real_cidr) # Need to set tenant id

#		print "Created subnet %s in Neutron" % (q_subnet["subnet"]["id"])

	        # Update sqlite database
	        try:
	    	    dbmgr.query("insert into networks (network_id,tenant_id,account_number,environment_number, \
					network_name,cidr,segmentation_id,network_type,subnet_id) values (?,?,?,?,?,?,?,?,?)", 
					([q_network["network"]["id"],q_network["network"]["tenant_id"],
					network_blob["account_number"],network_blob["environment_number"],
					m_network["network_name"],real_cidr,q_network["network"]["provider:segmentation_id"],
					q_network["network"]["provider:network_type"],q_subnet["subnet"]["id"]]))

		    details.add_row([network_blob["account_number"],network_blob["environment_number"],
					m_network["network_name"],real_cidr,q_network["network"]["id"],q_subnet["subnet"]["id"]])
	        except Exception, e:
		    print "Unable to update local database. Moonshine and Neutron could be out of sync! %s" % e
	    except Exception, e:
	        # (todo) Rollback neutron net-create, too?
	        print "Error! %s" % e	

    # Print the details of the networks created
    print "Networks created:"
    print details 
	
def create_ports(port_blob):
    dbmgr = DatabaseManager(db_filename)
    details = PrettyTable(["account", "environment", "device", "name", "port_id", "network_id"])

    for m_port in port_blob["ports"]:

        # Validates a port matching device number and network name doesn't already exist
        data = dbmgr.query("select count(*) from ports where device_number=? and environment_number=? and network_name=?",
                                (port_blob["device_number"],port_blob["environment_number"],m_port["network_name"]))

        count = data.fetchone()
        if count[0] > 0:
            print "Device '%s' already has a port on the '%s' network in environment %s! Not creating" % (port_blob["device_number"],m_port["network_name"],port_blob["environment_number"])

        else:
#            print "Device '%s' in environment '%s' does not have a port in the '%s' network in the database. Creating new port." % \
#			(port_blob["device_number"],port_blob["environment_number"],m_port["network_name"])            
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
	    	    print "Error! Network '%s' in environment '%s' does not exist in the database. Please create the network and try again." % \
				(m_port["network_name"],port_blob["environment_number"])
		    continue # Break out and process next port

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

#                print "Created port %s in Neutron" % (q_port["port"]["id"])
		

                # Update sqlite database
                try:
                    dbmgr.query("insert into ports (port_id,network_id,tenant_id,account_number,environment_number, \
                                        network_name,fixed_ip,device_number,port_name) values (?,?,?,?,?,?,?,?,?)",
                                        ([q_port["port"]["id"],q_port["port"]["network_id"],q_port["port"]["tenant_id"],
                                        port_blob["account_number"],port_blob["environment_number"],
                                        m_port["network_name"],q_port["port"]["fixed_ips"][0]["ip_address"],
                                        port_blob["device_number"],m_port["network_name"]]))

		    details.add_row([port_blob["account_number"],port_blob["environment_number"],port_blob["device_number"],
                                        m_port["network_name"],q_port["port"]["id"],q_port["port"]["network_id"]])

                except Exception, e:
                    print "Unable to update local database. Moonshine and Neutron could be out of sync! %s" % e
            except Exception, e:
                # (todo) Rollback neutron port-create, too?
                print "Error! %s" % e

    # Print the details of the ports created
    print "Ports created:"
    print details

def create_instance(instance_blob):
    dbmgr = DatabaseManager(db_filename)
    details = PrettyTable(["account", "environment", "device", "hostname", "device_type", "priority", "zone", "management_ip"])

    # (todo) Check to see if an instance with that device number exists!

    # Validates a port matching device number and network name exists
    # Otherwise, kick back to the user to create the port first
    port_exists = True # Initialize value
    for m_port in instance_blob["ports"]:
        data = dbmgr.query("select count(*) from ports where device_number=? and environment_number=? and network_name=?",
                                (instance_blob["device_number"],instance_blob["environment_number"],m_port["network_name"]))

        count = data.fetchone()
        if count[0] < 1:
            print "Device '%s' does not have a port in the '%s' network in environment %s! Please create the port and try again." % \
            				(instance_blob["device_number"],m_port["network_name"],instance_blob["environment_number"])
            port_exists = False
	continue # Continue the loop

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
	except Exception ,e:
	    print 'Unable to determine existence of ports %s' % e 

    # Load additional config options like image IDs and flavor IDs
    try:
        config = load_config()
	image_id = config[instance_blob['device_type']][instance_blob['device_model']]['image']
	flavor_id = config[instance_blob['device_type']][instance_blob['device_model']]['flavor']
    except Exception, e:
        logging.exception("Unable to load configuration file! %s" % e)
        sys.exit(1)


    # Generate device configuration
    device_config = generate_configuration(instance_blob)

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
            instance = novalib.boot_instance(name=hostname,image=image_id,flavor=flavor_id,config_drive="True",
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

            details.add_row([instance_blob["account_number"],instance_blob["environment_number"],instance_blob["device_number"],
                              hostname,instance_blob["device_type"],instance_blob["device_priority"],zone,management_ip])
        except Exception, e:
            print "Unable to update local database while booting the instance. Moonshine and Nova could be out of sync! %s" % e

        # Print the details of the instance created
        print "Instance details:"
        print details
	return instance

    except Exception, e:
	logging.exception("Unable to boot instance! %s" % e)

def generate_configuration(instance_blob):
    """
    :desc: Generates device configuration. Not really pluggable. Only works with certain device types/models.
    """

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
        logging.exception("Unable to build self port list when generating config! %s") % e

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
        device_config = ""

    return device_config


def delete_environment(environment_number):
    dbmgr = DatabaseManager(db_filename)
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
	    print "Deleted instance %s" % instance['instance_id']

    except Exception, e:
	logging.exception('Unable to delete instance! Check sync. %s' % e)

    # Ports
    try:
        result = dbmgr.query("select port_id from ports where environment_number=?",
                                ([environment_number]))
        ports = result.fetchall()

        for port in ports:
	    neutronlib.delete_port(port['port_id'])
            dbmgr.query("delete from ports where port_id=?",
                             ([port['port_id']]))
            print "Deleted port %s" % port['port_id']

    except Exception, e:
        logging.exception('Unable to delete port! Check sync. %s' % e)

    # Networks
    try:
        result = dbmgr.query("select network_id from networks where environment_number=?",
                                ([environment_number]))
        networks = result.fetchall()

        for network in networks:
            neutronlib.delete_network(network['network_id'])
            dbmgr.query("delete from networks where network_id=?",
                             ([network['network_id']]))
            print "Deleted network %s" % network['network_id']

    except Exception, e:
        logging.exception('Unable to delete network! Check sync. %s' % e)

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









def launch_firewall(ha,fw,_ports,_fw_configuration,image_id,flavor_id):
    global _metadata

    # Initialize metadata
    _metadata.update({"ha": str(ha)})
    _metadata.update({"type": "firewall"})
    _metadata.update({"device": keystonelib.generate_random_device()})
    _metadata.update({"peer": ""})

    # Boot the primary ASA
    print "Launching primary firewall..."
    _fw_configuration['priority'] = 'primary'

    if 'asav' in fw:
        primary_config = configlib.generate_asa_config(ha,_fw_configuration)
	file_path = "day0"
    elif 'vsrx' in fw:
        primary_config = configlib.generate_srx_config(ha,_fw_configuration)
	file_path = "juniper.conf"
    else:
        print "Unsupported firewall. Exiting!"
        sys.exit(1)
    
    # If ha, build out a failover port. Otherwise don't. These need to be in a specific order for the ASA.
    if ha:
	ports = []
	ports.append({'mgmt':_ports['fw_mgmt_primary_port_id']})
	ports.append({'outside':_ports['fw_outside_primary_port_id']})
	ports.append({'inside':_ports['fw_inside_primary_port_id']})
	ports.append({'failover':_ports['fw_failover_primary_port_id']})
    else:
	ports = []
        ports.append({'mgmt':_ports['fw_mgmt_primary_port_id']})
        ports.append({'outside':_ports['fw_outside_primary_port_id']})
        ports.append({'inside':_ports['fw_inside_primary_port_id']})

    az = "ZONE-A"
#    print _metadata # Debugging
    primary_fw = novalib.boot_instance(name=_metadata['hostname'],image=image_id,flavor=flavor_id,config_drive='True',
					ports=ports,file_contents=primary_config,az=az,file_path=file_path,
					meta=_metadata,project_id=os_project.id)


    # Check to see if VM state is ACTIVE.
    print "Waiting for primary firewall %s to go ACTIVE..." % primary_fw.id
    status = novalib.check_status(primary_fw.id)
    duration = 0
    while not status == "ACTIVE":
	if status == "ERROR":
	    print "Instance is in ERROR state. No sense in moving on..." # (todo) build some graceful delete
	    sys.exit(1)
	else:
	    if duration >= 20:
		print "Waiting..."
		duration = 0;
	    else:
	        time.sleep(1)
		duration += 1
                status = novalib.check_status(primary_fw.id)

    if ha:
	# Boot the secondary ASA
        print "Launching secondary firewall..."
        _fw_configuration['priority'] = 'secondary'
    
        # Initialize metadata
        _metadata.update({"ha": str(ha)})
	_metadata.update({"type": "firewall"})
        _metadata.update({"device": keystonelib.generate_random_device()})
        _metadata.update({"peer": ""})

        if 'asav' in fw:
            secondary_config = configlib.generate_asa_config(ha,_fw_configuration)
	    file_path = "day0"
        elif 'vsrx' in fw:
            secondary_config = configlib.generate_srx_config(ha,_fw_configuration)
	    file_path = "juniper.conf"
        else:
            print "Unsupported firewall. Exiting!"
            sys.exit(1)

        ports = []
        ports.append({'mgmt':_ports['fw_mgmt_secondary_port_id']})
        ports.append({'outside':_ports['fw_outside_secondary_port_id']})
        ports.append({'inside':_ports['fw_inside_secondary_port_id']})
        ports.append({'failover':_ports['fw_failover_secondary_port_id']})

	az = 'ZONE-B'
	secondary_fw = novalib.boot_instance(name=_metadata['hostname'],image=image_id,flavor=flavor_id,config_drive='True',
                                        ports=ports,file_contents=secondary_config,az=az,file_path=file_path,
					meta=_metadata,project_id=os_project.id)

        # Check to see if VM state is ACTIVE.
        # (todo) Will want to put an ERROR check in here so we can move on
        print "Waiting for secondary firewall %s to go ACTIVE..." % secondary_fw.id
        status = novalib.check_status(secondary_fw.id)
	duration = 0
        while not status == "ACTIVE":
            if status == "ERROR":
                print "Instance is in ERROR state. No sense in moving on..." # (todo) build some graceful delete
                sys.exit(1)
            else:
		if duration >= 20:
                    print "Waiting..."
                    duration = 0;
                else:
                    time.sleep(1)
                    duration += 1
                    status = novalib.check_status(secondary_fw.id)

    print "Please wait a few minutes while your firewall(s) come online."

    details = PrettyTable(["Parameter", "Value"])
    details.align["Parameter"] = "l" # right align
    details.align["Value"] = "l" # left align
    details.add_row(["Hostname:",_fw_configuration['fw_hostname']])
    details.add_row(["Primary IP:",_fw_configuration['fw_outside_primary_address']])
    details.add_row(["Primary Management IP:",_fw_configuration['fw_mgmt_primary_address']])

    # Only print secondary details if ha
    if ha:
        details.add_row(["Secondary IP:",_fw_configuration['fw_outside_secondary_address']])
        details.add_row(["Secondary Management IP:",_fw_configuration['fw_mgmt_secondary_address']])

    details.add_row(["Inside Network VLAN ID",_fw_configuration['fw_inside_segmentation_id']])
    details.add_row(["",""])
    details.add_row(["VPN Endpoint:",_fw_configuration['fw_outside_primary_address']])
    details.add_row(["VPN Group Name:",_fw_configuration['tunnel_group']])
    details.add_row(["VPN Group Password:",_fw_configuration['group_password']])
    details.add_row(["VPN Username:",_fw_configuration['vpn_user']])
    details.add_row(["VPN Password:",_fw_configuration['vpn_password']])
    details.add_row(["",""])
    details.add_row(["Primary Console:",novalib.get_console(primary_fw)])

    if ha:
	details.add_row(["Secondary Console:",novalib.get_console(secondary_fw)])
    print details

def launch_loadbalancer(ha,lb,_ports,_lb_configuration,image_id,flavor_id):
    global _metadata

    # Boot the primary load balancer
    print "\nLaunching primary load balancer..."
    _lb_configuration['priority'] = 'primary'
    if lb == 'ltm':
        primary_config = configlib.generate_f5_config(ha,_lb_configuration)
    elif lb == 'netscaler':
	primary_config = configlib.generate_netscaler_config(ha,_lb_configuration)
    else:
        print "Unsupported load balancer. Exiting!"
	sys.exit(1)

    # Initialize metadata
    _metadata.update({"ha": str(ha)})
    _metadata.update({"type": "load balancer"})
    _metadata.update({"device": keystonelib.generate_random_device()})
    _metadata.update({"peer": ""})

    # If ha, build out a failover port. Otherwise don't. These need to be in a specific order for the LB.
    if ha:
        ports = []
	ports.append({'mgmt':_ports['lb_mgmt_primary_port_id']})
        ports.append({'outside':_ports['lb_outside_primary_port_id']})
        ports.append({'inside':_ports['lb_inside_primary_port_id']})
	ports.append({'failover':_ports['lb_failover_primary_port_id']})
    else:
	ports = []
	ports.append({'mgmt':_ports['lb_mgmt_primary_port_id']})
	ports.append({'outside':_ports['lb_outside_primary_port_id']})
	ports.append({'inside':_ports['lb_inside_primary_port_id']})

    az = 'ZONE-A'
    primary_lb = novalib.boot_instance(name=_metadata['hostname'],image=image_id,flavor=flavor_id,
                                        ports=ports,userdata=primary_config,az=az,project_id=os_project.id,
					meta=_metadata)

    # Check to see if VM state is ACTIVE.
    print "Waiting for primary load balancer %s to go ACTIVE..." % primary_lb.id
    status = novalib.check_status(primary_lb.id)
    duration = 0
    while not status == "ACTIVE":
        if status == "ERROR":
            print "Instance is in ERROR state. No sense in moving on..." # (todo) build some graceful delete
            sys.exit(1)
        else:
            duration += 1
	    if (duration % 10 == 0):
		printf('|')
	    else:	 
	        printf('.')
	    time.sleep(1)		
            status = novalib.check_status(primary_lb.id)

    if ha:
        # Boot the secondary LB
        print "\nLaunching secondary load balancer..."
        _lb_configuration['priority'] = 'secondary'
        if lb == 'ltm':
	    secondary_config = configlib.generate_f5_config(ha,_lb_configuration)
        elif lb == 'netscaler':
            secondary_config = configlib.generate_netscaler_config(ha,_lb_configuration)
        else:
            print "Unsupported load balancer. Exiting!"
            sys.exit(1)

        # Initialize metadata
        _metadata.update({"ha": str(ha)})
        _metadata.update({"type": "load balancer"})
        _metadata.update({"device": keystonelib.generate_random_device()})
        _metadata.update({"peer": ""})

	ports = []
        ports.append({'mgmt':_ports['lb_mgmt_secondary_port_id']})
        ports.append({'outside':_ports['lb_outside_secondary_port_id']})
        ports.append({'inside':_ports['lb_inside_secondary_port_id']})
        ports.append({'failover':_ports['lb_failover_secondary_port_id']})

        az = 'ZONE-B'
        secondary_lb = novalib.boot_instance(name=_metadata['hostname'],image=image_id,flavor=flavor_id,
                                        ports=ports,userdata=secondary_config,az=az,project_id=os_project.id,
					meta=_metadata) 

        # Check to see if VM state is ACTIVE.
        # (todo) Will want to put an ERROR check in here so we can move on
        print "Waiting for secondary load balancer %s to go ACTIVE..." % secondary_lb.id
        status = novalib.check_status(secondary_lb.id)
	duration = 0
        while not status == "ACTIVE":
            if status == "ERROR":
                print "Instance is in ERROR state. No sense in moving on..." # (todo) build some graceful delete
                sys.exit(1)
            else:
		duration += 1
                if (duration % 10 == 0):
                    printf('|')
                else:
                    printf('.')
                time.sleep(1)
                status = novalib.check_status(secondary_lb.id)

    print " Done!\n Please wait a few minutes while your load balancer(s) come online."

    details = PrettyTable(["Parameter", "Value"])
    details.align["Parameter"] = "l" # right align
    details.align["Value"] = "l" # left align
    details.add_row(["Hostname:",_lb_configuration['lb_hostname']])
    details.add_row(["Primary Management IP:",_lb_configuration['lb_mgmt_primary_address']])
    
    # Only print secondary details if ha
    if ha:
        details.add_row(["Secondary Management IP:",_lb_configuration['lb_mgmt_secondary_address']])        

    details.add_row(["Inside Network VLAN ID",_lb_configuration['lb_inside_segmentation_id']])
    details.add_row(["",""])
    details.add_row(["Primary Console:",novalib.get_console(primary_lb)])
    if ha:
	details.add_row(["Secondary Console:",novalib.get_console(secondary_lb)])
    print details

def launch_instance(network_id,vm_image,vm_flavor):

    # Boot the primary load balancer
    print "\nLaunching a virtual machine for testing..."    

    vm_hostname = _metadata['hostname'] + "-VM"
    instance = novalib.boot_vm(vm_hostname,network_id,vm_image,vm_flavor,az="ZONE-A",project_name=os_project.name)

    # Check to see if VM state is ACTIVE.
    print "Waiting for the virtual machine %s to go ACTIVE..." % instance.id
    status = novalib.check_status(instance.id)
    duration = 0
    while not status == "ACTIVE":
        if status == "ERROR":
            print "Instance is in ERROR state. No sense in moving on..." # (todo) build some graceful delete
            sys.exit(1)
        else:
            duration += 1
            if (duration % 10 == 0):
                printf('|')
            else:
                printf('.')
            time.sleep(1)
            status = novalib.check_status(instance.id)

    print " Done!\n Please wait a few minutes while your instance(s) come online."

    details = PrettyTable(["Parameter", "Value"])
    details.align["Parameter"] = "l" # right align
    details.align["Value"] = "l" # left align
    details.add_row(["Hostname:",vm_hostname])
    details.add_row(["Network:",instance.networks])
    details.add_row(["NAT Address:",""])
    details.add_row(["Primary Console:",novalib.get_console(instance)])

    print details

def load_config():
    # Load local config file
    with open('config.json') as config_file:
        config = json.load(config_file)

    return config

def create(args):
    global _networks, _ports, _metadata, os_project

    # Try opening the file that contains information about the networks, flavors, and images
    # (todo) Accept these as (optional) command-line inputs
    try:
	config = load_config()
    except Exception, e:
	logging.exception("Unable to load configuration file! %s" % e)
	sys.exit(1)

    _networks['netdev_network'] = config['networks']['outside']
    _networks['oob_network'] = config['networks']['mgmt']

    fw_image = config['firewall'][args.fw]['image']
    fw_flavor = config['firewall'][args.fw]['flavor']

    if args.lb is not None:
        lb_image = config['loadbalancer'][args.lb]['image']
        lb_flavor = config['loadbalancer'][args.lb]['flavor']

    if args.vm:
        vm_image = config['vm']['image']
        vm_flavor = config['vm']['flavor']

    # Set arbitrary hostname
    # (todo) The hostname will eventually be device number. Need to work out adding devices one at a time!
    _metadata['hostname'] = novalib.random_server_name()

    # Create a project for the devices to live in
    os_project = create_project(args.account_number)
    _metadata['project_name'] = os_project.name

    # Assign admin role to the current user in the new project
    # This will allow us to boot instances in that project
    try:
        user = keystonelib.get_user('admin') # hardcoded for now
        # (todo) Maybe add this in to the create_project function
        response = keystonelib.add_user_to_project(user.id,os_project.id)
    except Exception, e:
	logging.exception("Unable to add user to new project. Bailing! %s" % e)

    # Set the environment number
    _metadata['env'] = args.env

    # Create networks
    _networks = create_fw_networks(args.ha,args.lb)
    if args.lb is not None:
        _networks.update(create_lb_networks(args.ha))

    # Create ports
    _ports = create_fw_ports()
    if args.lb is not None:
        _ports.update(create_lb_ports())

    # Launch devices
    print "Launching devices... (This operation can take a while for large images.)"
    _fw_configuration = build_fw_configuration(os_project.name,'username',args.ha)
    launch_firewall(args.ha,args.fw,_ports,_fw_configuration,fw_image,fw_flavor)

    if args.lb is not None: # If user is spinning up load balancers, launch 'em behind the FW
        _lb_configuration = build_lb_configuration(args.ha)
        launch_loadbalancer(args.ha,args.lb,_ports,_lb_configuration,lb_image,lb_flavor)
        
    # If --vm is specified, launch a VM in the backend INSIDE network that can be reachable from the web
    # (todo) Cleanup the dict/array with the configuration and networks
    if args.vm:
        network_id = _networks['fw_inside_network_id']
        if args.lb is not None:
            network_id = _networks['lb_inside_network_id']
        launch_instance(network_id,vm_image,vm_flavor)

def list_devices(db_filename):
    # Returns a list of instances known to Moonshine
    dbmgr = DatabaseManager(db_filename)
    details = PrettyTable(["instance_id", "environment_number", "account_number", "device_number", "device_name", "device_type", "management_ip"])
    details.align["id"] = "l" # left

    # Return instances in the local DB
    result = dbmgr.query("select * from instances")

    servers = result.fetchall()
    for server in servers:
	id = server['instance_id']
	env = server['environment_number']
	account = server['account_number']
	device = server['device_number']
	name = server['device_name']
	type = server['device_type']

	# Find the management port in local DB
	result = dbmgr.query("select port_id from ports where device_number=? and account_number=? and port_name='management'",
                                ([server['device_number'],server['account_number']]))
	port_id = result.fetchone()[0]
	management_ip = neutronlib.get_fixedip_from_port(port_id)

        details.add_row([id,env,account,device,name,type,management_ip])

    print details

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
	    create_networks(args.network_blob)
#            print json.dumps(args.networks)
#            sys.exit(1)
    except Exception, e:
        logging.exception("Error: Unable to create networks! %s" % e)

    # create-ports
    try:
	if args.command == 'create-ports':
	    create_ports(args.port_blob)
    except Exception, e:
	logging.exception("Error: Unable to create ports! %s" % e)

    # create-instance
    try:
        if args.command == 'create-instance':
            create_instance(args.instance_blob)
    except Exception, e:
        logging.exception("Error: Unable to create instance! %s" % e)    

    # Delete resources
    try:
	if args.command == 'delete':
	    if args.environment_number is not None:
		delete_environment(args.environment_number)
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
	    list_devices(db_filename)
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
