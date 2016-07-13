#!/usr/bin/env python

import sqlite3, os
import requests, json, sys
import argparse, time, logging
from prettytable import PrettyTable
import library.neutron as neutronlib
import library.config as configlib
import library.nova as novalib
import library.keystone as keystonelib
from library.printf import printf

# Initialize global variables that will be used throughout
# Best practice? Dunno.
_networks = {}
_ports = {}
_metadata = {}
db_filename = './moonshine_db.sqlite'
schema_filename = './moonshine_db.schema'

class DatabaseManager(object):
    def __init__(self, db):
        self.conn = sqlite3.connect(db)
        self.conn.execute('pragma foreign_keys = on')
        self.conn.commit()
        self.cur = self.conn.cursor()

    def query(self, arg, bindings=None):
	if bindings is not None:
	    self.cur.execute(arg,bindings)
	else:	
            self.cur.execute(arg)
        self.conn.commit()
        return self.cur

    def __del__(self):
        self.conn.close()

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

    for m_network in network_blob["networks"]:
	# Validates a network matching env and cidr doesn't already exist
	data = dbmgr.query("select count(*) from networks where cidr=? and environment_number=?", 
				(m_network["cidr"],network_blob["environment_number"]))

	count = data.fetchone()[0]
	if count > 0:
	    print "Network with CIDR %s already exists as part of environment %s! Not creating" % (m_network["cidr"],network_blob["environment_number"])

	else:
            print "Creating new network..."
    	    try:
		# Creates the network in Neutron
                q_network = neutronlib.create_network(network_name=m_network["name"],
                                                network_type="vxlan",
                                                tenant_id="4f077b35baba4c3bb1bb8d2cad49061d")
                print "Created network %s in Neutron" % (q_network["network"]["id"])

	        # Update sqlite database
	        try:
	    	    dbmgr.query("insert into networks (network_id,tenant_id,account_number,environment_number,type,cidr) values (?,?,?,?,?,?)", 
				([q_network["network"]["id"],q_network["network"]["tenant_id"],
				network_blob["account_number"],network_blob["environment_number"],
				m_network["type"],m_network["cidr"]]))
	        except Exception, e:
		    print "Unable to update local database! %s" % e
	    except Exception, e:
	        # (todo) Rollback neutron net-create, too?
	        print "boo %s" % e	
	

def create_fw_networks(ha,lb):    
    global _networks
    print "Creating virtual networks in Neutron for firewall(s)..."

    # Create INSIDE (or transit) network
    if lb is not None:
	_networks['fw_inside_network_name'] = _metadata['hostname'] + "-FW-LB"
	fw_inside_network = neutronlib.create_network(network_name=_networks['fw_inside_network_name'])
	dhcp=False
	inside_cidr = "192.168.254.0/24" # (todo) Allow this to be set on CLI
	_networks['fw_inside_net_addr'] = "192.168.254.0" # (todo) make this discoverable
	_networks['fw_inside_mask'] = "255.255.255.240"
	_networks['fw_inside_gateway'] = "192.168.254.1" # This needs to be set based on the primary IP of the FW. Which means we need to ask for this addr when creating the port!
    else:
	_networks['fw_inside_network_name'] = _metadata['hostname'] + "-FW-INSIDE"
	fw_inside_network = neutronlib.create_network(network_name=_networks['fw_inside_network_name'],
						network_type="vlan",
						tenant_id=os_project.id) # vxlan is temporary	
	dhcp=True
	inside_cidr = "192.168.100.0/28"
        _networks['fw_inside_net_addr'] = "192.168.100.0" # (todo) make this discoverable
        _networks['fw_inside_mask'] = "255.255.255.0"
	_networks['fw_inside_gateway'] = "192.168.100.1"

    _networks['fw_inside_network_id'] = fw_inside_network["network"]["id"]
    _networks['fw_inside_segmentation_id'] = neutronlib.get_segment_id_from_network(fw_inside_network["network"]["id"])
    _networks['fw_inside_subnet_id'] = neutronlib.create_subnet(network_id=_networks['fw_inside_network_id'],
							cidr=inside_cidr,
							gateway=_networks['fw_inside_gateway'],
							enable_dhcp=dhcp,
							tenant_id=os_project.id)

    # Create FAILOVER network if highly-available
    if ha:
	_networks['fw_failover_network_name'] = _metadata['hostname'] + "-FW-FAILOVER"
	fw_failover_network = neutronlib.create_network(network_name=_networks['fw_failover_network_name'],
						tenant_id=os_project.id)
	_networks['fw_failover_network_id'] = fw_failover_network["network"]["id"]
	failover_cidr = "192.168.255.0/28"
	_networks['fw_failover_subnet_id'] = neutronlib.create_subnet(network_id=_networks['fw_failover_network_id'],
								cidr=failover_cidr,
								tenant_id=os_project.id)
    else:
	_networks['fw_failover_network_name'] = None
	fw_failover_network = None # (todo) verify if this is necessary

    return _networks # Return the list. It will be used to create ports.

def create_lb_networks(ha):
    global _networks

    print "Creating virtual networks in Neutron for load balancer(s)..."
    
    # Create INSIDE network (where servers live)
    _networks['lb_inside_network_name'] = _metadata['hostname'] + "-LB-INSIDE"
    lb_inside_network = neutronlib.create_network(network_name=_networks['lb_inside_network_name'],
						network_type="vlan",
						tenant_id=os_project.id) # vxlan is temporary
    dhcp=True
    inside_cidr = "192.168.100.0/24"
    _networks['lb_inside_net_addr'] = "192.168.100.0" # (todo) make this discoverable
    _networks['lb_inside_mask'] = "255.255.255.0"
    _networks['lb_inside_gateway'] = "192.168.100.1"

    _networks['lb_inside_network_id'] = lb_inside_network["network"]["id"]
    _networks['lb_inside_subnet_id'] = neutronlib.create_subnet(network_id=_networks['lb_inside_network_id'],
							cidr=inside_cidr,
							gateway=_networks['lb_inside_gateway'],
							enable_dhcp=dhcp,
							tenant_id=os_project.id)
    _networks['lb_inside_segmentation_id'] = neutronlib.get_segment_id_from_network(lb_inside_network["network"]["id"])

    # Create FAILOVER network if highly-available
    if ha:
        _networks['lb_failover_network_name'] = _metadata['hostname'] + "-LB-FAILOVER"
        lb_failover_network = neutronlib.create_network(network_name=_networks['lb_failover_network_name'],
						tenant_id=os_project.id)
	dhcp=False
        _networks['lb_failover_network_id'] = lb_failover_network["network"]["id"]
        failover_cidr = "192.168.255.16/28"
        _networks['lb_failover_subnet_id'] = neutronlib.create_subnet(network_id=_networks['lb_failover_network_id'],
								cidr=failover_cidr,
								tenant_id=os_project.id)
    else:
        _networks['lb_failover_network_name'] = None
        lb_failover_network = None # (todo) verify if this is necessary

    return _networks # Return the list. It will be used to create ports.
    
def create_fw_ports():
    global _ports

    print "Creating virtual ports in Neutron for firewall(s)..."

    try:
        # Create ports
        _ports['fw_mgmt_primary_port_id'] = neutronlib.create_port(network_id=_networks['oob_network'],
								hostname=_metadata['hostname']+"-FW-PRI-MGMT",
								port_security_enabled='False',
								description='{"type":"management"}',
								tenant_id=os_project.id)
        _ports['fw_outside_primary_port_id'] = neutronlib.create_port(network_id=_networks['netdev_network'],
								hostname=_metadata['hostname']+"-FW-PRI-OUTSIDE",
								port_security_enabled='False',
								description='{"type":"outside"}',
								tenant_id=os_project.id)
        _ports['fw_inside_primary_port_id'] = neutronlib.create_port(network_id=_networks['fw_inside_network_id'],
								hostname=_metadata['hostname']+"-FW-PRI-INSIDE",
								subnet_id=_networks['fw_inside_subnet_id'],
								ip_address=_networks['fw_inside_gateway'],
								port_security_enabled='False',
								tenant_id=os_project.id)

        # If HA, create a failover port and secondary unit ports
        if _networks['fw_failover_network_name'] is not None:
	    _ports['fw_failover_primary_port_id'] = neutronlib.create_port(network_id=_networks['fw_failover_network_id'],
									hostname=_metadata['hostname']+"-FW-PRI-FAILOVER",
									port_security_enabled='False',
									description='{"type":"failover"}',
									tenant_id=os_project.id)
	    _ports['fw_failover_secondary_port_id'] = neutronlib.create_port(network_id=_networks['fw_failover_network_id'],
									hostname=_metadata['hostname']+"-FW-SEC-FAILOVER",
									port_security_enabled='False',
									description='{"type":"failover"}',
									tenant_id=os_project.id)
	    _ports['fw_mgmt_secondary_port_id'] = neutronlib.create_port(network_id=_networks['oob_network'],
									hostname=_metadata['hostname']+"-FW-SEC-MGMT",
									port_security_enabled='False',
									description='{"type":"management"}',
									tenant_id=os_project.id)
	    _ports['fw_outside_secondary_port_id'] = neutronlib.create_port(network_id=_networks['netdev_network'],
									hostname=_metadata['hostname']+"-FW-SEC-OUTSIDE",
									port_security_enabled='False',
									description='{"type":"outside"}',
									tenant_id=os_project.id)
	    _ports['fw_inside_secondary_port_id'] = neutronlib.create_port(_networks['fw_inside_network_id'],
									hostname=_metadata['hostname']+"-FW-SEC-INSIDE",
									port_security_enabled='False',
									tenant_id=os_project.id)
    except Exception, e:
	logging.exception("Error creating virtual ports. Rolling back port creation! %s" % e)
	# (todo) implement rollback then exit

    return _ports # Return the ports. They will be used to generate the configuration.

def create_lb_ports():
    global _ports

    print "Creating virtual ports in Neutron for load balancer(s)..."

    try:
        # Create ports
        _ports['lb_mgmt_primary_port_id'] = neutronlib.create_port(network_id=_networks['oob_network'],
								hostname=_metadata['hostname']+"-LB-PRI-MGMT",
								port_security_enabled='False',
								description='{"type":"management"}',
								tenant_id=os_project.id)
        _ports['lb_outside_primary_port_id'] = neutronlib.create_port(network_id=_networks['fw_inside_network_id'],
								hostname=_metadata['hostname']+"-LB-PRI-EXTERNAL",
								port_security_enabled='False',
								description='{"type":"outside"}',
                                                                tenant_id=os_project.id)
        _ports['lb_inside_primary_port_id'] = neutronlib.create_port(network_id=_networks['lb_inside_network_id'],
								hostname=_metadata['hostname']+"-LB-PRI-INTERNAL",
								port_security_enabled='False',
								tenant_id=os_project.id)

        # If HA, create a failover port and secondary unit ports
        if _networks['lb_failover_network_name'] is not None:
            _ports['lb_failover_primary_port_id'] = neutronlib.create_port(network_id=_networks['lb_failover_network_id'],
								hostname=_metadata['hostname']+"-LB-PRI-FAILOVER",
								port_security_enabled='False',
								description='{"type":"failover"}',
								tenant_id=os_project.id)
            _ports['lb_failover_secondary_port_id'] = neutronlib.create_port(network_id=_networks['lb_failover_network_id'],
								hostname=_metadata['hostname']+"-LB-SEC-FAILOVER",
								port_security_enabled='False',
								description='{"type":"failover"}',
								tenant_id=os_project.id)
            _ports['lb_mgmt_secondary_port_id'] = neutronlib.create_port(network_id=_networks['oob_network'],
								hostname=_metadata['hostname']+"-LB-SEC-MGMT",
								port_security_enabled='False',
								description='{"type":"management"}',
								tenant_id=os_project.id)
            _ports['lb_outside_secondary_port_id'] = neutronlib.create_port(network_id=_networks['fw_inside_network_id'],
								hostname=_metadata['hostname']+"-LB-SEC-EXTERNAL",
								port_security_enabled='False',
								description='{"type":"outside"}',
								tenant_id=os_project.id)
            _ports['lb_inside_secondary_port_id'] = neutronlib.create_port(network_id=_networks['lb_inside_network_id'],
								hostname=_metadata['hostname']+"-LB-SEC-INTERNAL",
								port_security_enabled='False',
								tenant_id=os_project.id)
    except Exception, e:
        logging.exception("Error creating virtual ports. Rolling back port creation! %s" % e)
        # (todo) implement rollback then exit
	sys.exit(1)
        
    return _ports # Return the ports. They will be used to generate the configuration.

def build_lb_configuration(ha=False):
    # Build the configuration that will be pushed to the devices
    _lb_configuration = {}
    _lb_configuration['lb_hostname'] = _metadata['hostname']
    _lb_configuration['lb_inside_net_addr'] = _networks['lb_inside_net_addr']
    _lb_configuration['lb_inside_mask'] = _networks['lb_inside_mask']
    _lb_configuration['lb_mgmt_primary_address'] = neutronlib.get_fixedip_from_port(_ports['lb_mgmt_primary_port_id'])
    _lb_configuration['lb_mgmt_gateway'],_lb_configuration['lb_mgmt_mask'], = neutronlib.get_gateway_from_port(_ports['lb_mgmt_primary_port_id'])
    _lb_configuration['lb_outside_primary_address'] = neutronlib.get_fixedip_from_port(_ports['lb_outside_primary_port_id'])
    _lb_configuration['lb_outside_gateway'],_lb_configuration['lb_outside_mask'], = neutronlib.get_gateway_from_port(_ports['lb_outside_primary_port_id'])
    _lb_configuration['lb_inside_primary_address'] = neutronlib.get_fixedip_from_port(_ports['lb_inside_primary_port_id'])
    _lb_configuration['lb_inside_netmask'] = neutronlib.get_netmask_from_subnet(_networks['lb_inside_subnet_id'])
    _lb_configuration['lb_inside_segmentation_id'] = _networks['lb_inside_segmentation_id']

    if ha:
        _lb_configuration['lb_failover_primary_address'] = neutronlib.get_fixedip_from_port(_ports['lb_failover_primary_port_id'])
        _lb_configuration['lb_mgmt_secondary_address'] = neutronlib.get_fixedip_from_port(_ports['lb_mgmt_secondary_port_id'])
        _lb_configuration['lb_failover_secondary_address'] = neutronlib.get_fixedip_from_port(_ports['lb_failover_secondary_port_id'])
        _lb_configuration['lb_failover_netmask'] = neutronlib.get_netmask_from_subnet(_networks['lb_failover_subnet_id'])
        _lb_configuration['lb_outside_secondary_address'] = neutronlib.get_fixedip_from_port(_ports['lb_outside_secondary_port_id'])
        _lb_configuration['lb_inside_secondary_address'] = neutronlib.get_fixedip_from_port(_ports['lb_inside_secondary_port_id'])

    return _lb_configuration

def build_fw_configuration(os_project_name,user_name,ha=False):

    # Build the configuration that will be pushed to the devices
    _fw_configuration = {}
    _fw_configuration['fw_hostname'] = _metadata['hostname']
    _fw_configuration['fw_inside_net_addr'] = _networks['fw_inside_net_addr']
    _fw_configuration['fw_inside_mask'] = _networks['fw_inside_mask']
    _fw_configuration['fw_mgmt_primary_address'] = neutronlib.get_fixedip_from_port(_ports['fw_mgmt_primary_port_id'])
    _fw_configuration['fw_mgmt_gateway'],_fw_configuration['fw_mgmt_mask'], = neutronlib.get_gateway_from_port(_ports['fw_mgmt_primary_port_id'])
    _fw_configuration['fw_outside_primary_address'] = neutronlib.get_fixedip_from_port(_ports['fw_outside_primary_port_id'])
    _fw_configuration['fw_outside_gateway'],_fw_configuration['fw_outside_mask'], = neutronlib.get_gateway_from_port(_ports['fw_outside_primary_port_id'])
    _fw_configuration['fw_inside_primary_address'] = neutronlib.get_fixedip_from_port(_ports['fw_inside_primary_port_id'])
    _fw_configuration['fw_inside_netmask'] = neutronlib.get_netmask_from_subnet(_networks['fw_inside_subnet_id'])
    _fw_configuration['fw_inside_segmentation_id'] = _networks['fw_inside_segmentation_id']

    if ha:
	_fw_configuration['fw_failover_primary_address'] = neutronlib.get_fixedip_from_port(_ports['fw_failover_primary_port_id'])
	_fw_configuration['fw_mgmt_secondary_address'] = neutronlib.get_fixedip_from_port(_ports['fw_mgmt_secondary_port_id'])
	_fw_configuration['fw_failover_secondary_address'] = neutronlib.get_fixedip_from_port(_ports['fw_failover_secondary_port_id'])
	_fw_configuration['fw_failover_netmask'] = neutronlib.get_netmask_from_subnet(_networks['fw_failover_subnet_id']) 
	_fw_configuration['fw_outside_secondary_address'] = neutronlib.get_fixedip_from_port(_ports['fw_outside_secondary_port_id'])
	_fw_configuration['fw_inside_secondary_address'] = neutronlib.get_fixedip_from_port(_ports['fw_inside_secondary_port_id'])

    # Build an IPSec Client VPN configuration
    # (todo) Build AnyConnect configuration
    _fw_configuration['tunnel_group'] = os_project_name
    _fw_configuration['group_policy'] = os_project_name
    _fw_configuration['group_password'] = keystonelib.generate_password(16)
    _fw_configuration['vpn_user'] = user_name
    _fw_configuration['vpn_password'] = keystonelib.generate_password(16)

    return _fw_configuration

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

def list_devices():
    servers = novalib.list_instances()

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
	    return True
        else:
	    return False


if __name__ == "__main__":
    # Build the local database used to keep track of resources
    # Should only be done on first execution
    build_db(db_filename,schema_filename)

    parser = argparse.ArgumentParser(prog='moonshine',description='Proof of concept instance deployment \
						tool used to bootstrap and deploy virtual network devices, \
						including firewalls and load balancers')
    subparsers = parser.add_subparsers(help='commands',dest='command')

    # A list command
    list_parser = subparsers.add_parser('list', help='List all virtual network instances')

    # A find command
    find_parser = subparsers.add_parser('find', help='Find virtual network instances')    
    find_parser.add_argument('--env', action='store', dest='env', help='Find instance based on environment number', required=False)
    find_parser.add_argument('--account', action='store', dest='account_number', help='Find instance based on account number', required=False)

    # A create-ports command
    # Moving to creating ports first, then can create instances at-will
    # (todo) use description of the port (with dict) to associate with device and account number
    createports_parser = subparsers.add_parser('create-ports', help='Create virtual network port(s)')
    createports_parser.add_argument('-p','--ports',type=json.loads,
				dest='ports',help='Specifies a list of dict key/value pairs for ports using net-id and fixed-ip')

    createnetworks_parser = subparsers.add_parser('create-networks', help='Create virtual network(s)')
    createnetworks_parser.add_argument('-n','--networks',type=json.loads,
                                dest='network_blob',help='Specifies a list of dict key/value pairs for network using name and cidr')

    create_parser = subparsers.add_parser('create', help='Create virtual network device(s)')

    create_parser.add_argument('-e','--environment', dest='environment_number', 
				help='Specify DCX environment number', required=True)

    create_parser.add_argument('-a','--account', dest='account_number', 
				help='Specify CORE account number', required=True)

    create_parser.add_argument('-d','--device',dest='device_number',
				help='Specify CORE device number', required=True)

    create_parser.add_argument('--fw', dest='fw', help='Specify firewall type', 
				choices=['asav5', 'asav10', 'asav30','vsrx'], required=False)
    create_parser.add_argument('--lb', dest='lb', help='Specify load balancer type', 
				choices=['ltm','netscaler'], required=False)
    create_parser.add_argument('--ha', dest='ha', action='store_true', help='Builds network instances in a highly-available manner', required=False)
    create_parser.add_argument('--vm', dest='vm', action='store_true', help='Builds a virtual machine on the backend', required=False)
    create_parser.set_defaults(ha=False)
    create_parser.set_defaults(lb=None)
    create_parser.set_defaults(vm=False)

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
        logging.exception("Unable to create networks! %s" % e)

    # create-ports
    try:
	if args.command == 'create-ports':
	    print json.dumps(args.ports)
	    sys.exit(1)
    except Exception, e:
	logging.exception("Bummer %s" % e)

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
	    list_devices()
	    sys.exit(1)
    except Exception, e:
	logging.exception("Oops! Unable to list! %s" % e)

    # The CREATE parser
    # (todo) Build it so that an individual device can be created and added to an environment
    # For now, all devices are created at launch
    try:
	if args.command == 'create':
	    # (todo) Tie environments into Keystone tenants.
	    # Check for tenant/project before proceeding. Maybe notify user?
	    print "Creating devices for environment %s in account %s" % (args.env,args.account_number)
	    create(args)
    except Exception, e:
	logging.exception("Oops! Unable to create! %s" % e)
