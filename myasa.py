import requests, json, sys
from pprint import pprint
#from neutronclient.v2_0 import client
#from prettytable import PrettyTable
from library.neutron import create_port,create_network,get_fixedip_from_port,add_address_pair
from library.neutron import get_gateway_from_port,get_netmask_from_subnet,create_subnet
from library.config import generate_base_config,generate_failover_config
from library.nova import boot_server,random_server_name

outside_net = '463bbed0-a84a-4c7c-8783-d73113d7e830'
management_net_id = '780734d4-bc1f-4ddd-8acd-cd574ce90aa4'

#inside_net = 'fcf1f6c8-8b0d-486a-9dbc-547d4f747be4'
#dmz_net = '5cea766e-ff12-4726-a808-f910d0aba8d8'
#failover_net = '0caa9a6d-2f45-4932-acde-acd79cc9c5d4'

#endpoint_url = 'http://controller01:9696/'
#token = '20d3c9c027a24c248298f4780a9baf0e'

def main(hostname,management_network):

    #
    # Create management interface and base configuration
#    management_port = create_port(management_network,hostname)
#    management_address = get_fixedip_from_port(management_port)

    _base_info = {}
    _base_info['hostname'] = hostname
    _base_info['mgmt_primary_port'] = create_port(management_network,hostname+"_MGMT")
    _base_info['mgmt_secondary_port'] = create_port(management_network,hostname+"_MGMT")
    _base_info['mgmt_primary_address'] = get_fixedip_from_port(_base_info['mgmt_primary_port'])
    _base_info['mgmt_secondary_address'] = get_fixedip_from_port(_base_info['mgmt_secondary_port'])
    _base_info['management_gateway'],_base_info['management_mask'], = get_gateway_from_port(_base_info['mgmt_primary_port'])

    # Add the respective address to the other port
    add_address_pair(_base_info['mgmt_primary_port'],_base_info['mgmt_secondary_address'])
    add_address_pair(_base_info['mgmt_secondary_port'],_base_info['mgmt_primary_address'])

    #
    # Create failover network
    _failover_info = {}
    _failover_info['failover_network_name'] = hostname + "_FAILOVER_NET"
    _failover_info['failover_net'] = create_network(_failover_info['failover_network_name'],network_type="")
    _failover_info['failover_subnet'] = create_subnet(_failover_info['failover_net'],cidr="10.253.0.0/29")
#    _failover_info['failover_net'] = '27712262-9855-4f1d-8f87-fb7436e1a1ba'
    _failover_info['failover_primary_port'] = create_port(_failover_info['failover_net'],hostname+"_FAILOVER")
    _failover_info['failover_secondary_port'] = create_port(_failover_info['failover_net'],hostname+"_FAILOVER")
    _failover_info['failover_primary_address'] = get_fixedip_from_port(_failover_info['failover_primary_port'])
    _failover_info['failover_secondary_address'] = get_fixedip_from_port(_failover_info['failover_secondary_port'])
    _failover_info['failover_netmask'] = get_netmask_from_subnet(_failover_info['failover_subnet'])

    # Add the respective address to the other port
    add_address_pair(_failover_info['failover_primary_port'],_failover_info['failover_secondary_address'])
    add_address_pair(_failover_info['failover_secondary_port'],_failover_info['failover_primary_address'])
 
    _device_info = {}
    _device_info.update(_base_info)
    _device_info.update(_failover_info)

    # Create an outside port for the firewall
#    outside_address,outside_port = create_port(network)
    
#    _network_info = {}
#    _network_info['outside_address'] = outside_address
#    _network_info['gateway_ip'],_network_info['outside_mask'], = get_gateway_from_port(outside_port)

#    print _network_info    
#    print generate_asa_config(_network_info)

    print "Creating ASA with the following attributes:"

#    print pprint(_base_info)
#    print pprint(_failover_info)
    print pprint(_device_info)
    
    # Generate primary ASA config
#    _failover_info['priority'] = 'primary'
#    asa_config = generate_base_config(_base_info)
#    asa_config += generate_failover_config(_failover_info)

    
#    print asa_config

    # Boot the primary ASA
    print "Launching primary ASA"
    _failover_info['priority'] = 'primary'
    asa_config = generate_base_config(_base_info)
    asa_config += generate_failover_config(_failover_info)
    print asa_config
    ports = {'mgmt':_base_info['mgmt_primary_port'],'failover':_failover_info['failover_primary_port']}
    server = boot_server(hostname,ports,asa_config)

    # Boot the secondary ASA
    print "Launching secondary ASA"
    _failover_info['priority'] = 'secondary'
    asa_config = generate_base_config(_base_info)
    asa_config += generate_failover_config(_failover_info)
    print asa_config
    ports = {'mgmt':_base_info['mgmt_secondary_port'],'failover':_failover_info['failover_secondary_port']}
    server = boot_server(hostname,ports,asa_config) 

if __name__ == "__main__":
        hostname = random_server_name()
        main(hostname,management_network=management_net_id)
