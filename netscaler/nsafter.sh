#!/usr/bin/bash

# Fetch userdata using HTTP
ATTEMPTS=3
FAILED=0
while [ ! -f /nsconfig/userdata ]; do
  curl -f http://169.254.169.254/openstack/2012-08-10/user_data --connect-timeout 5 > /tmp/userdata 2>/dev/null
  if [ $? -eq 0 ]; then
    cat /tmp/userdata >> /nsconfig/userdata
    chmod 0700 /nsconfig/userdata
    rm -f /tmp/userdata
    echo "Successfully retrieved userdata"
    echo "*****************"
    echo "USERDATA"
    echo "*****************"
    cat /nsconfig/userdata
    echo "*****************"
    /nsconfig/userdata
  else
    FAILED=`expr $FAILED + 1`
    if [ $FAILED -ge $ATTEMPTS ]; then
      echo "Failed to retrieve userdata from instance metadata after $FAILED attempts, quitting"
      break
    fi
    echo "Could not retrieve userdata from instance metadata (attempt #$FAILED/$ATTEMPTS), retrying in 5 seconds..."
    sleep 5
  fi
done

# Reset failed attempts
FAILED=0

while [ ! -f /nsconfig/userdata ]; do
   DHCPSERVER=`grep dhcp-server-identifier /var/db/dhclient.leases.1 | awk '{print $NF}' | sed -e 's/;//' | uniq | tail -1`

   curl -f http://$DHCPSERVER/openstack/2012-08-10/user_data --connect-timeout 5 > /tmp/userdata 2>/dev/null
   if [ $? -eq 0 ]; then
      cat /tmp/userdata >> /nsconfig/userdata
      chmod 0700 /nsconfig/userdata
      rm -f /tmp/userdata
      echo "Successfully retrieved userdata"
      echo "*****************"
      echo "USERDATA"
      echo "*****************"
      cat /nsconfig/userdata
      echo "*****************"
      /nsconfig/userdata
      break
   else
      FAILED=`expr $FAILED + 1`
      if [ $FAILED -ge $ATTEMPTS ]; then
        echo "Failed to retrieve userdata via DHCP server $DHCPSERVER after $FAILED attempts, quitting"
        break 3
      fi
      echo "Could not retrieve userdata via DHCP server $DHCPSERVER (attempt #$FAILED/$ATTEMPTS), retrying in 5 seconds..."
      sleep 5
   fi
done
