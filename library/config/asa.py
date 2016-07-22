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

    # Determine device IPs based on port.
    # Build management interface dict first
    if 'standalone' in data['priority']:
	subnet_id = neutronlib.get_subnet_from_port(self_ports[0])
	data['standby_keyword'] = ''
        data['pri_mgmt_addr'] = neutronlib.get_fixedip_from_port(self_ports[0])
        data['pri_mgmt_netmask'] = neutronlib.get_netmask_from_subnet(subnet_id)
	data['sec_mgmt_address'] = ''
        data['mgmt_gateway'] = neutronlib.get_gateway_from_port(self_ports[0])
    elif 'primary' in data['priority']:
	subnet_id = neutronlib.get_subnet_from_port(self_ports[0])
	data['standby_keyword'] = 'standby'
	data['pri_mgmt_addr'] = neutronlib.get_fixedip_from_port(self_ports[0])
	data['pri_mgmt_netmask'] = neutronlib.get_netmask_from_subnet(subnet_id)
	data['sec_mgmt_address'] = neutronlib.get_fixedip_from_port(peer_ports[0])
	data['mgmt_gateway'] = neutronlib.get_gateway_from_port(self_ports[0])
    elif 'secondary' in data['priority']:
	subnet_id = neutronlib.get_subnet_from_port(self_ports[0])
        data['standby_keyword'] = 'standby'
        data['pri_mgmt_addr'] = neutronlib.get_fixedip_from_port(peer_ports[0])
        data['pri_mgmt_netmask'] = neutronlib.get_netmask_from_subnet(subnet_id)
        data['sec_mgmt_address'] = neutronlib.get_fixedip_from_port(self_ports[0])
        data['mgmt_gateway'] = neutronlib.get_gateway_from_port(self_ports[0])

    # Generate the base configuration
    configuration = generate_base_config(data)

    # Generate the interface configuration
    configuration += generate_management_interface_config(data)

    # Now, let's build all of the other interfaces
    configuration += generate_interface_config(db_filename,data,self_ports,peer_ports)

    # Generate object groups
    configuration += generate_inside_object_groups(db_filename,self_ports)

    # Generate more configuration
#    config += generate_access_config(data)
    configuration += generate_logging_config()
    configuration += generate_ntp_config()
    configuration += generate_security_config()
#    config += generate_vpn_config(data)

    return configuration

def generate_management_interface_config(data):
    management_interface = """
        ! Begin interface configuration.
        ! Interface m0/0 is management (first attached interface)
        interface management0/0
        nameif management
        management-only
        security-level 90
        ip address {pri_mgmt_addr} {pri_mgmt_netmask} {standby_keyword} {sec_mgmt_address}
        no shut
        route management 0.0.0.0 0.0.0.0 {mgmt_gateway}
        """.format(**data)

    return textwrap.dedent(management_interface)

def generate_inside_object_groups(db_filename,self_ports):
    # Generates object groups for inside networks
    # (todo) Fix this so it only looks at inside networks
    dbmgr = DatabaseManager(db_filename)
    obj_groups = ""    
    data = {}

    for port_id in self_ports:
        result = dbmgr.query("select port_name from ports where port_id=?",
                                ([port_id]))

	data['port_name'] = result.fetchone()[0]	

	if "outside" or "management" or "failover" not in data['port_name']:
	    subnet_id = neutronlib.get_subnet_from_port(port_id)
	    data['network_addr'],data['network_netmask'] = neutronlib.get_network_netmask_from_subnet(subnet_id)

            obj_groups += """
                object network obj-{port_name}-network
                subnet {network_addr} {network_netmask}
            """.format(**data)

    return obj_groups

def generate_interface_config(db_filename,data,self_ports,peer_ports):
    # (todo) move the ACL config to its own function
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

        if 'standalone' in data['priority']:
	    interface['standby_keyword'] = ''
	    interface['pri_addr'] = neutronlib.get_fixedip_from_port(self_ports[index])
            interface['netmask'] = neutronlib.get_netmask_from_subnet(subnet_id)
            interface['sec_addr'] = ''
        elif 'primary' in data['priority']:
            interface['standby_keyword'] = 'standby'
            interface['pri_addr'] = neutronlib.get_fixedip_from_port(self_ports[index])
            interface['netmask'] = neutronlib.get_netmask_from_subnet(subnet_id)
            interface['sec_addr'] = neutronlib.get_fixedip_from_port(peer_ports[index])
	elif 'secondary' in data['priority']:
            interface['standby_keyword'] = 'standby'
            interface['pri_addr'] = neutronlib.get_fixedip_from_port(peer_ports[index])
            interface['netmask'] = neutronlib.get_netmask_from_subnet(subnet_id)
            interface['sec_addr'] = neutronlib.get_fixedip_from_port(self_ports[index])

	# Only generate full interface for non-failover port
	if not 'failover' in interface['port_name']:
            interface_config += """
                ! Interfaces built in order as passed to script. 
                ! First is management, then outside, then inside, etc.
                ! Failover interface must be named 'failover'
                interface GigabitEthernet0/{0}
                no shut
                nameif {port_name}
                security-level {0}
                ip address {pri_addr} {netmask} {standby_keyword} {sec_addr}
                ! Disable proxy ARP ticket 140923-08822
                sysopt noproxyarp {port_name}
                ip verify reverse-path interface {port_name}

                access-list {port_name}_in permit ip any any
                access-group {port_name}_in in interface {port_name}
            """.format(index,**interface)

	if 'failover' in interface['port_name']:
	    interface['failover_interface'] = 'GigabitEthernet0/%d' % index

	    interface_config += """
                interface GigabitEthernet0/{0}
                no shut
            """.format(index)

	    # Generate and return the failover configuration
            interface_config += generate_failover_configuration(data['priority'],interface)

	index += 1 # Iterate the index and loop back through

    return textwrap.dedent(interface_config)

def generate_asa_nat_config(data):
    # (todo) get the port list, pop off first, use second to build the NATs (second is outside)
    nat_config = """
        ! Begin NAT configuration
        ! At this time, only dynamic NAT is supported
        nat (inside,outside) after-auto source dynamic any interface
    """.format(**data)

def generate_base_config(data):
    # Generates the base config of a Cisco ASA

    configuration = """
        ! Begin template
        hostname {hostname}
        domain-name IAD3.RACKSPACE.COM
        no http server enable
        prompt hostname pri state
        crypto key generate rsa general-keys modulus 2048 noconfirm

        ! Inspections
        no threat-detection basic-threat
        no threat-detection statistics access-list
        no call-home reporting anonymous

        class-map inspection_default
        match default-inspection-traffic

        policy-map type inspect dns preset_dns_map
        parameters
        message-length maximum 512
        message-length maximum client auto
        message-length maximum server auto

        policy-map global_policy
        class inspection_default
        inspect icmp
        inspect dns preset_dns_map
        inspect ftp
        inspect h323 h225
        inspect h323 ras
        inspect rsh
        inspect skinny
        inspect xdmcp
        inspect sip
        inspect netbios
        inspect tftp
        inspect esmtp
        no inspect esmtp
        inspect rtsp
        no inspect rtsp
        inspect sqlnet
        no inspect sqlnet
        inspect sunrpc
        no inspect sunrpc

        service-policy global_policy global

        ! User configuration
        username moonshine password openstack12345 privilege 15
          """.format(**data)

    return textwrap.dedent(configuration)

def generate_access_config(data):
    # (todo) generate this using correct port info
    access_config = """
	! ACL Configuration
        object-group icmp-type ICMP-ALLOWED
        description "These are the ICMP types Rackspace allows by default"
        icmp-object echo-reply
        icmp-object unreachable
        icmp-object echo
        icmp-object time-exceeded
        icmp-object traceroute
        ! Generating ENT Z specific rackspace object-group
        object-group network RACKSPACE-IPS
        network-object 64.39.0.0 255.255.254.0
        network-object 64.39.2.144 255.255.255.240
        network-object 10.0.0.0 255.240.0.0
        network-object 10.16.0.0 255.255.0.0
        network-object 69.20.0.0 255.255.255.128
        network-object 69.20.0.160 255.255.255.224
        network-object 69.20.0.192 255.255.255.192
        network-object 69.20.1.0 255.255.255.0
        network-object 212.100.225.32 255.255.255.224
        network-object 66.216.93.64 255.255.255.240
        network-object host 212.100.224.20
        network-object 72.3.128.0 255.255.254.0
        network-object host 83.138.151.69
        network-object host 83.138.138.174
        network-object 69.20.0.64 255.255.255.224
        network-object 212.100.255.192 255.255.255.240
        network-object 72.3.130.0 255.255.255.192
        network-object 66.216.65.192 255.255.255.224
        network-object host 92.52.76.140
        network-object 72.3.223.8 255.255.255.248
        network-object 120.136.32.96 255.255.255.240
        network-object host 92.52.78.14
        network-object host 173.203.4.161
        network-object host 173.203.4.162
        network-object host 173.203.4.180
        network-object 173.203.32.188 255.255.255.254
        network-object 50.57.61.0 255.255.255.192
        network-object 67.192.2.192 255.255.255.192
        network-object 74.205.28.0 255.255.255.192
        network-object 78.136.44.0 255.255.255.192
        network-object 180.150.149.64 255.255.255.192
        network-object 50.57.32.48 255.255.255.240
        network-object host 83.138.139.8
        network-object host 94.236.7.185
        network-object host 212.100.225.52
        network-object 50.56.228.0 255.255.255.224
        network-object 50.56.230.0 255.255.255.224
        network-object host 72.3.128.213
        network-object host 72.3.128.220
        network-object host 173.203.4.129
        network-object host 173.203.4.130
        network-object host 69.20.0.4
        network-object host 69.20.0.12
        network-object host 212.100.224.13
        network-object host 212.100.225.16
        network-object host 120.136.34.36
        network-object host 120.136.34.44
        object-group network RACKSPACE-BASTIONS
        network-object host 72.3.128.84
        network-object host 69.20.0.1
        network-object host 212.100.225.42
        network-object host 212.100.225.49
        network-object host 120.136.34.22
        network-object host 119.9.63.53
        network-object host 50.57.22.125
        network-object host 119.9.4.2
        object-group network RACKSPACE-NETOPS
        network-object 66.216.70.224 255.255.255.240
        network-object 69.20.123.0 255.255.255.240
        network-object 72.3.218.80 255.255.255.240
        network-object 72.4.112.112 255.255.255.240
        network-object 72.32.94.80 255.255.255.248
        network-object 92.52.121.80 255.255.255.240
        network-object 120.136.35.16 255.255.255.240
        network-object 184.106.8.160 255.255.255.240
        object-group network RACKSPACE-MONITORING
        network-object 66.216.125.0 255.255.255.224
        network-object 66.216.111.0 255.255.255.0
        network-object 72.32.192.0 255.255.255.0
        network-object 74.205.2.0 255.255.255.0
        network-object 92.52.126.0 255.255.254.0
        network-object 120.136.33.0 255.255.255.128
        network-object 120.136.34.16 255.255.255.240
        network-object 98.129.223.0 255.255.255.0
        network-object 72.4.123.0 255.255.255.128
        network-object 72.4.123.128 255.255.255.192
        network-object 72.4.123.192 255.255.255.240
        network-object 72.4.123.216 255.255.255.248
        network-object 72.4.123.224 255.255.255.224
        network-object 173.203.5.0 255.255.255.0
        !IAD3 RW Pollers
        network-object 72.4.120.203 255.255.255.255
        network-object 72.4.120.204 255.255.255.255
        ! 121019-08978 MaaS Production DFW
        network-object 50.56.142.128 255.255.255.192
        ! 121019-08978 MaaS Production HKG
        network-object 180.150.149.64 255.255.255.192
        ! 121019-08978 MaaS Production IAD
        network-object 69.20.52.192 255.255.255.192
        ! 121019-08978 MaaS Production LON
        network-object 78.136.44.0 255.255.255.192
        ! 121019-08978 MaaS Production ORD
        network-object 50.57.61.0 255.255.255.192
        ! 121019-08978 MaaS Production SYD
        network-object 119.9.5.0 255.255.255.192
        ! 121019-08978 MaaS Staging DFW
        network-object 74.205.48.192 255.255.255.240
        ! 121019-08978 MaaS Staging HKG & IAD
        network-object 10.24.196.0 255.255.254.0
        ! 121019-08978 MaaS Staging LON
        network-object 94.236.68.64 255.255.255.248
        ! 121019-08978 MaaS Staging ORD
        network-object 50.57.208.104 255.255.255.248
        ! 121220-07123 SYD2 SCOM/Nimbus/WSUS
        network-object 119.9.4.64 255.255.255.192
        ! 121220-07123 SYD2 Rackwatch
        network-object 119.9.4.48 255.255.255.240
        ! 121025-07550 ORD1 Numbus Monitoring and RackConnect
        network-object 50.57.57.0 255.255.255.128
        ! 130109-08366 SYD2 Nimbus
        network-object host 10.16.25.34
        ! Nimbus London Infrastructure
        network-object 92.52.127.48 255.255.255.240
        ! RackConnect Automation Infrastructure
        network-object 162.209.16.56 255.255.255.248
        network-object 72.32.176.248 255.255.255.248
        object-group network RACKSPACE-RBA
        ! 130107-09019 DFW1 RBA Infrastructure
        network-object 67.192.155.96 255.255.255.224
        ! 130107-09019 -UNKNOWN- RBA Infrastructure
        network-object 64.49.200.192 255.255.255.224
        ! 130107-09019 LON3 RBA Infrastructure
        network-object 89.234.21.64 255.255.255.240
        ! 130107-09019 IAD1/2 RBA Infrastructure
        network-object 69.20.80.0 255.255.255.240
        ! 130107-09019 HKG1 RBA Infrastructure
        network-object 120.136.32.192 255.255.255.224
        ! 130107-09019 ORD1 RBA Infrastructure
        network-object 173.203.32.136 255.255.255.248
        ! 130107-09019 ORD1 RBA Infrastructure
        network-object 173.203.5.160 255.255.255.224
        ! 130107-09019 -UNKNOWN- RBA Infrastructure
        network-object 72.3.128.84 255.255.255.252
        ! 130107-09019 -UNKNOWN- RBA Infrastructure
        network-object 69.20.0.0 255.255.255.248
        ! 130107-09019 -UNKNOWN- RBA Infrastructure
        network-object 120.136.34.16 255.255.255.240
        ! 130107-09019 -UNKNOWN- RBA Infrastructure
        network-object host 72.4.123.216
        ! 130107-09019 -UNKNOWN- RBA Infrastructure
        network-object host 212.100.225.42
        ! 130107-09019 -UNKNOWN- RBA Infrastructure
        network-object host 212.100.225.49
        ! 130107-09019 SYD2 RBA Infrastructure
        network-object 119.9.4.56 255.255.255.248
        ! New Hybrid vCenter Infrastructure - ORD
        network-object 108.166.25.250 255.255.255.254
        ! New Hybrid vCenter Infrastructure - DFW
        network-object 67.192.38.80 255.255.255.254
        ! New Hybrid vCenter Infrastructure - LON
        network-object 162.13.22.242 255.255.255.254
        ! New Hybrid vCenter Infrastructure - HKG
        network-object 120.136.35.184 255.255.255.254
        ! New Hybrid vCenter Infrastructure - SYD
        network-object 119.9.60.168 255.255.255.254
        ! New Hybrid vCenter Infrastructure - IAD
        network-object 207.97.212.228 255.255.255.254
        object-group network RACKSPACE-SITESCOPE
        network-object 174.143.23.0 255.255.255.0
        network-object 94.236.100.0 255.255.255.128
        object-group network RACKSPACE-PATCHING
        ! Winpatch IPs
        network-object host 72.32.191.242
        network-object host 72.32.191.245
        network-object host 72.32.191.246
        network-object host 72.32.191.248
        network-object 108.171.164.192 255.255.255.252
        network-object host 69.20.123.153
        network-object 204.232.161.104 255.255.255.254
        network-object host 204.232.161.106
        network-object 83.138.165.112 255.255.255.254
        network-object host 83.138.165.115
        network-object host 83.138.165.118
        network-object 180.150.136.224 255.255.255.254
        network-object host 180.150.136.229
        network-object host 120.136.41.15
        network-object 119.9.146.24 255.255.255.252
        object-group network RACKSPACE-NEST
        description "Rackspace admin IP object-groups are nested here"
        group-object RACKSPACE-MONITORING
        group-object RACKSPACE-BASTIONS
        group-object RACKSPACE-RBA
        group-object RACKSPACE-NETOPS
        group-object RACKSPACE-IPS
        group-object RACKSPACE-SITESCOPE
        group-object RACKSPACE-PATCHING

        ! Intensive and Enterprise IP blocks
        object-group network INTENSIVE-INFRASTRUCTURE
        network-object 72.32.192.0 255.255.255.0
        network-object 74.205.2.0 255.255.255.0
        network-object host 66.216.65.214
        network-object host 64.39.19.196
        network-object 66.216.111.168 255.255.255.254
        network-object 173.203.32.136 255.255.255.248
        network-object 69.20.84.16 255.255.255.240
        network-object 72.3.156.176 255.255.255.240
        network-object 98.129.181.192 255.255.255.224
        network-object 83.138.145.192 255.255.255.192
        network-object 92.52.127.48 255.255.255.240
        network-object 72.4.123.192 255.255.255.240
        network-object 120.136.33.64 255.255.255.240
        network-object 173.203.5.128 255.255.255.224
        object-group network RACKSPACE-NEST
        group-object INTENSIVE-INFRASTRUCTURE

        access-list 101 line 1 extended permit ip object-group RACKSPACE-NEST any
        access-list 101 line 2 extended permit icmp any any object-group ICMP-ALLOWED

        access-list 100 permit ip any any

          """.format(**data)

    return textwrap.dedent(access_config)

def generate_logging_config():
    logging_config = """
        ! Logging
        logging enable
        logging timestamp
        logging list RS-BUFFER-LOG level errors
        logging list RS-BUFFER-LOG message 111008
        logging list RS-BUFFER-LOG level informational class vpn
        logging list RS-BUFFER-LOG level informational class vpnc
        logging buffer-size 1048576
        logging buffered RS-BUFFER-LOG
        ! Workaround for  CSCur41860 AKH 12/22/14
        no logging message 769004
        ! Prevent TCP syslog from taking down box
        logging permit-hostdown
        """

    return textwrap.dedent(logging_config)

def generate_ntp_config():
    ntp_config = """
        ! Clock Settings
        clock timezone CST -6
        clock summer-time CDT recurring
        ntp server 173.203.4.8 source OUTSIDE prefer
        ntp server 72.3.128.240 source OUTSIDE
        ntp server 83.138.151.80 source OUTSIDE
        ntp server 69.20.0.164 source OUTSIDE
        ntp server 120.136.32.62 source OUTSIDE
        ntp server 119.9.60.62 source OUTSIDE
        ntp server 69.20.0.164 source OUTSIDE prefer
        """
    return textwrap.dedent(ntp_config)

def generate_security_config():
    security_config = """
        ! Timeout values
        console timeout 5
        ssh timeout 15
        ssh scopy enable

        ! SSH lines
        ssh 10.0.0.0 255.240.0.0 OUTSIDE
        ssh 64.39.0.0 255.255.254.0 OUTSIDE
        ssh 72.3.128.0 255.255.254.0 OUTSIDE
        ssh 92.52.78.14 255.255.255.255 OUTSIDE
        ssh 212.100.225.32 255.255.255.224 OUTSIDE
        ssh 72.3.218.80 255.255.255.240 OUTSIDE
        ssh 69.20.123.0 255.255.255.240 OUTSIDE
        ssh 184.106.8.160 255.255.255.240 OUTSIDE
        ssh 69.20.0.0 255.255.254.0 OUTSIDE
        ssh 72.3.223.8 255.255.255.248 OUTSIDE
        ssh 72.32.94.80 255.255.255.248 OUTSIDE
        ssh 66.216.70.224 255.255.255.240 OUTSIDE
        ssh 72.4.112.112 255.255.255.240 OUTSIDE
        ssh 92.52.121.80 255.255.255.240 OUTSIDE
        ssh 120.136.35.16 255.255.255.240 OUTSIDE
        ssh 108.166.25.250 255.255.255.254 OUTSIDE
        ssh 67.192.38.80 255.255.255.254 OUTSIDE
        ssh 162.13.22.242 255.255.255.254 OUTSIDE
        ssh 120.136.35.184 255.255.255.254 OUTSIDE
        ssh 119.9.60.168 255.255.255.254 OUTSIDE
        ssh 207.97.212.228 255.255.255.254 OUTSIDE
        ssh 67.192.155.96 255.255.255.224 OUTSIDE
        ssh 120.136.32.192 255.255.255.224 OUTSIDE
        ssh 69.20.80.0 255.255.255.240 OUTSIDE
        ssh 89.234.21.64 255.255.255.240 OUTSIDE
        ssh 173.203.32.136 255.255.255.248 OUTSIDE
        ssh 173.203.5.160 255.255.255.224 OUTSIDE
        ssh 64.49.200.192 255.255.255.224 OUTSIDE
        ssh 72.3.128.84 255.255.255.252 OUTSIDE
        ssh 50.57.22.125 255.255.255.255 OUTSIDE
        ssh 69.20.0.0 255.255.255.248 OUTSIDE
        ssh 120.136.34.16 255.255.255.240 OUTSIDE
        ssh 50.57.32.48 255.255.255.240 OUTSIDE
        ssh 83.138.139.8 255.255.255.255 OUTSIDE
        ssh 83.138.138.174 255.255.255.255 OUTSIDE
        ssh 94.236.7.185 255.255.255.255 OUTSIDE
        ssh 212.100.225.52 255.255.255.255 OUTSIDE
        ssh 50.56.228.0 255.255.255.224 OUTSIDE
        ssh 50.56.230.0 255.255.255.224 OUTSIDE
        ! RBA NTaaS
        ssh 72.4.123.216 255.255.255.248 OUTSIDE
        ! Support Bastion Farms
        ssh 72.3.128.84 255.255.255.255 OUTSIDE
        ssh 69.20.0.1 255.255.255.255 OUTSIDE
        ssh 212.100.225.42 255.255.255.255 OUTSIDE
        ssh 212.100.225.49 255.255.255.255 OUTSIDE
        ssh 120.136.34.22 255.255.255.255 OUTSIDE
        ssh 119.9.4.2 255.255.255.255 OUTSIDE
        ! Network Security Bastion Servers
        ssh 72.3.128.213 255.255.255.255 OUTSIDE
        ssh 72.3.128.220 255.255.255.255 OUTSIDE
        ssh 173.203.4.129 255.255.255.255 OUTSIDE
        ssh 173.203.4.130 255.255.255.255 OUTSIDE
        ssh 69.20.0.4 255.255.255.255 OUTSIDE
        ssh 69.20.0.12 255.255.255.255 OUTSIDE
        ssh 212.100.224.13 255.255.255.255 OUTSIDE
        ssh 212.100.225.16 255.255.255.255 OUTSIDE
        ssh 120.136.34.36 255.255.255.255 OUTSIDE
        ssh 120.136.34.44 255.255.255.255 OUTSIDE
        ! bastion[12].syd2.rackspace.com PAT address - 121220-07123
        ssh 119.9.63.53 255.255.255.255 OUTSIDE
        ! Home Lab (REMOVE)
        ssh 192.168.1.0 255.255.255.0 management
        ssh 192.168.1.0 255.255.255.0 OUTSIDE
        ! OOB From RAX
        ssh 10.0.0.0 255.240.0.0 management
        ssh timeout 15
          """

    return textwrap.dedent(security_config)

def generate_vpn_config(data):
    vpn_config = """
        ! VPN configuration
        crypto ipsec ikev1 transform-set AES256-SHA esp-aes-256 esp-sha-hmac
        crypto ipsec ikev1 transform-set AES256-MD5 esp-aes-256 esp-md5-hmac
        crypto ipsec ikev1 transform-set AES-SHA esp-aes esp-sha-hmac
        crypto ipsec ikev1 transform-set AES-MD5 esp-aes esp-md5-hmac
        crypto ipsec ikev1 transform-set 3DES-SHA esp-3des esp-sha-hmac
        crypto ipsec ikev1 transform-set 3DES-MD5 esp-3des esp-md5-hmac
        crypto ikev1 policy 100
        encryption aes-256
        hash sha
        group 5
        crypto ikev1 policy 110
        encryption aes-256
        hash sha
        group 2
        crypto ikev1 policy 120
        encryption aes-256
        hash md5
        group 5
        crypto ikev1 policy 130
        encryption aes-256
        hash md5
        group 2
        crypto ikev1 policy 200
        encryption aes
        hash sha
        group 5
        crypto ikev1 policy 210
        encryption aes
        hash sha
        group 2
        crypto ikev1 policy 220
        encryption aes
        hash md5
        group 5
        crypto ikev1 policy 230
        encryption aes
        hash md5
        group 2
        crypto ikev1 policy 300
        encryption 3des
        hash sha
        group 5
        crypto ikev1 policy 310
        encryption 3des
        hash sha
        group 2
        crypto ikev1 policy 320
        encryption 3des
        hash md5
        group 5
        crypto ikev1 policy 330
        encryption 3des
        hash md5
        group 2
        crypto dynamic-map DYNMAP 65535 set ikev1 transform-set AES256-SHA AES256-MD5 AES256-SHA AES-MD5 3DES-SHA 3DES-MD5
        crypto map VPNMAP 65535 ipsec-isakmp dynamic DYNMAP

        ! VPN Configuration
        ip local pool ippool 172.30.5.1-172.30.5.254 mask 255.255.255.0

        object-group network CLIENT_VPN_POOL
        network-object 172.30.5.0 255.255.255.0

        object-group network RFC_1918
        network-object 10.0.0.0 255.0.0.0
        network-object 192.168.0.0 255.255.0.0
        network-object 172.16.0.0 255.240.0.0

        access-list 103 extended permit ip object-group RFC_1918 object-group CLIENT_VPN_POOL

        group-policy {group_policy} internal
        group-policy {group_policy} attributes
        vpn-idle-timeout 30
        split-tunnel-policy tunnelspecified
        split-tunnel-network-list value 103
        default-domain value rackspace.com

        tunnel-group {tunnel_group} type remote-access
        tunnel-group {tunnel_group} general-attributes
        address-pool ippool
        default-group-policy {group_policy}
        tunnel-group {tunnel_group} ipsec-attributes
        ikev1 pre-shared-key {group_password}

        username {vpn_user} password {vpn_password}

        ! Enable VPN
        crypto isakmp nat-traversal 20
        crypto ikev1 enable OUTSIDE
        crypto map VPNMAP interface OUTSIDE

        ! AAA Configuration - Managed by RAX
        aaa-server RACKACS protocol tacacs+
        reactivation-mode depletion deadtime 5
        aaa-server RACKACS (OUTSIDE) host 10.4.109.17 Ri7@4Zx8 timeout 2
        aaa-server RACKACS (OUTSIDE) host 10.4.109.25 Ri7@4Zx8 timeout 2

        aaa authentication enable console LOCAL
        aaa authentication ssh console LOCAL
        aaa authentication http console LOCAL
        aaa authorization command LOCAL
          """.format(**data)

    return textwrap.dedent(vpn_config)

def generate_failover_configuration(priority,interface):
    failover_config = """
        failover
        failover lan unit {0}
        failover lan interface LANFAIL {failover_interface}
        failover polltime unit 1 holdtime 5
        failover key openstack
        failover replication http
        failover link LANFAIL {failover_interface}
        failover interface ip LANFAIL {pri_addr} {netmask} {standby_keyword} {sec_addr}
        """.format(priority,**interface)

    return textwrap.dedent(failover_config)
