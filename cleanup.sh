echo "Cleanup script that deletes projects, users, networks"
echo "and ports created by the NFV PoC script."
echo -e "\n"
read -n1 -rsp "Press space to continue..." key

if [ "$key" = '' ]; then
	echo -e "\nDeleting Ports..."
	for i in $(neutron port-list | grep -v 'Jumping-MangetoutMarjoram' | grep -E 'MGMT|FAILOVER|OUTSIDE|INSIDE|EXTERNAL|INTERNAL' | awk {'print $2'}); do neutron port-delete $i; done
	echo -e "\nDeleting Networks..."
	for i in $(neutron net-list | grep -v 'Jumping-MangetoutMarjoram' | grep -E 'FAILOVER|FW-LB|INSIDE' | awk {'print $2'}); do neutron net-delete $i; done
	echo -e "\nDeleting users..."
	for i in $(openstack user list | grep -E 'User_' | awk {'print $2'}); do openstack user delete $i; done
        echo -e "\nDeleting projects..."
	for i in $(openstack project list | grep -E 'Moonshine' | awk {'print $2'}); do openstack project delete $i; done
else
	echo -e "\nExiting cleanup!"
fi
