from library.database import *
import library.neutron as neutronlib
import textwrap, json, sys
import netaddr

def generate_configuration(db_filename,instance_blob,self_ports,peer_ports):
    dbmgr = DatabaseManager(db_filename)
    # The ASA configuration will match between devices with the exception of device priority

    # Assemble device information that will be passed to other functions
    data = {}
    data['hostname'] = instance_blob['environment_number'] + '-' + instance_blob['account_number'] + '-' + instance_blob['device_number']
    data['priority'] = instance_blob['device_priority']
    
    if 'standalone' in data['priority']:
        subnet_id = neutronlib.get_subnet_from_port(self_ports[0])
        data['standby_keyword'] = ''
        data['pri_mgmt_addr'] = neutronlib.get_fixedip_from_port(self_ports[0])
        data['pri_mgmt_netmask'] = neutronlib.get_netmask_from_subnet(subnet_id)
        data['sec_mgmt_address'] = ''
        data['mgmt_gateway'] = neutronlib.get_gateway_from_port(self_ports[0])
    elif 'primary' in data['priority']:
    	data['peerid'] = '2'
        subnet_id = neutronlib.get_subnet_from_port(self_ports[0])
        data['standby_keyword'] = 'standby'
        data['pri_mgmt_addr'] = neutronlib.get_fixedip_from_port(self_ports[0])
        data['pri_mgmt_netmask'] = neutronlib.get_netmask_from_subnet(subnet_id)
        data['sec_mgmt_address'] = neutronlib.get_fixedip_from_port(peer_ports[0])
        data['mgmt_gateway'] = neutronlib.get_gateway_from_port(self_ports[0])
    elif 'secondary' in data['priority']:
    	data['peerid'] = '1'
        subnet_id = neutronlib.get_subnet_from_port(self_ports[0])
        data['standby_keyword'] = 'standby'
        data['pri_mgmt_addr'] = neutronlib.get_fixedip_from_port(peer_ports[0])
        data['pri_mgmt_netmask'] = neutronlib.get_netmask_from_subnet(subnet_id)
        data['sec_mgmt_address'] = neutronlib.get_fixedip_from_port(self_ports[0])
        data['mgmt_gateway'] = neutronlib.get_gateway_from_port(self_ports[0])    
    
    
    configuration = generate_base_netscaler_config(data)
    configuration += generate_interface_config(db_filename,data,self_ports,peer_ports)
    configuration += generate_netscaler_failover_config(data)
    configuration += generate_default_route(db_filename,instance_blob['device_number'],data['mgmt_gateway'])
    configuration += save_configuration()

    return configuration
    
def save_configuration():
    netscaler_config = '''
        nscli -u :nsroot:nsroot savec
    '''

    return textwrap.dedent(netscaler_config)
    
def generate_default_route(db_filename,device_number,mgmt_gateway_ip):
    # Generates default route for outside interface
    dbmgr = DatabaseManager(db_filename)
    data = {}
    result = dbmgr.query("select port_id from ports where port_name='fw_inside' and device_number=?",
                                ([device_number]))

    data['mgmt_gateway'] = mgmt_gateway_ip
    data['port_id'] = result.fetchone()[0]
    data['gateway_ip'] = neutronlib.get_gateway_from_port(data['port_id'])

    if data['gateway_ip'] is not None:
        route = """
            nscli remove route 0.0.0.0 0.0.0.0 {mgmt_gateway}
            nscli add route 0.0.0.0 0.0.0.0 {gateway_ip}
            nscli add route 10.0.0.0 255.0.0.0 {mgmt_gateway}
        """.format(**data)
    else:
        route = ""

    return textwrap.dedent(route)

def generate_base_netscaler_config(data):
    # (todo) implement base key injection

    # Generate the base configuration
    netscaler_config = '''
        # Save initial configuration
        nscli -u :nsroot:nsroot savec

        # Add additional configuration
        nscli -u :nsroot:nsroot set ns hostName {hostname}

        nscli -u :nsroot:nsroot add dns nameServer 8.8.8.8
        nscli -u :nsroot:nsroot add dns nameServer 8.8.4.4 
    '''.format(**data)

    return textwrap.dedent(netscaler_config)
    
def generate_interface_config(db_filename,data,self_ports,peer_ports):
    dbmgr = DatabaseManager(db_filename)

    self_ports.pop(0) # Pop out the first port, since we've already handled management interface
    if peer_ports: # If empty, peer_ports will evaluate as false
        peer_ports.pop(0)
        
    # Generate the interface configuration as well as interface ACL
    interface_config = ""
    index = 0 # Start with the 0 index
    interface_num = 1
    localvlan = 4092 # Start with local VLAN tag (not tagged)
    
    for port_id in self_ports:
        result = dbmgr.query("select port_name from ports where port_id=?",
                                ([port_id]))
        port_name = result.fetchone()[0]

        subnet_id = neutronlib.get_subnet_from_port(port_id)
        interface = {}
        interface['port_name'] = port_name
        interface['mtu'] = neutronlib.get_mtu_from_port(port_id)
        interface['mss'] = int(interface['mtu']) - 120

        interface['pri_addr'] = neutronlib.get_fixedip_from_port(self_ports[index])
        interface['netmask'] = neutronlib.get_netmask_from_subnet(subnet_id)
            
        # Only generate full interface for non-failover port
        if not 'failover' in interface['port_name']:
            interface_config += """
                ! Interfaces built in order as passed to script.
                ! First is management, then outside, then inside, etc.
                ! Failover interface must be named 'failover'
                nscli -u :nsroot:nsroot add vlan {0}
                nscli -u :nsroot:nsroot add ns ip {pri_addr} {netmask} -vServer DISABLED
                nscli -u :nsroot:nsroot bind vlan {0} -ifnum 1/{2}
                nscli -u :nsroot:nsroot bind vlan {0} -IPAddress {pri_addr} {netmask}

                
            """.format(localvlan,index,interface_num,**interface)

        index += 1 # Iterate the index and loop back through
        localvlan -= 1 # Decrement the localvlan and loop back through
        interface_num += 1

    return textwrap.dedent(interface_config)
                

def generate_netscaler_failover_config(data):

    if 'primary' in data['priority']:
        netscaler_failover_config = '''
            nscli -u :nsroot:nsroot add node {peerid} {sec_mgmt_addr}
            nscli -u :nsroot:nsroot set rpcnode {pri_mgmt_addr} -password @penstack1234
            nscli -u :nsroot:nsroot set rpcnode {sec_mgmt_addr} -password @penstack1234
        '''.format(**data)
    elif 'secondary' in data['priority']:
        netscaler_failover_config = '''
            nscli -u :nsroot:nsroot add node {peerid} {pri_mgmt_addr}
            nscli -u :nsroot:nsroot set rpcnode {pri_mgmt_addr} -password @penstack1234
            nscli -u :nsroot:nsroot set rpcnode {sec_mgmt_addr} -password @penstack1234
        '''.format(**data)
    else:
        netscaler_failover_config = ""
        
    return textwrap.dedent(netscaler_failover_config)
