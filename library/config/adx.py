from library.database import *
import library.neutron as neutronlib  
import textwrap
from textwrap import dedent as dedent
import json, sys
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
    startup_prefix = """\
        #vadx-openstack
        commit_post_init_commands=true
        startup_config=\"\"\"
        """

    configuration += textwrap.dedent(startup_prefix)    
    # Generate base configuration
    configuration += generate_base_configuration(data)

    startup_suffix = """\
        \"\"\"
        """
    configuration += textwrap.dedent(startup_suffix)

    postinit_prefix = """\
        post_init_commands=\"\"\"
        conf t
        crypto key generate rsa
        """
    configuration += textwrap.dedent(postinit_prefix)

    # Generate management interface configuration
    configuration += generate_management_interface_config(data)

    # Generate other interface config
    configuration += generate_interface_config(db_filename,data,self_ports,peer_ports)

    postinit_suffix = """\
        exit
        \"\"\"
        """
    configuration += textwrap.dedent(postinit_suffix)

    print configuration
    return configuration    

def generate_management_interface_config(data):
    # Begin interface configuration.
    # Interface management 1 is management (first attached interface)

    management_interface = """
        int management 1
        dhcp-client disable
        ip address {pri_mgmt_addr} {pri_mgmt_netmask}
        exit

        ip route 10.0.0.0 255.240.0.0 {mgmt_gateway}
        ip route 10.16.0.0 255.254.0.0 {mgmt_gateway}
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
	    # Interfaces built in order as passed to script.
            # First is management, then outside, then inside, etc.
            interface_config += """

                interface e{0}
                enable
                ip address {pri_addr} {netmask}
                exit

            """.format(index+1,**interface) # We add 1 since e1 will be the first interface after mgmt

	index += 1 # Iterate the index and loop back through

    return textwrap.dedent(interface_config)

def generate_base_configuration(data):

    configuration = """
        ssl clear all
        ssl set export-master-pswd rack 

        hostname {hostname}
        ip dns domain-name rackspace.com

        """.format(**data)

    return textwrap.dedent(configuration)
