import requests, json, sys
from clients import neutron
import netaddr

def create_network(network_name,**kwargs):
    # Creates a network and returns the object
    
    network = {}
    network["network"] = {}
    network["network"]["name"] = network_name
    network["network"]["admin_state_up"] = 'True'
    
    # Set the network type {vxlan,vlan}
    if kwargs.get('network_type') is not None:
	network["network"]['provider:network_type'] = kwargs.get('network_type')
    else:
	network["network"]['provider:network_type'] = 'vxlan' # Default to vxlan if type isn't specified

    # Set the segmentation id
    if kwargs.get('segmentation_id') is not None:
        network["network"]['provider:segmentation_id'] = kwargs.get('segmentation_id')

    # Set the tenant/project id
    if kwargs.get('tenant_id') is not None:
	network['network']['tenant_id'] = kwargs.get('tenant_id')

    # For now, desc is json with metadata about network
    if kwargs.get('description') is not None:
	network['network']['description'] = kwargs.get('description')

    return neutron.create_network(body=network)

def get_segment_id_from_network(network_id):
    # Given a network id, returns the segmentation id
  
    network_details = neutron.show_network(network_id)
    segmentation_id = network_details["network"]["provider:segmentation_id"]
    network_type = network_details["network"]["provider:network_type"]

    if network_type != "vlan":
	segmentation_id = "N/A"

    return segmentation_id

def create_subnet(network_id,cidr,**kwargs):
    # Creates a subnet and returns the subnet id

    subnet = {}
    subnet['subnet'] = {}
    subnet['subnet']['network_id'] = network_id
    subnet['subnet']['cidr'] = cidr

    # Specify IP version
    if kwargs.get('ip_version') is not None:
	subnet['subnet']['ip_version'] = kwargs.get('ip_version')
    else:
	subnet['subnet']['ip_version'] = '4' # Default to IPv4 if not specified 	

    # Specify gateway address for subnet
    if kwargs.get('gateway_ip') is not None:
        subnet['subnet']['gateway_ip'] = kwargs.get('gateway_ip')

    # Enable/Disable DHCP for subnet
    if kwargs.get('enable_dhcp') is not None:
        subnet['subnet']['enable_dhcp'] = kwargs.get('enable_dhcp')
    else:
        subnet['subnet']['enable_dhcp'] = 'False' # Default to False if not specified

    # Set the tenant/project id
    if kwargs.get('tenant_id') is not None:
        subnet['subnet']['tenant_id'] = kwargs.get('tenant_id')

    return neutron.create_subnet(body=subnet)

def add_address_pair(port_id,ip_address,mac_address=None):
    # This function is UNUSED at this time (but works)
    # Port security is disabled on all ports by default

    if mac_address is None:
        mac_address = get_macaddr_from_port(port_id)

    entry = {'ip_address':ip_address,'mac_address':mac_address}
    port_details = neutron.show_port(port_id)
    address_pairs = port_details["port"]["allowed_address_pairs"]

    address_pairs.append(dict(entry))

    req = { 
        "port": { 
            "allowed_address_pairs": address_pairs
        }
    }

    response = neutron.update_port(port_id, req)    

def create_port(network_id,**kwargs):
    # Creates a port and returns the port id

    port = {}
    port["port"] = {}
    port["port"]["admin_state_up"] = 'True'
    port["port"]["network_id"] = network_id

    # Set port security true/false if specified. Otherwise use to Neutron default.
    if kwargs.get('port_security_enabled') is not None:
        port["port"]["port_security_enabled"] = kwargs.get('port_security_enabled')

    # Manually set IP of port
    if kwargs.get('ip_address') is not None:
        port["port"]["fixed_ips"] = []
	if kwargs.get('subnet_id') is not None:
            port["port"]["fixed_ips"].append({'subnet_id':kwargs.get('subnet_id'),
					'ip_address':kwargs.get('ip_address')})
	else:
	    port["port"]["fixed_ips"].append({'ip_address':kwargs.get('ip_address')})

    # Set port name if specified
    if kwargs.get('port_name') is not None:
	port["port"]["name"] = kwargs.get('port_name')

    # Add description (json)
    if kwargs.get('description') is not None:
	port["port"]["description"] = kwargs.get('description')

    # Set the tenant/project id
    if kwargs.get('tenant_id') is not None:
        port['port']['tenant_id'] = kwargs.get('tenant_id')

    return neutron.create_port(body=port)

def get_fixedip_from_port(port_id):
    # Returns the (first) fixed IP of a port

    port_details = neutron.show_port(port_id)
    fixed_ip = port_details["port"]["fixed_ips"][0]["ip_address"]

    return fixed_ip

def get_macaddr_from_port(port_id):
    # Returns the MAC address of a port

    port_details = neutron.show_port(port_id)
    mac_addr = port_details["port"]["mac_address"]

    return mac_addr

def get_gateway_from_port(port_id):

    port_details = neutron.show_port(port_id)
    subnet_id = port_details["port"]["fixed_ips"][0]["subnet_id"]    
    subnet_details = neutron.show_subnet(subnet_id)
    gateway_ip = subnet_details["subnet"]["gateway_ip"]
#    subnet_mask = get_netmask_from_subnet(subnet_id)

    return gateway_ip

def get_subnet_from_port(port_id):

    port_details = neutron.show_port(port_id)
    subnet_id = port_details["port"]["fixed_ips"][0]["subnet_id"]

    return subnet_id

def get_network_netmask_from_subnet(subnet_id):
    # Get address string and CIDR string from command line
    subnet_details = neutron.show_subnet(subnet_id)
    subnet_cidr = subnet_details["subnet"]["cidr"]

    network_addr = str(netaddr.IPNetwork(subnet_cidr).network)
    network_netmask = str(netaddr.IPNetwork(subnet_cidr).netmask)
    return network_addr,network_netmask

def get_netmask_from_subnet(subnet_id):
    
    # Get address string and CIDR string from command line
    subnet_details = neutron.show_subnet(subnet_id)
    subnet_cidr = subnet_details["subnet"]["cidr"]
    (addrString, cidrString) = subnet_cidr.split('/')
    cidr = int(cidrString)

    # Initialize the netmask and calculate based on CIDR mask
    mask = [0, 0, 0, 0]
    for i in range(cidr):
	mask[i/8] = mask[i/8] + (1 << (7 - i % 8))

    # Print information, mapping integer lists to strings for easy printing
    subnet_mask = ".".join(map(str, mask))
    return subnet_mask

def list_ports(device_id=None,type=None):
    # (todo) test this heavily
    if type is not None:
	ports = neutron.list_ports(device_id=device_id,description='{"type":"%s"}' % type)
    else:
        ports = neutron.list_ports(device_id=device_id)
    return ports

def update_port_dns_name(port_id,hostname):
    req = {
        "port": {
            "dns_name": hostname
        }
    }

    return neutron.update_port(port_id,req)

def delete_port(port_id):
    return neutron.delete_port(port_id)

def delete_network(network_id):
    return neutron.delete_network(network_id)

def get_mtu_from_port(port_id):
    # Returns the network MTU
    # If 0 and vxlan, sets to 1450 (safe value)
    port_details = neutron.show_port(port_id)
    network_id = port_details["port"]["network_id"]
    network_details = neutron.show_network(network_id)
    network_mtu = network_details["network"]["mtu"]
    network_type = network_details["network"]["provider:network_type"]

    if network_mtu == '0':
        if 'vxlan' in network_type:
	    network_mtu = '1450'
	elif 'vlan' in network_type:
	    network_mtu = '1500'

    return network_mtu

