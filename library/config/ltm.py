import textwrap, json

def generate_f5_config(ha,_lb_configuration):
    # (todo) implement base key injection
    # (todo) implement ha configuration

    # Determine the addresses and config to use based on device (primary/secondary)
    if _lb_configuration['priority'] is 'primary':
	external_address = _lb_configuration['lb_outside_primary_address']
	internal_address = _lb_configuration['lb_inside_primary_address']

	if ha:
	    failover_address = _lb_configuration['lb_failover_primary_address']

    elif _lb_configuration['priority'] is 'secondary':
	external_address = _lb_configuration['lb_outside_secondary_address']
        internal_address = _lb_configuration['lb_inside_secondary_address']
	failover_address = _lb_configuration['lb_failover_secondary_address']

    ###################################
    # Generate the base configuration #
    config = {}
    config['bigip'] = {}
    config['bigip']['ssh_key_inject'] = 'false'
    config['bigip']['change_passwords'] = 'true'
    config['bigip']['admin_password'] = 'openstack12345'
    config['bigip']['root_password'] = 'openstack12345'

    # Execute custom commands
    config['bigip']['system_cmds'] = []
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
    config['bigip']['network']['interfaces']['1.1']['address'] = external_address
    config['bigip']['network']['interfaces']['1.1']['netmask'] = _lb_configuration['lb_outside_mask']
    config['bigip']['network']['interfaces']['1.2'] = {}
    config['bigip']['network']['interfaces']['1.2']['dhcp'] = 'false'
    config['bigip']['network']['interfaces']['1.2']['vlan_name'] = 'INTERNAL'
    config['bigip']['network']['interfaces']['1.2']['address'] = internal_address
    config['bigip']['network']['interfaces']['1.2']['netmask'] = _lb_configuration['lb_inside_mask']

    # Add routes
    config['bigip']['network']['routes'] = []
    config['bigip']['network']['routes'].append({'destination':'0.0.0.0/0','gateway':_lb_configuration['lb_outside_gateway']})
    # Additional routes must be appended like those above!

    if ha:
	config['bigip']['network']['interfaces']['1.3'] = {}
	config['bigip']['network']['interfaces']['1.3']['dhcp'] = 'false'
	config['bigip']['network']['interfaces']['1.3']['vlan_name'] = 'FAILOVER'
	config['bigip']['network']['interfaces']['1.3']['address'] = failover_address
	config['bigip']['network']['interfaces']['1.3']['netmask'] = _lb_configuration['lb_failover_netmask']
        config['bigip']['network']['interfaces']['1.3']['is_failover'] = 'true'
        config['bigip']['network']['interfaces']['1.3']['is_sync'] = 'true'

    json_config = json.dumps(config)
    return json_config
