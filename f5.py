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

#def generate_firewall_config(hostname,project_name,user_name,management_network,ha,lb):

def create_fw_ports(hostname,_networks):
    
    print "Creating virtual ports in Neutron for load balancer %s..." % hostname

    try:
        # Create ports
        _ports = {}
        _ports['fw_mgmt_primary_port_id'] = neutronlib.create_port(management_network_id,hostname+"-UNIT1-MGMT")
#        _ports['fw_outside_primary_port_id'] = neutronlib.create_port(outside_network_id,hostname+"-PRI-OUTSIDE")
#        _ports['fw_inside_primary_port_id'] = neutronlib.create_port(_networks['fw_inside_network_id'],hostname+"-PRI-INSIDE")

        # If HA, create a failover port and secondary unit ports
        if _networks['fw_failover_network_name'] is not None:
	    _ports['fw_failover_primary_port_id'] = neutronlib.create_port(_networks['fw_failover_network_id'],hostname+"PRI-FAILOVER")
	    _ports['fw_failover_secondary_port_id'] = neutronlib.create_port(_networks['fw_failover_network_id'],hostname+"SEC-FAILOVER")
	    _ports['fw_mgmt_secondary_port_id'] = neutronlib.create_port(management_network_id,hostname+"-SEC-MGMT")
#	    _ports['fw_outside_secondary_port_id'] = neutronlib.create_port(outside_network_id,hostname+"-SEC-OUTSIDE")
#	    _ports['fw_inside_secondary_port_id'] = neutronlib.create_port(_networks['fw_inside_network_id'],hostname+"_INSIDE")
    except Exception, e:
	print "Error creating virtual ports. Rolling back port creation! %s" % e
	# (todo) implement rollback then exit

    return _ports # Return the ports. They will be used to generate the configuration.

def launch_firewall(ha,_ports,_device_configuration):

    image_id = 'eea922aa-f07f-42c4-a4a7-19025e0eda00'
    flavor_id = '3c00dddc-8a48-4c5e-82e2-aa53db455818'

    # Boot the primary ASA
    print "Launching primary load balancer..."
    _device_configuration['priority'] = 'primary'
#    primary_config = configlib.generate_config(ha,_device_configuration)
    primary_config = ''
    
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
    print details

    print "Please wait a few minutes while your firewall(s) come online."

    print "In the meantime, you can view the console of the firewall by opening the following URL in a browser: "
    print novalib.get_console(primary_fw)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='nfv.py - NFV PoC that build virtual firewalls and load balancers')

    flavor = parser.add_mutually_exclusive_group(required=False)
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
    _ports,_device_configuration = build_firewall_configuration(hostname,keystone_project.name,keystone_user.name,args.ha,args.lb)
    launch_firewall(args.ha,_ports,_device_configuration)


#    _device_configuration = generate_firewall_config(hostname,new_project.name,new_user.name,management_network=management_net_id)
#    launch(_device_configuration)
    
