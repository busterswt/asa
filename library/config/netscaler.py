import textwrap, json

def generate_netscaler_config(ha,data):
    config = generate_base_netscaler_config(data)

    # Generate failover configuration (if ha)
    if ha:
        config += generate_netscaler_failover_config(data)

    return config

def generate_base_netscaler_config(data):
    # (todo) implement base key injection
    # (todo) implement ha configuration

    # Fix hostnames
    if data['priority'] == 'primary':
	data['my_hostname'] = data['lb_hostname']+'-Unit1'
    else:
	data['my_hostname'] = data['lb_hostname']+'-Unit2'

    # Generate the base configuration
    netscaler_config = '''
        # Save initial configuration
        nscli -u :nsroot:nsroot savec

        # Add additional configuration
        nscli -u :nsroot:nsroot set ns hostName {my_hostname}
        nscli -u :nsroot:nsroot add vlan 4092
        nscli -u :nsroot:nsroot add vlan 4091
        nscli -u :nsroot:nsroot add ns ip {lb_outside_primary_address} {lb_outside_mask} -vServer DISABLED
        nscli -u :nsroot:nsroot add ns ip {lb_inside_primary_address} {lb_inside_mask} -vServer DISABLED
        nscli -u :nsroot:nsroot bind vlan 4092 -ifnum 1/1
        nscli -u :nsroot:nsroot bind vlan 4092 -IPAddress {lb_outside_primary_address} {lb_outside_mask}
        nscli -u :nsroot:nsroot bind vlan 4091 -ifnum 1/2
        nscli -u :nsroot:nsroot bind vlan 4091 -IPAddress {lb_inside_primary_address} {lb_inside_mask}
        nscli -u :nsroot:nsroot add dns nameServer 8.8.8.8
        nscli -u :nsroot:nsroot add dns nameServer 8.8.4.4

        # Save the new running config
        nscli -u :nsroot:nsroot savec
          '''.format(**data)

    return textwrap.dedent(netscaler_config)

def generate_netscaler_failover_config(data):

    if data['priority'] == 'primary':
	data['peerid'] = '2'
        netscaler_failover_config = '''
            nscli -u :nsroot:nsroot add node {peerid} {lb_mgmt_secondary_address}
            nscli -u :nsroot:nsroot set rpcnode {lb_mgmt_primary_address} -password @penstack1234
            nscli -u :nsroot:nsroot set rpcnode {lb_mgmt_secondary_address} -password @penstack1234
              '''.format(**data)

    elif data['priority'] == 'secondary':
        data['peerid'] = '1'
        netscaler_failover_config = '''
            nscli -u :nsroot:nsroot add node {peerid} {lb_mgmt_primary_address}
            nscli -u :nsroot:nsroot set rpcnode {lb_mgmt_primary_address} -password @penstack1234
            nscli -u :nsroot:nsroot set rpcnode {lb_mgmt_secondary_address} -password @penstack1234
              '''.format(**data)


    return textwrap.dedent(netscaler_failover_config)
