import requests, json, sys
import argparse, time
from prettytable import PrettyTable
import library.neutron as neutronlib
import library.config as configlib
import library.nova as novalib
import library.keystone as keystonelib

outside_network_id = '8c5726e0-9ee8-4bca-810d-78cffb2b281f'
management_network_id = 'c9e8b39d-c8e2-43ed-817a-c1022a3aadc9'
firewall_image_id = ''

def create_project():

    print "Creating Keystone project and user..."

    try:
        account_number = keystonelib.generate_random_account()
        keystone_project = keystonelib.create_project(account_number)
        password = keystonelib.generate_password(10)
        keystone_user = keystonelib.create_user(account_number,keystone_project.id,password)
    except Exception, e:
	print "Unable to create project and user in Keystone. Rolling back! %s" % e
	# (todo) rollback and exit gracefully

    # Return the new project id that will be used when creating resources
    return keystone_project,keystone_user

def create_fw_networks(hostname,ha,lb):    
    print "Creating virtual networks in Neutron for firewall(s)..."

    _networks = {}
    # Create INSIDE (or transit) network
    if lb:
	_networks['fw_inside_network_name'] = hostname + "-FW-LB"
	fw_inside_network = neutronlib.create_network(_networks['fw_inside_network_name'],network_type="vxlan")
	inside_cidr = "192.168.0.0/24" # (todo) Allow this to be set on CLI
	_networks['fw_inside_net_addr'] = "192.168.0.0" # (todo) make this discoverable
	_networks['fw_inside_mask'] = "255.255.255.0"
    else:
	_networks['fw_inside_network_name'] = hostname + "-FW-INSIDE"
	fw_inside_network = neutronlib.create_network(_networks['fw_inside_network_name'],network_type="vlan")	
	inside_cidr = "192.168.254.0/28"
        _networks['fw_inside_net_addr'] = "192.168.254.0" # (todo) make this discoverable
        _networks['fw_inside_mask'] = "255.255.255.240"

    _networks['fw_inside_network_id'] = fw_inside_network["network"]["id"]
    _networks['fw_inside_subnet_id'] = neutronlib.create_subnet(_networks['fw_inside_network_id'],inside_cidr)


    # Create FAILOVER network if highly-available
    if ha:
	_networks['fw_failover_network_name'] = hostname + "-FW-FAILOVER"
	fw_failover_network = neutronlib.create_network(_networks['fw_failover_network_name'],network_type="vxlan")
	_networks['fw_failover_network_id'] = fw_failover_network["network"]["id"]
	failover_cidr = "192.168.255.0/28"
	_networks['fw_failover_subnet_id'] = neutronlib.create_subnet(_networks['fw_failover_network_id'],failover_cidr)
    else:
	_networks['fw_failover_network_name'] = None
	fw_failover_network = None # (todo) verify if this is necessary

    return _networks # Return the list. It will be used to create ports.

def create_lb_networks(hostname,ha,_networks):
    print "Creating virtual networks in Neutron for load balancer(s)..."
    
    # Create INSIDE network (where servers live)
    _networks['lb_inside_network_name'] = hostname + "-LB-INSIDE"
    lb_inside_network = neutronlib.create_network(_networks['lb_inside_network_name'],network_type="vlan")
    inside_cidr = "192.168.100.0/24"
    _networks['lb_inside_net_addr'] = "192.168.100.0" # (todo) make this discoverable
    _networks['lb_inside_mask'] = "255.255.255.0"

    _networks['lb_inside_network_id'] = lb_inside_network["network"]["id"]
    _networks['lb_inside_subnet_id'] = neutronlib.create_subnet(_networks['lb_inside_network_id'],inside_cidr)


    # Create FAILOVER network if highly-available
    if ha:
        _networks['lb_failover_network_name'] = hostname + "-LB-FAILOVER"
        lb_failover_network = neutronlib.create_network(_networks['lb_failover_network_name'],network_type="vxlan")
        _networks['lb_failover_network_id'] = lb_failover_network["network"]["id"]
        failover_cidr = "192.168.255.16/28"
        _networks['lb_failover_subnet_id'] = neutronlib.create_subnet(_networks['lb_failover_network_id'],failover_cidr)
    else:
        _networks['lb_failover_network_name'] = None
        lb_failover_network = None # (todo) verify if this is necessary

    return _networks # Return the list. It will be used to create ports.
    
def create_fw_ports(hostname,_networks):
    
    print "Creating virtual ports in Neutron for firewall(s)..."

    try:
        # Create ports
        _ports = {}
        _ports['fw_mgmt_primary_port_id'] = neutronlib.create_port(management_network_id,hostname+"-PRI-MGMT")
        _ports['fw_outside_primary_port_id'] = neutronlib.create_port(outside_network_id,hostname+"-PRI-OUTSIDE")
        _ports['fw_inside_primary_port_id'] = neutronlib.create_port(_networks['fw_inside_network_id'],hostname+"-PRI-INSIDE")

        # If HA, create a failover port and secondary unit ports
        if _networks['fw_failover_network_name'] is not None:
	    _ports['fw_failover_primary_port_id'] = neutronlib.create_port(_networks['fw_failover_network_id'],hostname+"-PRI-FAILOVER")
	    _ports['fw_failover_secondary_port_id'] = neutronlib.create_port(_networks['fw_failover_network_id'],hostname+"-SEC-FAILOVER")
	    _ports['fw_mgmt_secondary_port_id'] = neutronlib.create_port(management_network_id,hostname+"-SEC-MGMT")
	    _ports['fw_outside_secondary_port_id'] = neutronlib.create_port(outside_network_id,hostname+"-SEC-OUTSIDE")
	    _ports['fw_inside_secondary_port_id'] = neutronlib.create_port(_networks['fw_inside_network_id'],hostname+"-SEC-INSIDE")
    except Exception, e:
	print "Error creating virtual ports. Rolling back port creation! %s" % e
	# (todo) implement rollback then exit

    return _ports # Return the ports. They will be used to generate the configuration.

def create_lb_ports(hostname,_networks,_ports):

    print "Creating virtual ports in Neutron for load balancer(s)..."

    try:
        # Create ports
        _ports['lb_mgmt_primary_port_id'] = neutronlib.create_port(management_network_id,hostname+"-PRI-MGMT")
        _ports['lb_outside_primary_port_id'] = neutronlib.create_port(_networks['fw_inside_network_id'],hostname+"-PRI-EXTERNAL")
        _ports['lb_inside_primary_port_id'] = neutronlib.create_port(_networks['lb_inside_network_id'],hostname+"-PRI-INTERNAL")

        # If HA, create a failover port and secondary unit ports
        if _networks['lb_failover_network_name'] is not None:
            _ports['lb_failover_primary_port_id'] = neutronlib.create_port(_networks['lb_failover_network_id'],hostname+"PRI-FAILOVER")
            _ports['lb_failover_secondary_port_id'] = neutronlib.create_port(_networks['lb_failover_network_id'],hostname+"SEC-FAILOVER")
            _ports['lb_mgmt_secondary_port_id'] = neutronlib.create_port(management_network_id,hostname+"-SEC-MGMT")
            _ports['lb_outside_secondary_port_id'] = neutronlib.create_port(_networks['fw_inside_network_id'],hostname+"-SEC-EXTERNAL")
            _ports['lb_inside_secondary_port_id'] = neutronlib.create_port(_networks['lb_inside_network_id'],hostname+"-SEC-INTERNAL")
    except Exception, e:
        print "Error creating virtual ports. Rolling back port creation! %s" % e
        # (todo) implement rollback then exit
        
    return _ports # Return the ports. They will be used to generate the configuration.

def build_lb_configuration(hostname,ha=False):
    # Build the configuration that will be pushed to the devices
    _device_configuration = {}
    _device_configuration['lb_hostname'] = hostname
    _device_configuration['lb_inside_net_addr'] = _networks['lb_inside_net_addr']
    _device_configuration['lb_inside_mask'] = _networks['lb_inside_mask']
    _device_configuration['lb_mgmt_primary_address'] = neutronlib.get_fixedip_from_port(_ports['lb_mgmt_primary_port_id'])
    _device_configuration['lb_mgmt_gateway'],_device_configuration['lb_mgmt_mask'], = neutronlib.get_gateway_from_port(_ports['lb_mgmt_primary_port_id'])
    _device_configuration['lb_outside_primary_address'] = neutronlib.get_fixedip_from_port(_ports['lb_outside_primary_port_id'])
    _device_configuration['lb_outside_gateway'],_device_configuration['lb_outside_mask'], = neutronlib.get_gateway_from_port(_ports['lb_outside_primary_port_id'])
    _device_configuration['lb_inside_primary_address'] = neutronlib.get_fixedip_from_port(_ports['lb_inside_primary_port_id'])
    _device_configuration['lb_inside_netmask'] = neutronlib.get_netmask_from_subnet(_networks['lb_inside_subnet_id'])

    if ha:
        _device_configuration['lb_failover_primary_address'] = neutronlib.get_fixedip_from_port(_ports['lb_failover_primary_port_id'])
        _device_configuration['lb_mgmt_secondary_address'] = neutronlib.get_fixedip_from_port(_ports['lb_mgmt_secondary_port_id'])
        _device_configuration['lb_failover_secondary_address'] = neutronlib.get_fixedip_from_port(_ports['lb_failover_secondary_port_id'])
        _device_configuration['lb_failover_netmask'] = neutronlib.get_netmask_from_subnet(_networks['lb_failover_subnet_id'])
        _device_configuration['lb_outside_secondary_address'] = neutronlib.get_fixedip_from_port(_ports['lb_outside_secondary_port_id'])
        _device_configuration['lb_inside_secondary_address'] = neutronlib.get_fixedip_from_port(_ports['lb_inside_secondary_port_id'])

    return _device_configuration

def build_fw_configuration(hostname,project_name,user_name,ha=False,lb=False):

    # Build the configuration that will be pushed to the devices
    _device_configuration = {}
    _device_configuration['fw_hostname'] = hostname
    _device_configuration['fw_inside_net_addr'] = _networks['fw_inside_net_addr']
    _device_configuration['fw_inside_mask'] = _networks['fw_inside_mask']
    _device_configuration['fw_mgmt_primary_address'] = neutronlib.get_fixedip_from_port(_ports['fw_mgmt_primary_port_id'])
    _device_configuration['fw_mgmt_gateway'],_device_configuration['fw_mgmt_mask'], = neutronlib.get_gateway_from_port(_ports['fw_mgmt_primary_port_id'])
    _device_configuration['fw_outside_primary_address'] = neutronlib.get_fixedip_from_port(_ports['fw_outside_primary_port_id'])
    _device_configuration['fw_outside_gateway'],_device_configuration['fw_outside_mask'], = neutronlib.get_gateway_from_port(_ports['fw_outside_primary_port_id'])
    _device_configuration['fw_inside_primary_address'] = neutronlib.get_fixedip_from_port(_ports['fw_inside_primary_port_id'])
    _device_configuration['fw_inside_netmask'] = neutronlib.get_netmask_from_subnet(_networks['fw_inside_subnet_id'])

    if ha:
	_device_configuration['fw_failover_primary_address'] = neutronlib.get_fixedip_from_port(_ports['fw_failover_primary_port_id'])
	_device_configuration['fw_mgmt_secondary_address'] = neutronlib.get_fixedip_from_port(_ports['fw_mgmt_secondary_port_id'])
	_device_configuration['fw_failover_secondary_address'] = neutronlib.get_fixedip_from_port(_ports['fw_failover_secondary_port_id'])
	_device_configuration['fw_failover_netmask'] = neutronlib.get_netmask_from_subnet(_networks['fw_failover_subnet_id']) 
	_device_configuration['fw_outside_secondary_address'] = neutronlib.get_fixedip_from_port(_ports['fw_outside_secondary_port_id'])
	_device_configuration['fw_inside_secondary_address'] = neutronlib.get_fixedip_from_port(_ports['fw_inside_secondary_port_id'])

    # Build an IPSec Client VPN configuration
    # (todo) Build AnyConnect configuration
    _device_configuration['tunnel_group'] = project_name
    _device_configuration['group_policy'] = project_name
    _device_configuration['group_password'] = keystonelib.generate_password(16)
    _device_configuration['vpn_user'] = user_name
    _device_configuration['vpn_password'] = keystonelib.generate_password(16)

    return _device_configuration

def launch_firewall(ha,_ports,_device_configuration):

    image_id = 'ec535aa8-d15d-4205-a821-6b8eae952559'
    flavor_id = '4928fddd-8101-4c2e-a834-7fa22345092f'

    # Boot the primary ASA
    print "Launching primary firewall..."
    _device_configuration['priority'] = 'primary'
    primary_config = configlib.generate_config(ha,_device_configuration)
    
    # If ha, build out a failover port. Otherwise don't. These need to be in a specific order for the ASA.
    if ha:
	ports = {'mgmt':_ports['fw_mgmt_primary_port_id'],
		'failover':_ports['fw_failover_primary_port_id'],
		'outside':_ports['fw_outside_primary_port_id'],
		'inside':_ports['fw_inside_primary_port_id']
		}
    else:
	ports = {'mgmt':_ports['fw_mgmt_primary_port_id'],
                'outside':_ports['fw_outside_primary_port_id'],
                'inside':_ports['fw_inside_primary_port_id']
                }
    primary_fw = novalib.boot_server(hostname,image_id,flavor_id,ports,primary_config,az="ZONE-A",file_path="day0")

    # Check to see if VM state is ACTIVE.
    print "Waiting for primary firewall %s to go ACTIVE..." % primary_fw.id
    status = novalib.check_status(primary_fw.id)
    while not status == "ACTIVE":
	if status == "ERROR":
	    print "Instance is in ERROR state. No sense in moving on..." # (todo) build some graceful delete
	    sys.exit(1)
	else:
	    time.sleep(1)
            status = novalib.check_status(primary_fw.id)

    if ha:
	# Boot the secondary ASA
        print "Launching secondary firewall..."
        _device_configuration['priority'] = 'secondary'
        secondary_config = configlib.generate_config(ha,_device_configuration)
        ports = {'mgmt':_ports['fw_mgmt_secondary_port_id'],
		'failover':_ports['fw_failover_secondary_port_id'],
		'outside':_ports['fw_outside_secondary_port_id'],
		'inside':_ports['fw_inside_secondary_port_id']
		}
        secondary_fw = novalib.boot_server(hostname,image_id,flavor_id,ports,secondary_config,az="ZONE-B",file_path="day0") 

        # Check to see if VM state is ACTIVE.
        # (todo) Will want to put an ERROR check in here so we can move on
        print "Waiting for secondary firewall %s to go ACTIVE..." % secondary_fw.id
        status = novalib.check_status(secondary_fw.id)
        while not status == "ACTIVE":
            if status == "ERROR":
                print "Instance is in ERROR state. No sense in moving on..." # (todo) build some graceful delete
                sys.exit(1)
            else:
                time.sleep(1)
                status = novalib.check_status(secondary_fw.id)

    print "Please wait a few minutes while your firewall(s) come online."

    details = PrettyTable(["Parameter", "Value"])
    details.align["Parameter"] = "l" # right align
    details.align["Value"] = "l" # left align
    details.add_row(["Primary IP:",_device_configuration['fw_outside_primary_address']])
    details.add_row(["Primary Management IP:",_device_configuration['fw_mgmt_primary_address']])

    # Only print secondary details if ha
    if ha:
        details.add_row(["Secondary IP:",_device_configuration['fw_outside_secondary_address']])
        details.add_row(["Secondary Management IP:",_device_configuration['fw_mgmt_secondary_address']])

    details.add_row(["",""])
    details.add_row(["VPN Endpoint:",_device_configuration['fw_outside_primary_address']])
    details.add_row(["VPN Group Name:",_device_configuration['tunnel_group']])
    details.add_row(["VPN Group Password:",_device_configuration['group_password']])
    details.add_row(["VPN Username:",_device_configuration['vpn_user']])
    details.add_row(["VPN Password:",_device_configuration['vpn_password']])
    details.add_row(["",""])
    details.add_row(["Primary Console:",novalib.get_console(primary_fw)])

    if ha:
	details.add_row(["Secondary Console:",novalib.get_console(secondary_fw)])
    print details

def launch_loadbalancer(ha,_ports,_lb_configuration):

    image_id = '131a4bb6-ad5a-4f36-9a38-436bd1c968dd'
    flavor_id = '8203ba21-ede0-48a4-8877-8bbdec75163c'

    # Boot the primary load balancer
    print "Launching primary load balancer..."
    #_lb_configuration['priority'] = 'primary'
    primary_config = configlib.generate_f5_config(ha,_lb_configuration)
    # JD delete
    print primary_config
    # If ha, build out a failover port. Otherwise don't. These need to be in a specific order for the LB.
    if ha:
        ports = {'mgmt':_ports['lb_mgmt_primary_port_id'],
                'failover':_ports['lb_failover_primary_port_id'],
                'outside':_ports['lb_outside_primary_port_id'],
                'inside':_ports['lb_inside_primary_port_id']
                }
    else:
        ports = {'mgmt':_ports['lb_mgmt_primary_port_id'],
                'outside':_ports['lb_outside_primary_port_id'],
                'inside':_ports['lb_inside_primary_port_id']
                }

    primary_lb = novalib.boot_server(hostname,image_id,flavor_id,ports,primary_config,az="ZONE-A",file_path='/config/user_data.json')
    
    # Check to see if VM state is ACTIVE.
    print "Waiting for primary load balancer %s to go ACTIVE..." % primary_lb.id
    status = novalib.check_status(primary_lb.id)
    while not status == "ACTIVE":
        if status == "ERROR":
            print "Instance is in ERROR state. No sense in moving on..." # (todo) build some graceful delete
            sys.exit(1)
        else:
            time.sleep(1)
            status = novalib.check_status(primary_lb.id)

    if ha:
        # Boot the secondary LB
        print "Launching secondary load balancer..."
        #_device_configuration['priority'] = 'secondary'
        secondary_config = configlib.generate_f5_config(ha,_lb_configuration)
        ports = {'mgmt':_ports['lb_mgmt_secondary_port_id'],
                'failover':_ports['lb_failover_secondary_port_id'],
                'outside':_ports['lb_outside_secondary_port_id'],
                'inside':_ports['lb_inside_secondary_port_id']
                }
        secondary_lb = novalib.boot_server(hostname,image_id,flavor_id,ports,secondary_config,az="ZONE-B",file_path='/config/user_data.json')
  
        # Check to see if VM state is ACTIVE.
        # (todo) Will want to put an ERROR check in here so we can move on
        print "Waiting for secondary load balancer %s to go ACTIVE..." % secondary_lb.id
        status = novalib.check_status(secondary_lb.id)
        while not status == "ACTIVE":
            if status == "ERROR":
                print "Instance is in ERROR state. No sense in moving on..." # (todo) build some graceful delete
                sys.exit(1)
            else:
                time.sleep(1)
                status = novalib.check_status(secondary_lb.id)

    print "Please wait a few minutes while your load balancer(s) come online."

    details = PrettyTable(["Parameter", "Value"])
    details.align["Parameter"] = "l" # right align
    details.align["Value"] = "l" # left align
    details.add_row(["Primary Management IP:",_lb_configuration['lb_mgmt_primary_address']])
    
    # Only print secondary details if ha
    if ha:
        details.add_row(["Secondary Management IP:",_lb_configuration['lb_mgmt_secondary_address']])        

    details.add_row(["Primary Console:",novalib.get_console(primary_lb)])
    if ha:
	details.add_row(["Secondary Console:",novalib.get_console(secondary_lb)])
    print details

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='nfv.py - NFV PoC that build virtual firewalls and load balancers')

    flavor = parser.add_mutually_exclusive_group(required=False)
#    flavor.add_argument('--small', dest='flavor', action='store', help='Builds a small device', required=False, default='4928fddd-8101-4c2e-a834-7fa22345092f')
#    flavor.add_argument('--medium', dest='flavor', action='store', help='Builds a medium device', required=False, default='513d599f-0f31-451f-837b-6bb89f587c93')
#    flavor.add_argument('--large', dest='flavor', action='store', help='Builds a large device', required=False, default='2c581a1c-b0ef-4f32-bb04-6b6b8da35a0a')
#    group.add_argument('--tenant-id', dest='tenant_id', type=str, help='Provides floating IPs related to provided tenant ID', required=False, default=None)
    parser.add_argument('--lb', dest='lb', action='store_true', help='Builds a firewall and load balancer (routed mode)', required=False)
    parser.add_argument('--ha', dest='ha', action='store_true', help='Builds network devices in a highly-available manner', required=False)
    parser.set_defaults(lb=False)
    parser.set_defaults(ha=False)
    parser.set_defaults(flavor='4928fddd-8101-4c2e-a834-7fa22345092f')

    # Array for all arguments passed to script
    args = parser.parse_args()

    # Launch the device(s)
    hostname = novalib.random_server_name()
    keystone_project,keystone_user = create_project()

    # Create networks and ports
    _networks = create_fw_networks(hostname,args.ha,args.lb)
    if args.lb:
	#_networks += create_lb_networks(hostname,args.ha,_networks)
	_networks.update(create_lb_networks(hostname,args.ha,_networks))

    _ports = create_fw_ports(hostname,_networks)
    if args.lb:
	#_ports += create_lb_ports(hostname,_networks,_ports)
	_ports.update(create_lb_ports(hostname,_networks,_ports))

    _fw_configuration = build_fw_configuration(hostname,keystone_project.name,keystone_user.name,args.ha,args.lb)
    launch_firewall(args.ha,_ports,_fw_configuration)

    if args.lb: # If user is spinning up load balancers, launch 'em behind the FW
        _lb_configuration = build_lb_configuration(hostname,args.ha)
        launch_loadbalancer(args.ha,_ports,_lb_configuration)

    
