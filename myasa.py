import requests, json, sys
from pprint import pprint
#from neutronclient.v2_0 import client
#from prettytable import PrettyTable
import library.neutron as neutronlib
import library.config as configlib
import library.nova as novalib 

outside_network = '67dae4e7-f64f-4144-8cc5-880414501f6c'
management_net_id = '21f730af-6cac-4486-900a-9da00c5d8e70'

def main(hostname,management_network):

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
    _failover_info['failover_net'] = neutronlib.create_network(_failover_info['failover_network_name'],network_type="")
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

    _device_info = {}
    _device_info.update(_base_info)
    _device_info.update(_failover_info)

    print "Creating ASA with the following attributes:"
    print pprint(_device_info)
    
    # Boot the primary ASA
    print "Launching primary ASA"
    _failover_info['priority'] = 'primary'
    asa_config = configlib.generate_base_config(_base_info)
    asa_config += configlib.generate_failover_config(_failover_info)
    print asa_config
    ports = {'mgmt':_base_info['mgmt_primary_port'],'failover':_failover_info['failover_primary_port'],'outside':_base_info['outside_primary_port']}
    server = novalib.boot_server(hostname,ports,asa_config,az="ZONE-A")

    # Boot the secondary ASA
    print "Launching secondary ASA"
    _failover_info['priority'] = 'secondary'
    asa_config = configlib.generate_base_config(_base_info)
    asa_config += configlib.generate_failover_config(_failover_info)
    print asa_config
    ports = {'mgmt':_base_info['mgmt_secondary_port'],'failover':_failover_info['failover_secondary_port'],'outside':_base_info['outside_secondary_port']}
    server = novalib.boot_server(hostname,ports,asa_config,az="ZONE-B") 

if __name__ == "__main__":
        hostname = novalib.random_server_name()
        main(hostname,management_network=management_net_id)
