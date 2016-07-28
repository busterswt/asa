echo "Project Moonshine Demo:"
echo "Builds highly-available ASA firewalls"
echo -e "\n"
read -n1 -rsp "Press space to continue..." key

# source credentials
source /root/asa.alpha/openrc.moonshine

# Delete the old environment (if exists)
echo -e "\n"
echo "Deleting old demo environment (if it exists)..."
/root/asa.alpha/moonshine.py delete -e ENV111111

# Generate a random string used for the account number
ACCOUNT_NUMBER=$(cat /dev/urandom | tr -dc '0-9' | fold -w 6 | head -n 1)

# Create the networks used for the environment
echo 'Creating networks...'

/root/asa.alpha/moonshine.py create-networks -j \
'{
    "account_number": "'$ACCOUNT_NUMBER'",
    "environment_number": "ENV111111",
    "networks": [
        {
            "network_name": "fw_inside",
            "purpose": "inside",
            "network_type": "vlan",
            "cidr": "192.168.100.0/24"
        },
        {
            "network_name": "fw_failover",
            "purpose": "inside",
            "network_type": "vxlan",
            "cidr": "192.168.254.0/24"
        }
    ]
}'

sleep 1

# Create the ports used in the environment
echo 'Creating ports for devices...'

DEV1=$(cat /dev/urandom | tr -dc '0-9' | fold -w 6 | head -n 1)

/root/asa.alpha/moonshine.py create-ports -j \
'{
    "account_number": "'$ACCOUNT_NUMBER'",
    "environment_number": "ENV111111",
    "device_number": "'$DEV1'",
    "ports": [
        {
            "network_name": "fw_inside",
            "ip_address": "192.168.100.1",
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

DEV2=$(cat /dev/urandom | tr -dc '0-9' | fold -w 6 | head -n 1)

/root/asa.alpha/moonshine.py create-ports -j \
'{
    "account_number": "'$ACCOUNT_NUMBER'",
    "environment_number": "ENV111111",
    "device_number": "'$DEV2'",
    "ports": [
        {
            "network_name": "fw_inside",
            "ip_address": "192.168.100.2",
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

sleep 1

echo "Creating instances..."

/root/asa.alpha/moonshine.py create-instance -j \
'{
    "account_number": "'$ACCOUNT_NUMBER'",
    "environment_number": "ENV111111",
    "device_number": "'$DEV1'",
    "peer_device": "'$DEV2'",
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

/root/asa.alpha/moonshine.py create-instance -j \
'{
    "account_number": "'$ACCOUNT_NUMBER'",
    "environment_number": "ENV111111",
    "device_number": "'$DEV2'",
    "peer_device": "'$DEV1'",
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

# (todo) add some code to check on status of environment
# (todo) add some code to return info about instances and networks
