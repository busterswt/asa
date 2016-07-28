from library.database import *
import library.neutron as neutronlib  
import textwrap, json, sys
import netaddr

def generate_configuration(db_filename,instance_blob,self_ports,peer_ports):
    data = {}
    data['hostname'] = instance_blob['environment_number'] + '-' + str(instance_blob['account_number']) + '-' + instance_blob['device_number']

    subnet_id = neutronlib.get_subnet_from_port(self_ports[0])
    data['pri_mgmt_addr'] = neutronlib.get_fixedip_from_port(self_ports[0])
    data['pri_mgmt_netmask'] = neutronlib.get_netmask_from_subnet(subnet_id)
    data['mgmt_gateway'] = neutronlib.get_gateway_from_port(self_ports[0])
    data['priority'] = instance_blob['device_priority']

    configuration = ""
    # Generate base configuration
    configuration += generate_base_configuration(data)

    # Generate management interface configuration
    configuration += generate_management_interface_config(data)

    # Generate other interface config
    configuration += generate_interface_config(db_filename,data,self_ports,peer_ports)

    return configuration

def generate_management_interface_config(data):
    management_interface = """
        ! Begin interface configuration.
        ! Interface GigabitEthernet1 is management (first attached interface)
        ip vrf mgmt-vrf

        interface GigabitEthernet1
        no shutdown
        ip vrf forwarding mgmt-vrf
        ip address {pri_mgmt_addr} {pri_mgmt_netmask}

        ip route vrf mgmt-vrf 0.0.0.0 0.0.0.0 {mgmt_gateway} 1
        """.format(**data)

    return textwrap.dedent(management_interface)

def generate_interface_config(db_filename,data,self_ports,peer_ports):
    dbmgr = DatabaseManager(db_filename)

    self_ports.pop(0) # Pop out the first port, since we've already handled management interface
    if peer_ports: # If empty, peer_ports will evaluate as false
        peer_ports.pop(0)

    # Generate the interface configuration as well as interface ACL
    interface_config = ""
    index = 0 # Start with the 0 index

    for port_id in self_ports:
        result = dbmgr.query("select port_name from ports where port_id=?",
                                ([port_id]))
        port_name = result.fetchone()[0]

        subnet_id = neutronlib.get_subnet_from_port(port_id)
        interface = {}
        interface['port_name'] = port_name
        interface['mtu'] = neutronlib.get_mtu_from_port(port_id)
        interface['mss'] = int(interface['mtu']) - 120

        if 'standalone' in data['priority']:
            interface['standby_keyword'] = ''
            interface['pri_addr'] = neutronlib.get_fixedip_from_port(self_ports[index])
            interface['netmask'] = neutronlib.get_netmask_from_subnet(subnet_id)
            interface['sec_addr'] = ''

        # Only generate full interface for non-failover port
        if not 'failover' in interface['port_name']:
            interface_config += """
                ! Interfaces built in order as passed to script.
                ! First is management, then outside, then inside, etc.
                ! Failover interface must be named 'failover'
                interface GigabitEthernet{0}
                no shut
                description {port_name}  
                ip address {pri_addr} {netmask}
            """.format(index+2,**interface) # We add 2 since GigabitEthernet2 will be the first interface after mgmt

	index += 1 # Iterate the index and loop back through

    return textwrap.dedent(interface_config)

def generate_base_configuration(data):

    configuration = """line con 0
        logging synchronous
        transport preferred none
    
        line vty 0 4
        login local
        transport preferred none
        transport input ssh
    
        username moonshine priv 15 secret openstack12345

        hostname {hostname}
        ip domain name moonshine.rackspace.com
        crypto key generate rsa modulus 1024
    
        ip ssh version 2
        ip ssh pubkey-chain
        username moonshine
        key-string
        exit
    
        netconf max-sessions 16
        netconf ssh
        """.format(**data)

    return textwrap.dedent(configuration)
