import requests, json, sys
import argparse, time
from prettytable import PrettyTable
import library.neutron as neutronlib
import library.config as configlib
import library.nova as novalib
import library.keystone as keystonelib
from library.printf import printf

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
    if lb is not None:
	_networks['fw_inside_network_name'] = hostname + "-FW-LB"
	fw_inside_network = neutronlib.create_network(network_name=_networks['fw_inside_network_name'])
	dhcp=False
	inside_cidr = "192.168.254.0/24" # (todo) Allow this to be set on CLI
	_networks['fw_inside_net_addr'] = "192.168.254.0" # (todo) make this discoverable
	_networks['fw_inside_mask'] = "255.255.255.240"
	_networks['fw_inside_gateway'] = "192.168.254.1" # This needs to be set based on the primary IP of the FW. Which means we need to ask for this addr when creating the port!
    else:
	_networks['fw_inside_network_name'] = hostname + "-FW-INSIDE"
	fw_inside_network = neutronlib.create_network(network_name=_networks['fw_inside_network_name'],
						network_type="vlan")	
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
							enable_dhcp=dhcp)

    # Create FAILOVER network if highly-available
    if ha:
	_networks['fw_failover_network_name'] = hostname + "-FW-FAILOVER"
	fw_failover_network = neutronlib.create_network(network_name=_networks['fw_failover_network_name'])
	_networks['fw_failover_network_id'] = fw_failover_network["network"]["id"]
	failover_cidr = "192.168.255.0/28"
	_networks['fw_failover_subnet_id'] = neutronlib.create_subnet(network_id=_networks['fw_failover_network_id'],
								cidr=failover_cidr)
    else:
	_networks['fw_failover_network_name'] = None
	fw_failover_network = None # (todo) verify if this is necessary

    return _networks # Return the list. It will be used to create ports.

def create_lb_networks(hostname,ha,_networks):
    print "Creating virtual networks in Neutron for load balancer(s)..."
    
    # Create INSIDE network (where servers live)
    _networks['lb_inside_network_name'] = hostname + "-LB-INSIDE"
    lb_inside_network = neutronlib.create_network(network_name=_networks['lb_inside_network_name'],
						network_type="vlan")
    dhcp=True
    inside_cidr = "192.168.100.0/24"
    _networks['lb_inside_net_addr'] = "192.168.100.0" # (todo) make this discoverable
    _networks['lb_inside_mask'] = "255.255.255.0"
    _networks['lb_inside_gateway'] = "192.168.100.1"

    _networks['lb_inside_network_id'] = lb_inside_network["network"]["id"]
    _networks['lb_inside_subnet_id'] = neutronlib.create_subnet(network_id=_networks['lb_inside_network_id'],
							cidr=inside_cidr,
							gateway=_networks['lb_inside_gateway'],
							enable_dhcp=dhcp)
    _networks['lb_inside_segmentation_id'] = neutronlib.get_segment_id_from_network(lb_inside_network["network"]["id"])

    # Create FAILOVER network if highly-available
    if ha:
        _networks['lb_failover_network_name'] = hostname + "-LB-FAILOVER"
        lb_failover_network = neutronlib.create_network(network_name=_networks['lb_failover_network_name'])
	dhcp=False
        _networks['lb_failover_network_id'] = lb_failover_network["network"]["id"]
        failover_cidr = "192.168.255.16/28"
        _networks['lb_failover_subnet_id'] = neutronlib.create_subnet(network_id=_networks['lb_failover_network_id'],
								cidr=failover_cidr)
    else:
        _networks['lb_failover_network_name'] = None
        lb_failover_network = None # (todo) verify if this is necessary

    return _networks # Return the list. It will be used to create ports.
    
def create_fw_ports(hostname,_networks):
    
    print "Creating virtual ports in Neutron for firewall(s)..."

    try:
        # Create ports
        _ports = {}
        _ports['fw_mgmt_primary_port_id'] = neutronlib.create_port(network_id=management_network_id,
								hostname=hostname+"-FW-PRI-MGMT")
        _ports['fw_outside_primary_port_id'] = neutronlib.create_port(network_id=outside_network_id,
								hostname=hostname+"-FW-PRI-OUTSIDE")
        _ports['fw_inside_primary_port_id'] = neutronlib.create_port(network_id=_networks['fw_inside_network_id'],
								hostname=hostname+"-FW-PRI-INSIDE",
								subnet_id=_networks['fw_inside_subnet_id'],
								ip_address=_networks['fw_inside_gateway'])

        # If HA, create a failover port and secondary unit ports
        if _networks['fw_failover_network_name'] is not None:
	    _ports['fw_failover_primary_port_id'] = neutronlib.create_port(network_id=_networks['fw_failover_network_id'],
									hostname=hostname+"-FW-PRI-FAILOVER")
	    _ports['fw_failover_secondary_port_id'] = neutronlib.create_port(network_id=_networks['fw_failover_network_id'],
									hostname=hostname+"-FW-SEC-FAILOVER")
	    _ports['fw_mgmt_secondary_port_id'] = neutronlib.create_port(network_id=management_network_id,
									hostname=hostname+"-FW-SEC-MGMT")
	    _ports['fw_outside_secondary_port_id'] = neutronlib.create_port(network_id=outside_network_id,
									hostname=hostname+"-FW-SEC-OUTSIDE")
	    _ports['fw_inside_secondary_port_id'] = neutronlib.create_port(_networks['fw_inside_network_id'],hostname=hostname+"-FW-SEC-INSIDE")
    except Exception, e:
	print "Error creating virtual ports. Rolling back port creation! %s" % e
	# (todo) implement rollback then exit

    return _ports # Return the ports. They will be used to generate the configuration.

def create_lb_ports(hostname,_networks,_ports):

    print "Creating virtual ports in Neutron for load balancer(s)..."

    try:
        # Create ports
        _ports['lb_mgmt_primary_port_id'] = neutronlib.create_port(network_id=management_network_id,
								hostname=hostname+"-LB-PRI-MGMT")
        _ports['lb_outside_primary_port_id'] = neutronlib.create_port(network_id=_networks['fw_inside_network_id'],
								hostname=hostname+"-LB-PRI-EXTERNAL")
        _ports['lb_inside_primary_port_id'] = neutronlib.create_port(network_id=_networks['lb_inside_network_id'],
								hostname=hostname+"-LB-PRI-INTERNAL")

        # If HA, create a failover port and secondary unit ports
        if _networks['lb_failover_network_name'] is not None:
            _ports['lb_failover_primary_port_id'] = neutronlib.create_port(network_id=_networks['lb_failover_network_id'],
								hostname=hostname+"-LB-PRI-FAILOVER")
            _ports['lb_failover_secondary_port_id'] = neutronlib.create_port(network_id=_networks['lb_failover_network_id'],
								hostname=hostname+"-LB-SEC-FAILOVER")
            _ports['lb_mgmt_secondary_port_id'] = neutronlib.create_port(network_id=management_network_id,
								hostname=hostname+"-LB-SEC-MGMT")
            _ports['lb_outside_secondary_port_id'] = neutronlib.create_port(network_id=_networks['fw_inside_network_id'],
								hostname=hostname+"-LB-SEC-EXTERNAL")
            _ports['lb_inside_secondary_port_id'] = neutronlib.create_port(network_id=_networks['lb_inside_network_id'],
								hostname=hostname+"-LB-SEC-INTERNAL")
    except Exception, e:
        print "Error creating virtual ports. Rolling back port creation! %s" % e
        # (todo) implement rollback then exit
	sys.exit(1)
        
    return _ports # Return the ports. They will be used to generate the configuration.

def build_lb_configuration(hostname,ha=False):
    # Build the configuration that will be pushed to the devices
    _lb_configuration = {}
    _lb_configuration['lb_hostname'] = hostname
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

def build_fw_configuration(hostname,project_name,user_name,ha=False):

    # Build the configuration that will be pushed to the devices
    _fw_configuration = {}
    _fw_configuration['fw_hostname'] = hostname
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
    _fw_configuration['tunnel_group'] = project_name
    _fw_configuration['group_policy'] = project_name
    _fw_configuration['group_password'] = keystonelib.generate_password(16)
    _fw_configuration['vpn_user'] = user_name
    _fw_configuration['vpn_password'] = keystonelib.generate_password(16)

    return _fw_configuration

def launch_firewall(ha,fw,_ports,_fw_configuration,fw_image,fw_flavor):

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
    primary_fw = novalib.boot_server(hostname,fw_image,fw_flavor,ports,primary_config,az,file_path)

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
        secondary_fw = novalib.boot_server(hostname,fw_image,fw_flavor,ports,secondary_config,az,file_path) 

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

def launch_loadbalancer(ha,lb,_ports,_lb_configuration,lb_image,lb_flavor):

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

    primary_lb = novalib.boot_lb(hostname,lb_image,lb_flavor,ports,primary_config,az="ZONE-A")
    
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

	ports = []
        ports.append({'mgmt':_ports['lb_mgmt_secondary_port_id']})
        ports.append({'outside':_ports['lb_outside_secondary_port_id']})
        ports.append({'inside':_ports['lb_inside_secondary_port_id']})
        ports.append({'failover':_ports['lb_failover_secondary_port_id']})

        secondary_lb = novalib.boot_lb(hostname,lb_image,lb_flavor,ports,secondary_config,az="ZONE-B")
  
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

    vm_hostname = hostname + "-VM"
    instance = novalib.boot_vm(vm_hostname,network_id,vm_image,vm_flavor,az="ZONE-A")

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

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='nfv.py - NFV PoC that build virtual firewalls and load balancers')

    parser.add_argument('--fw', dest='fw', help='Specify firewall type', choices=['asav5', 'asav10', 'asav30','vsrx'], required=True)
    parser.add_argument('--lb', dest='lb', help='Specify load balancer type', choices=['ltm','netscaler'], required=False)
    parser.add_argument('--ha', dest='ha', action='store_true', help='Builds network devices in a highly-available manner', required=False)
    parser.add_argument('--vm', dest='vm', action='store_true', help='Builds a virtual machine on the backend', required=False)
    parser.set_defaults(ha=False)
    parser.set_defaults(lb=None)
    parser.set_defaults(vm=False)

    # Array for all arguments passed to script
    args = parser.parse_args()

    # Validate that there is an image and flavor for each specified option
    # (todo) build validator

    try:
        with open('config.json') as config_file:    
            config = json.load(config_file)
        
	outside_network_id = config['networks']['outside']
	management_network_id = config['networks']['mgmt']

        fw_image = config['firewall'][args.fw]['image']
        fw_flavor = config['firewall'][args.fw]['flavor']

	if args.lb is not None:
	    lb_image = config['loadbalancer'][args.lb]['image']
	    lb_flavor = config['loadbalancer'][args.lb]['flavor']

	if args.vm:
	    vm_image = config['vm']['image']
	    vm_flavor = config['vm']['flavor']

    except Exception, e:
        print "Error loading config file! %s" % e
	sys.exit(1)

    # Launch the device(s)
    hostname = novalib.random_server_name()
    keystone_project,keystone_user = create_project()

    # Create networks
    _networks = create_fw_networks(hostname,args.ha,args.lb)
    if args.lb is not None:
	_networks.update(create_lb_networks(hostname,args.ha,_networks))

    # Create ports
    _ports = create_fw_ports(hostname,_networks)
    if args.lb is not None:
	_ports.update(create_lb_ports(hostname,_networks,_ports))

    # Launch devices
    print "Launching devices... (This operation can take a while for large images.)"
    _fw_configuration = build_fw_configuration(hostname,keystone_project.name,keystone_user.name,args.ha)
    launch_firewall(args.ha,args.fw,_ports,_fw_configuration,fw_image,fw_flavor)

    if args.lb is not None: # If user is spinning up load balancers, launch 'em behind the FW
        _lb_configuration = build_lb_configuration(hostname,args.ha)
        launch_loadbalancer(args.ha,args.lb,_ports,_lb_configuration,lb_image,lb_flavor)

    # If --vm is specified, launch a VM in the backend INSIDE network that can be reachable from the web
    # (todo) Cleanup the dict/array with the configuration and networks
    if args.vm:
	network_id = _networks['fw_inside_network_id']
	if args.lb is not None:
	    network_id = _networks['lb_inside_network_id']
	launch_instance(network_id,vm_image,vm_flavor)
