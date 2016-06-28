import textwrap, json

def generate_asa_config(ha,data):
    # Generate the base configuration
    config = generate_base_config(data)

    # Generate the interface configuration
    if ha:
	config += generate_ha_interface_config(data)
    else:
	config += generate_standalone_interface_config(data)

    # Generate more configuration
    config += generate_access_config(data)
    config += generate_logging_config()
    config += generate_ntp_config()
    config += generate_security_config()
    config += generate_vpn_config(data)

    # Gerate failover configuration (if ha)
    if ha:
	config += generate_failover_config(data)

    return config

def generate_asa_nat_config(data):
    nat_config = '''
        ! Begin NAT configuration
        ! At this time, only dynamic NAT is supported
        nat (inside,outside) after-auto source dynamic any interface
    '''.format(**data)

def generate_standalone_interface_config(data):
    standalone_config = '''
        ! Begin interface configuration.
        ! Interface m0/0 is management (first attached interface)
        interface management0/0
        nameif management
        management-only
        security-level 10
        ip address {fw_mgmt_primary_address} {fw_mgmt_mask}
        no shut
        route management 0.0.0.0 0.0.0.0 {fw_mgmt_gateway}

        ! Interface g0/0 must be OUTSIDE (second attached interface)
        interface GigabitEthernet0/0
        no shut
        nameif OUTSIDE
        security-level 0
        ip address {fw_outside_primary_address} {fw_outside_mask}
        route outside 0.0.0.0 0.0.0.0 {fw_outside_gateway}
        ! Disable proxy ARP ticket 140923-08822
        sysopt noproxyarp OUTSIDE
        ip verify reverse-path interface OUTSIDE
        access-group 101 in interface OUTSIDE

        ! Interface g0/1 must be INSIDE (fourth attached interface)
        interface GigabitEthernet0/1
        no shut
        nameif INSIDE
        security-level 100
        ip address {fw_inside_primary_address} {fw_inside_netmask}
        ! Disable proxy ARP ticket 140923-08822
        sysopt noproxyarp INSIDE
        ip verify reverse-path interface INSIDE
        access-group 100 in interface INSIDE
          '''.format(**data)

    return textwrap.dedent(standalone_config)

def generate_ha_interface_config(data):
    ha_config = '''
        ! Begin interface configuration.
        ! Interface m0/0 is management (first attached interface)
        interface management0/0
        nameif management
        management-only
        security-level 10
        ip address {fw_mgmt_primary_address} {fw_mgmt_mask} standby {fw_mgmt_secondary_address}
        no shut
        route management 0.0.0.0 0.0.0.0 {fw_mgmt_gateway}

        ! Interface g0/0 must be OUTSIDE (second attached interface)
        interface GigabitEthernet0/0
        no shut
        nameif OUTSIDE
        security-level 0
        ip address {fw_outside_primary_address} {fw_outside_mask} standby {fw_outside_secondary_address}
        route outside 0.0.0.0 0.0.0.0 {fw_outside_gateway}
        ! Disable proxy ARP ticket 140923-08822
        sysopt noproxyarp OUTSIDE
        ip verify reverse-path interface OUTSIDE
        access-group 101 in interface OUTSIDE

        ! Interface g0/1 must be INSIDE (third attached interface)
        interface GigabitEthernet0/1
        no shut
        nameif INSIDE
        security-level 100
        ip address {fw_inside_primary_address} {fw_inside_netmask} standby {fw_inside_secondary_address}
        ! Disable proxy ARP ticket 140923-08822
        sysopt noproxyarp INSIDE
        ip verify reverse-path interface INSIDE
        access-group 100 in interface INSIDE

        ! Interface g0/2 must be failover (third attached interface)
        interface GigabitEthernet0/2
        no shut
          '''.format(**data)

    return textwrap.dedent(ha_config)

def generate_base_config(data):
    base_config = '''
        ! Begin template
        hostname {fw_hostname}
        domain-name IAD3.RACKSPACE.COM
        no http server enable
        prompt hostname pri state
        crypto key generate rsa general-keys modulus 1024 noconfirm

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
          '''.format(**data)

    return textwrap.dedent(base_config)

def generate_access_config(data):
    access_config = '''

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
        
        object network obj-INSIDE-NETWORK
        subnet {fw_inside_net_addr} {fw_inside_netmask}
          '''.format(**data)

    return textwrap.dedent(access_config)

def generate_logging_config():
    logging_config = '''
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
          '''

    return textwrap.dedent(logging_config)

def generate_ntp_config():
    ntp_config = '''
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
          '''

    return textwrap.dedent(ntp_config)

def generate_security_config():
    security_config = '''
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
          '''

    return textwrap.dedent(security_config)

def generate_vpn_config(data):        
    vpn_config = '''
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
          '''.format(**data)

    return textwrap.dedent(vpn_config)

def generate_failover_config(data):
    failover_config = '''
        failover
        failover lan unit {priority}
        failover lan interface LANFAIL GigabitEthernet0/2
        failover polltime unit 1 holdtime 5
        failover key openstack
        failover replication http
        failover link LANFAIL GigabitEthernet0/2
        failover interface ip LANFAIL {fw_failover_primary_address} {fw_failover_netmask} standby {fw_failover_secondary_address}
        '''.format(**data)

    return textwrap.dedent(failover_config)

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
    print json_config
    return json_config


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

def generate_srx_config(ha,data):
    config = '''
version 15.1X49-D50.3;
system {{
    host-name srx;
    root-authentication {{
        encrypted-password "$5$ytpefe9E$XTJpyXsaA9wT0IXXyg4N/xLsnRG2mbMg2MO2WGQCpW0"; ## SECRET-DATA
    }}
    services {{
        ssh;
        web-management {{
            http {{
                interface fxp0.0;
            }}
        }}
    }}
    syslog {{
        user * {{
            any emergency;
        }}
        file messages {{
            any any;
            authorization info;
        }}
        file interactive-commands {{
            interactive-commands any;
        }}
    }}
    license {{
        autoupdate {{
            url https://james.test.net/junos/key_retrieval;
        }}
    }}
}}
security {{
    screen {{
        ids-option untrust-screen {{
            icmp {{
                ping-death;
            }}
            ip {{
                source-route-option;
                tear-drop;
            }}
            tcp {{
                syn-flood {{
                    alarm-threshold 1024;
                    attack-threshold 200;
                    source-threshold 1024;
                    destination-threshold 2048;
                    queue-size 2000; ## Warning: 'queue-size' is deprecated
                    timeout 20;
                }}
                land;
            }}
        }}
    }}
    policies {{
        from-zone trust to-zone trust {{
            policy default-permit {{
                match {{
                    source-address any;
                    destination-address any;
                    application any;
                }}
                then {{
                    permit;
                }}
            }}
        }}
        from-zone trust to-zone untrust {{
            policy default-permit {{
                match {{
                    source-address any;
                    destination-address any;
                    application any;
                }}
                then {{
                    permit;
                }}
            }}
        }}
    }}
    zones {{
        security-zone trust {{
            tcp-rst;
            interfaces {{
                ge-0/0/0.0;
            }}
        }}
        security-zone untrust {{
            screen untrust-screen;
        }}
    }}
}}
interfaces {{
    ge-0/0/0 {{
        unit 0 {{
            family inet {{
                dhcp;
            }}
        }}
    }}
    fxp0 {{
        unit 0 {{
            family inet {{
                dhcp;
            }}
        }}
    }}
}}
	  '''.format(**data)

    return config
