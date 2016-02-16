import textwrap

def generate_base_config(data):
    base_config = '''
        hostname {hostname}
        prompt hostname pri state
        crypto key generate rsa
        int g0/0
        no shut
        interface management0/0
        nameif management
        security-level 10
        ip address {mgmt_primary_address} {management_mask} standby {mgmt_secondary_address}
        no shut
        route management 0.0.0.0 0.0.0.0 {management_gateway}
        ssh 0.0.0.0 0.0.0.0 management
        username rpc password rpc privilege 15
        aaa authentication ssh console LOCAL
        '''.format(**data)

    return textwrap.dedent(base_config)

def generate_failover_config(data):
    failover_config = '''
        failover
        failover lan unit {priority}
        failover lan interface LANFAIL GigabitEthernet0/0
        failover polltime unit 1 holdtime 5
        failover key openstack
        failover replication http
        failover link LANFAIL GigabitEthernet0/0
        failover interface ip LANFAIL {failover_primary_address} {failover_netmask} standby {failover_secondary_address}
        '''.format(**data)

    return textwrap.dedent(failover_config)
