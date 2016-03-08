import requests, json, sys
from pprint import pprint
#from neutronclient.v2_0 import client
from prettytable import PrettyTable
import library.neutron as neutronlib
import library.config as configlib
import library.nova as novalib 
import library.keystone as keystonelib

outside_network = '67dae4e7-f64f-4144-8cc5-880414501f6c'
management_net_id = '21f730af-6cac-4486-900a-9da00c5d8e70'

def create_project():
    print "Generating account number..."
    account_number = keystonelib.generate_random_account()
    print "Creating tenant..."
    new_tenant = keystonelib.create_tenant(account_number)
    print "Tenant Name: %s" % new_tenant.name
    print "Tenant ID: %s" % new_tenant.id

    print "Creating user..."
    password = keystonelib.generate_password(10)
    new_user = keystonelib.create_user(account_number,new_tenant.id,password)
    print "Username: %s" % new_user.name
    print "Password: %s" % password

    # Return the new tenant id that will be used when creating resources
    return new_tenant,new_user

def generate_config(hostname,tenant_name,user_name,management_network):

    # Create management interface and base configuration
    _base_info = {}
    _base_info['hostname'] = hostname
    _base_info['mgmt_primary_port'] = neutronlib.create_port(management_network,hostname+"_MGMT")
    _base_info['mgmt_secondary_port'] = neutronlib.create_port(management_network,hostname+"_MGMT")
    _base_info['mgmt_primary_address'] = neutronlib.get_fixedip_from_port(_base_info['mgmt_primary_port'])
    _base_info['mgmt_primary_mac'] = neutronlib.get_macaddr_from_port(_base_info['mgmt_primary_port'])
    _base_info['mgmt_secondary_address'] = neutronlib.get_fixedip_from_port(_base_info['mgmt_secondary_port'])
    _base_info['mgmt_secondary_mac'] = neutronlib.get_macaddr_from_port(_base_info['mgmt_secondary_port'])
    _base_info['management_gateway'],_base_info['management_mask'], = neutronlib.get_gateway_from_port(_base_info['mgmt_primary_port'])

    # Add the respective address to the other port (port security requirement)
    neutronlib.add_address_pair(_base_info['mgmt_primary_port'],_base_info['mgmt_secondary_address'],_base_info['mgmt_secondary_mac'])
    neutronlib.add_address_pair(_base_info['mgmt_secondary_port'],_base_info['mgmt_primary_address'],_base_info['mgmt_primary_mac'])

    # Create failover network
    _failover_info = {}
    _failover_info['failover_network_name'] = hostname + "_FAILOVER_NET"
    failover_network = neutronlib.create_network(_failover_info['failover_network_name'],network_type="vxlan")
#    _failover_info['failover_net'] = neutronlib.create_network(_failover_info['failover_network_name'],network_type="vxlan")
    _failover_info['failover_net'] = failover_network["network"]["id"]
    _failover_info['failover_subnet'] = neutronlib.create_subnet(_failover_info['failover_net'],cidr="10.253.0.0/29")
    _failover_info['failover_primary_port'] = neutronlib.create_port(_failover_info['failover_net'],hostname+"_FAILOVER")
    _failover_info['failover_secondary_port'] = neutronlib.create_port(_failover_info['failover_net'],hostname+"_FAILOVER")
    _failover_info['failover_primary_address'] = neutronlib.get_fixedip_from_port(_failover_info['failover_primary_port'])
    _failover_info['failover_primary_mac'] = neutronlib.get_macaddr_from_port(_failover_info['failover_primary_port'])
    _failover_info['failover_secondary_address'] = neutronlib.get_fixedip_from_port(_failover_info['failover_secondary_port'])
    _failover_info['failover_secondary_mac'] = neutronlib.get_macaddr_from_port(_failover_info['failover_secondary_port'])
    _failover_info['failover_netmask'] = neutronlib.get_netmask_from_subnet(_failover_info['failover_subnet'])

    # Add the respective address to the other port
    neutronlib.add_address_pair(_failover_info['failover_primary_port'],_failover_info['failover_secondary_address'],_failover_info['failover_secondary_mac'])
    neutronlib.add_address_pair(_failover_info['failover_secondary_port'],_failover_info['failover_primary_address'],_failover_info['failover_primary_mac'])
 
    # OUTSIDE INTERFACE
    _base_info['outside_primary_port'] = neutronlib.create_port(outside_network,hostname+"_OUTSIDE")
    _base_info['outside_secondary_port'] = neutronlib.create_port(outside_network,hostname+"_OUTSIDE")
    _base_info['outside_primary_address'] = neutronlib.get_fixedip_from_port(_base_info['outside_primary_port'])
    _base_info['outside_primary_mac'] = neutronlib.get_macaddr_from_port(_base_info['outside_primary_port'])
    _base_info['outside_secondary_address'] = neutronlib.get_fixedip_from_port(_base_info['outside_secondary_port'])
    _base_info['outside_secondary_mac'] = neutronlib.get_macaddr_from_port(_base_info['outside_secondary_port'])
    _base_info['outside_gateway'],_base_info['outside_mask'], = neutronlib.get_gateway_from_port(_base_info['outside_primary_port'])

    # Add the respective address to the other port
    neutronlib.add_address_pair(_base_info['outside_primary_port'],_base_info['outside_secondary_address'],_base_info['outside_secondary_mac'])
    neutronlib.add_address_pair(_base_info['outside_secondary_port'],_base_info['outside_primary_address'],_base_info['outside_primary_mac'])

    # INSIDE INTERFACE
    _inside_info = {}
    inside_network = neutronlib.create_network("INSIDE",network_type="vlan")
    inside_segmentation_id = inside_network["network"]["provider:segmentation_id"]
    print inside_segmentation_id
    inside_cidr = "192.168.%s.0/24" % inside_segmentation_id
    _inside_info['inside_net_addr'] = "192.168.%s.0" % inside_segmentation_id
    _inside_info['inside_subnet'] = neutronlib.create_subnet(inside_network["network"]["id"],inside_cidr)
    _inside_info['inside_primary_port'] = neutronlib.create_port(inside_network["network"]["id"],hostname+"_INSIDE")
    _inside_info['inside_secondary_port'] = neutronlib.create_port(inside_network["network"]["id"],hostname+"_INSIDE")
    _inside_info['inside_primary_address'] = neutronlib.get_fixedip_from_port(_inside_info['inside_primary_port'])
    _inside_info['inside_primary_mac'] = neutronlib.get_macaddr_from_port(_inside_info['inside_primary_port'])
    _inside_info['inside_secondary_address'] = neutronlib.get_fixedip_from_port(_inside_info['inside_secondary_port'])
    _inside_info['inside_secondary_mac'] = neutronlib.get_macaddr_from_port(_inside_info['inside_secondary_port'])
    _inside_info['inside_netmask'] = neutronlib.get_netmask_from_subnet(_inside_info['inside_subnet'])

    # Add the respective address to the other port
    neutronlib.add_address_pair(_inside_info['inside_primary_port'],_inside_info['inside_secondary_address'],_inside_info['inside_secondary_mac'])
    neutronlib.add_address_pair(_inside_info['inside_secondary_port'],_inside_info['inside_primary_address'],_inside_info['inside_primary_mac'])

    #debug
    print pprint(_inside_info)

    _vpn_info = {}
    _vpn_info['tunnel_group'] = tenant_name
    _vpn_info['group_policy'] = tenant_name
    _vpn_info['group_password'] = keystonelib.generate_password(16)
    _vpn_info['vpn_user'] = user_name
    _vpn_info['vpn_password'] = keystonelib.generate_password(16)

    _device_configuration = {}
    _device_configuration.update(_base_info)
    _device_configuration.update(_failover_info)
    _device_configuration.update(_inside_info)
    _device_configuration.update(_vpn_info)

    return _device_configuration

def launch(_device_configuration):
    
    # Boot the primary ASA
    print "Launching primary ASA..."
    _device_configuration['priority'] = 'primary'
    #print pprint(_device_configuration)
    asa_config = configlib.generate_base_config(_device_configuration)
    ports = {'mgmt':_device_configuration['mgmt_primary_port'],'failover':_device_configuration['failover_primary_port'],'outside':_device_configuration['outside_primary_port'],'inside':_device_configuration['inside_primary_port']}
    server1 = novalib.boot_server(hostname,ports,asa_config,az="ZONE-A")

    # Check to see if VM state is ACTIVE.
    print "Waiting for instance %s to go ACTIVE..." % server1.id
    status = novalib.check_status(server1.id)
    while not status == "ACTIVE":
        status = novalib.check_status(server1.id)

    # Boot the secondary ASA
    print "Launching secondary ASA..."
    _device_configuration['priority'] = 'secondary'
    #print pprint(_device_configuration)
    asa_config = configlib.generate_base_config(_device_configuration)
    ports = {'mgmt':_device_configuration['mgmt_secondary_port'],'failover':_device_configuration['failover_secondary_port'],'outside':_device_configuration['outside_secondary_port'],'inside':_device_configuration['inside_secondary_port']}
    server2 = novalib.boot_server(hostname,ports,asa_config,az="ZONE-B") 

    # Check to see if VM state is ACTIVE.
    # (todo) Will want to put an ERROR check in here so we can move on
    print "Waiting for instance %s to go ACTIVE..." % server2.id
    status = novalib.check_status(server2.id)
    while not status == "ACTIVE":
        status = novalib.check_status(server2.id)

    print "Firewall details:"
    details = PrettyTable(["Parameter", "Value"])
    details.align["Parameter"] = "r" # right align
    details.align["Value"] = "l" # left align
    details.add_row(["Primary IP:",_device_configuration['outside_primary_address']])
    details.add_row(["Secondary IP:",_device_configuration['outside_secondary_address']])
    details.add_row(["Primary Management IP:",_device_configuration['mgmt_primary_address']])
    details.add_row(["Secondary Management IP:",_device_configuration['mgmt_secondary_address']])
    details.add_row(["",""])
    details.add_row(["VPN Endpoint:",_device_configuration['outside_primary_address']])
    details.add_row(["VPN Group Name:",_device_configuration['tunnel_group']])
    details.add_row(["VPN Group Password:",_device_configuration['group_password']])
    details.add_row(["VPN Username:",_device_configuration['vpn_user']])
    details.add_row(["VPN Password:",_device_configuration['vpn_password']])
    print details
    print "Please wait a few minutes while your firewall is brought online."

    print "In the meantime, you can view the console of the firewall by opening the following URL in a browser: "
    print novalib.get_console(server1)

if __name__ == "__main__":
    hostname = novalib.random_server_name()
    new_tenant,new_user = create_project()
    _device_configuration = generate_config(hostname,new_tenant.name,new_user.name,management_network=management_net_id)
    launch(_device_configuration)
