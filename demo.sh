# Create the networks used for the environment
echo 'Creating networks...'

./moonshine.py create-networks -j \
'{
    "account_number": "123456",
    "environment_number": "ENV123456",
    "networks": [
        {
            "network_name": "lb_failover",
            "purpose": "failover",
            "network_type": "vxlan",
            "cidr": "192.168.255.0/24"
        },
        {
            "network_name": "fw_failover",
            "purpose": "failover",
            "network_type": "vxlan",
            "cidr": "192.168.254.0/24"
        },
        {
            "network_name": "fw_inside",
            "purpose": "inside",
            "network_type": "vxlan",
            "cidr": "192.168.1.0/27"
        },
        {
            "network_name": "lb_inside",
            "purpose": "inside",
            "cidr": "10.0.1.0/24"
        }
    ]
}'	

sleep 1

# Creatr the ports used in the environment
echo 'Creating ports for devices...'

./moonshine.py create-ports -j \
'{
    "account_number": "123456",
    "environment_number": "ENV123456",
    "device_number": "111111",
    "ports": [
        {
            "network_name": "fw_inside",
            "port_security_enabled": "False"
        }, 
        {
            "network_name": "management",
            "port_security_enabled": "False"
        },    
        {
            "network_name": "outside",
            "port_security_enabled": "False"
        },
        {
            "network_name": "fw_failover",
            "port_security_enabled": "False"
        }
    ]
}'	

./moonshine.py create-ports -j \
'{
    "account_number": "123456",
    "environment_number": "ENV123456",
    "device_number": "222222",
    "ports": [
        {
            "network_name": "fw_inside",
            "port_security_enabled": "False"
        }, 
        {
            "network_name": "management",
            "port_security_enabled": "False"
        },    
        {
            "network_name": "outside",
            "port_security_enabled": "False"
        },
        {
            "network_name": "fw_failover",
            "port_security_enabled": "False"
        }
    ]
}'	

./moonshine.py create-ports -j \
'{
    "account_number": "123456",
    "environment_number": "ENV123456",
    "device_number": "333333",
    "ports": [
        {
            "network_name": "fw_inside",
            "port_security_enabled": "False"
        }, 
        {
            "network_name": "management",
            "port_security_enabled": "False"
        },    
        {
            "network_name": "lb_failover",
            "port_security_enabled": "False"
        },
        {
            "network_name": "lb_inside",
            "port_security_enabled": "False",
            "ip_address": "10.0.1.2"
        }
    ]
}'	

./moonshine.py create-ports -j \
'{
    "account_number": "123456",
    "environment_number": "ENV123456",
    "device_number": "444444",
    "ports": [
        {
            "network_name": "fw_inside",
            "port_security_enabled": "False"
        }, 
        {
            "network_name": "management",
            "port_security_enabled": "False"
        },    
        {
            "network_name": "lb_failover",
            "port_security_enabled": "False"
        },
        {
            "network_name": "lb_inside",
            "port_security_enabled": "False",
            "ip_address": "10.0.1.3"
        }
    ]
}'	

sleep 1

echo "Creating instances..."

./moonshine.py create-instance -j \
'{
    "account_number": "123456",
    "environment_number": "ENV123456",
    "device_number": "111111",
    "peer_device": "222222",
    "device_type": "firewall",
    "device_model": "asav5",
    "device_priority": "primary",
    "ports": [
        {
            "network_name": "management"
        }, 
        {
            "network_name": "outside"
        },    
        {
            "network_name": "fw_inside"
        },
        {
            "network_name": "fw_failover"
        }
    ]
}'	

./moonshine.py create-instance -j \
'{
    "account_number": "123456",
    "environment_number": "ENV123456",
    "device_number": "222222",
    "peer_device": "111111",
    "device_type": "firewall",
    "device_model": "asav5",
    "device_priority": "secondary",
    "ports": [
        {
            "network_name": "management"
        }, 
        {
            "network_name": "outside"
        },    
        {
            "network_name": "fw_inside"
        },
        {
            "network_name": "fw_failover"
        }
    ]
}'	

./moonshine.py create-instance -j \
'{
    "account_number": "123456",
    "environment_number": "ENV123456",
    "device_number": "333333",
    "peer_device": "444444",
    "device_type": "loadbalancer",
    "device_model": "ltm",
    "device_priority": "primary",
    "ports": [
        {
            "network_name": "management"
        }, 
        {
            "network_name": "fw_inside"
        },    
        {
            "network_name": "lb_inside"
        },
        {
            "network_name": "lb_failover"
        }
    ]
}'	

./moonshine.py create-instance -j \
'{
    "account_number": "123456",
    "environment_number": "ENV123456",
    "device_number": "444444",
    "peer_device": "333333",
    "device_type": "loadbalancer",
    "device_model": "ltm",
    "device_priority": "secondary",
    "ports": [
        {
            "network_name": "management"
        }, 
        {
            "network_name": "fw_inside"
        },    
        {
            "network_name": "lb_inside"
        },
        {
            "network_name": "lb_failover"
        }
    ]
}'	
