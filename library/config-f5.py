import textwrap,json

def generate_f5_config(ha,data):
    # (todo) implement base key injection
    # (todo) implement ha configuration

    # Generate the base configuration
    config = {}
    config['bigip'] = {}
    config['bigip']['ssh_key_inject'] = 'false'
    config['bigip']['change_password'] = 'false'
    config['bigip']['admin_password'] = 'openstack'

    # Configure network settings
    config['bigip']['network'] = {}
    config['bigip']['network']['dhcp'] = 'false'
    config['bigip']['network']['interfaces'] = {}
    config['bigip']['network']['interfaces']['1.1'] = {}
    config['bigip']['network']['interfaces']['1.1']['dhcp'] = 'false'
    config['bigip']['network']['interfaces']['1.1']['vlan_name'] = 'EXTERNAL'
    config['bigip']['network']['interfaces']['1.1']['address'] = '1.2.1.1'
    config['bigip']['network']['interfaces']['1.1']['netmask'] = '255.255.255.0'
    config['bigip']['network']['routes'] = {}
    config['bigip']['network']['routes']['0.0.0.0/0'] = '1.2.1.254'


    json_config = json.dumps(config)
    print json_config

generate_f5_config('1','1')
