from library.database import *
import library.neutron as neutronlib
import textwrap, json, sys
import netaddr

def generate_configuration(db_filename,instance_blob,self_ports,peer_ports):
    # (todo) implement base key injection
    # (todo) implement ha configuration

    # Determine interface addresses
    # Interfaces determined in order (management, outside, inside, failover, etc.)
    # (todo) Support multiple interfaces. For now, it's pretty static

    interface = {}
    interface['external_addr'] = neutronlib.get_fixedip_from_port(self_ports[1]) # Outside/External interface
    interface['external_netmask'] = neutronlib.get_netmask_from_subnet(neutronlib.get_subnet_from_port(self_ports[1]))
    interface['internal_addr'] = neutronlib.get_fixedip_from_port(self_ports[2]) # Inside/Internal interface
    interface['internal_netmask'] = neutronlib.get_netmask_from_subnet(neutronlib.get_subnet_from_port(self_ports[1]))

    # Determine HA info
    if 'primary' or 'secondary' in instance_blob['device_priority']:
        interface['self_failover_addr'] = neutronlib.get_fixedip_from_port(self_ports[3])
        interface['self_failover_netmask'] = neutronlib.get_netmask_from_subnet(neutronlib.get_subnet_from_port(self_ports[3]))


    ###################################
    # Generate the base configuration #
    config = {}
    config['bigip'] = {}
    config['bigip']['hostname'] = instance_blob['environment_number'] + '-' + instance_blob['account_number'] + '-' + instance_blob['device_number']
    config['bigip']['domain'] = 'moonshine.rackspace.com'
    config['bigip']['ssh_key_inject'] = 'false'
    config['bigip']['change_passwords'] = 'true'
    config['bigip']['admin_password'] = 'openstack12345'
    config['bigip']['root_password'] = 'openstack12345'

    # Execute custom commands
    config['bigip']['system_cmds'] = []
    config['bigip']['system_cmds'].append('tmsh modify /sys global-settings hostname %s.%s' % (config['bigip']['hostname'],config['bigip']['domain']))
    config['bigip']['system_cmds'].append('touch /tmp/openstack-moonshine')
    config['bigip']['system_cmds'].append('uname -r >> /tmp/openstack-moonshine')
    config['bigip']['system_cmds'].append('tmsh modify /sys sshd banner enabled banner-text "System auto-configured by Moonshine. Unauthorized access is prohibited!"')
    # Additional commands must be appended like those above

    # Configure network settings
    config['bigip']['network'] = {}
    config['bigip']['network']['dhcp'] = 'false'
    config['bigip']['network']['interfaces'] = {}
    config['bigip']['network']['interfaces']['1.1'] = {}
    config['bigip']['network']['interfaces']['1.1']['dhcp'] = 'false'
    config['bigip']['network']['interfaces']['1.1']['vlan_name'] = 'EXTERNAL'
    config['bigip']['network']['interfaces']['1.1']['address'] = interface['external_addr']
    config['bigip']['network']['interfaces']['1.1']['netmask'] = interface['external_netmask']
    config['bigip']['network']['interfaces']['1.2'] = {}
    config['bigip']['network']['interfaces']['1.2']['dhcp'] = 'false'
    config['bigip']['network']['interfaces']['1.2']['vlan_name'] = 'INTERNAL'
    config['bigip']['network']['interfaces']['1.2']['address'] = interface['internal_addr']
    config['bigip']['network']['interfaces']['1.2']['netmask'] = interface['external_netmask']

    # Add routes
    config['bigip']['network']['routes'] = []
    config['bigip']['network']['routes'].append({'destination':'0.0.0.0/0','gateway':neutronlib.get_gateway_from_port(self_ports[1])})
    # Additional routes must be appended like those above!

    if 'primary' or 'secondary' in instance_blob['device_priority']:
	config['bigip']['network']['interfaces']['1.3'] = {}
	config['bigip']['network']['interfaces']['1.3']['dhcp'] = 'false'
	config['bigip']['network']['interfaces']['1.3']['vlan_name'] = 'FAILOVER'
	config['bigip']['network']['interfaces']['1.3']['address'] = interface['self_failover_addr']
	config['bigip']['network']['interfaces']['1.3']['netmask'] = interface['self_failover_netmask']
        config['bigip']['network']['interfaces']['1.3']['is_failover'] = 'true'
        config['bigip']['network']['interfaces']['1.3']['is_sync'] = 'true'
        config['bigip']['network']['interfaces']['1.3']['is_mirror_primary'] = 'true'

    json_config = json.dumps(config)
    return json_config
