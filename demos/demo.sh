# Create the networks used for the environment
echo 'Creating networks...'

./moonshine create-networks -j \
'{
    "account_number": "888888",
    "environment_number": "ENV888888",
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

./moonshine create-ports -j \
'{
    "account_number": "888888",
    "environment_number": "ENV888888",
    "device_number": "555555",
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

./moonshine create-ports -j \
'{
    "account_number": "888888",
    "environment_number": "ENV888888",
    "device_number": "666666",
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

./moonshine create-ports -j \
'{
    "account_number": "888888",
    "environment_number": "ENV888888",
    "device_number": "777777",
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

./moonshine create-ports -j \
'{
    "account_number": "888888",
    "environment_number": "ENV888888",
    "device_number": "888888",
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

./moonshine create-instance -j \
'{
    "account_number": "888888",
    "environment_number": "ENV888888",
    "device_number": "555555",
    "peer_device": "666666",
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

./moonshine create-instance -j \
'{
    "account_number": "888888",
    "environment_number": "ENV888888",
    "device_number": "666666",
    "peer_device": "555555",
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

./moonshine create-instance -j \
'{
    "account_number": "888888",
    "environment_number": "ENV888888",
    "device_number": "777777",
    "peer_device": "888888",
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

./moonshine create-instance -j \
'{
    "account_number": "888888",
    "environment_number": "ENV888888",
    "device_number": "888888",
    "peer_device": "777777",
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
