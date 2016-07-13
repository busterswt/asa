# ports.py


def create_fw_ports():
    global _ports

    print "Creating virtual ports in Neutron for firewall(s)..."

    try:
        # Create ports
        _ports['fw_mgmt_primary_port_id'] = neutronlib.create_port(network_id=_networks['oob_network'],
								hostname=_metadata['hostname']+"-FW-PRI-MGMT",
								port_security_enabled='False',
								description='{"type":"management"}',
								tenant_id=os_project.id)
        _ports['fw_outside_primary_port_id'] = neutronlib.create_port(network_id=_networks['netdev_network'],
								hostname=_metadata['hostname']+"-FW-PRI-OUTSIDE",
								port_security_enabled='False',
								description='{"type":"outside"}',
								tenant_id=os_project.id)
        _ports['fw_inside_primary_port_id'] = neutronlib.create_port(network_id=_networks['fw_inside_network_id'],
								hostname=_metadata['hostname']+"-FW-PRI-INSIDE",
								subnet_id=_networks['fw_inside_subnet_id'],
								ip_address=_networks['fw_inside_gateway'],
								port_security_enabled='False',
								tenant_id=os_project.id)

        # If HA, create a failover port and secondary unit ports
        if _networks['fw_failover_network_name'] is not None:
	    _ports['fw_failover_primary_port_id'] = neutronlib.create_port(network_id=_networks['fw_failover_network_id'],
									hostname=_metadata['hostname']+"-FW-PRI-FAILOVER",
									port_security_enabled='False',
									description='{"type":"failover"}',
									tenant_id=os_project.id)
	    _ports['fw_failover_secondary_port_id'] = neutronlib.create_port(network_id=_networks['fw_failover_network_id'],
									hostname=_metadata['hostname']+"-FW-SEC-FAILOVER",
									port_security_enabled='False',
									description='{"type":"failover"}',
									tenant_id=os_project.id)
	    _ports['fw_mgmt_secondary_port_id'] = neutronlib.create_port(network_id=_networks['oob_network'],
									hostname=_metadata['hostname']+"-FW-SEC-MGMT",
									port_security_enabled='False',
									description='{"type":"management"}',
									tenant_id=os_project.id)
	    _ports['fw_outside_secondary_port_id'] = neutronlib.create_port(network_id=_networks['netdev_network'],
									hostname=_metadata['hostname']+"-FW-SEC-OUTSIDE",
									port_security_enabled='False',
									description='{"type":"outside"}',
									tenant_id=os_project.id)
	    _ports['fw_inside_secondary_port_id'] = neutronlib.create_port(_networks['fw_inside_network_id'],
									hostname=_metadata['hostname']+"-FW-SEC-INSIDE",
									port_security_enabled='False',
									tenant_id=os_project.id)
    except Exception, e:
	logging.exception("Error creating virtual ports. Rolling back port creation! %s" % e)
	# (todo) implement rollback then exit

    return _ports # Return the ports. They will be used to generate the configuration.

def create_lb_ports():
    global _ports

    print "Creating virtual ports in Neutron for load balancer(s)..."

    try:
        # Create ports
        _ports['lb_mgmt_primary_port_id'] = neutronlib.create_port(network_id=_networks['oob_network'],
								hostname=_metadata['hostname']+"-LB-PRI-MGMT",
								port_security_enabled='False',
								description='{"type":"management"}',
								tenant_id=os_project.id)
        _ports['lb_outside_primary_port_id'] = neutronlib.create_port(network_id=_networks['fw_inside_network_id'],
								hostname=_metadata['hostname']+"-LB-PRI-EXTERNAL",
								port_security_enabled='False',
								description='{"type":"outside"}',
                                                                tenant_id=os_project.id)
        _ports['lb_inside_primary_port_id'] = neutronlib.create_port(network_id=_networks['lb_inside_network_id'],
								hostname=_metadata['hostname']+"-LB-PRI-INTERNAL",
								port_security_enabled='False',
								tenant_id=os_project.id)

        # If HA, create a failover port and secondary unit ports
        if _networks['lb_failover_network_name'] is not None:
            _ports['lb_failover_primary_port_id'] = neutronlib.create_port(network_id=_networks['lb_failover_network_id'],
								hostname=_metadata['hostname']+"-LB-PRI-FAILOVER",
								port_security_enabled='False',
								description='{"type":"failover"}',
								tenant_id=os_project.id)
            _ports['lb_failover_secondary_port_id'] = neutronlib.create_port(network_id=_networks['lb_failover_network_id'],
								hostname=_metadata['hostname']+"-LB-SEC-FAILOVER",
								port_security_enabled='False',
								description='{"type":"failover"}',
								tenant_id=os_project.id)
            _ports['lb_mgmt_secondary_port_id'] = neutronlib.create_port(network_id=_networks['oob_network'],
								hostname=_metadata['hostname']+"-LB-SEC-MGMT",
								port_security_enabled='False',
								description='{"type":"management"}',
								tenant_id=os_project.id)
            _ports['lb_outside_secondary_port_id'] = neutronlib.create_port(network_id=_networks['fw_inside_network_id'],
								hostname=_metadata['hostname']+"-LB-SEC-EXTERNAL",
								port_security_enabled='False',
								description='{"type":"outside"}',
								tenant_id=os_project.id)
            _ports['lb_inside_secondary_port_id'] = neutronlib.create_port(network_id=_networks['lb_inside_network_id'],
								hostname=_metadata['hostname']+"-LB-SEC-INTERNAL",
								port_security_enabled='False',
								tenant_id=os_project.id)
    except Exception, e:
        logging.exception("Error creating virtual ports. Rolling back port creation! %s" % e)
        # (todo) implement rollback then exit
	sys.exit(1)

    return _ports # Return the ports. They will be used to generate the configuration.
