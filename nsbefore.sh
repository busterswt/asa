#!/usr/bin/bash
# Fetch public key using HTTP
ATTEMPTS=3
FAILED=0

echo "Attempting to retrieve key from metadata..."
while [ ! -f /nsconfig/ssh/authorized_keys ]; do
  curl -f http://169.254.169.254/latest/meta-data/public-keys/0/openssh-key --connect-timeout 5 > /tmp/metadata-key 2>/dev/null
  if [ $? -eq 0 ]; then
    cat /tmp/metadata-key >> /nsconfig/ssh/authorized_keys
    chmod 0600 /nsconfig/ssh/authorized_keys
    rm -f /tmp/metadata-key
    echo "Successfully retrieved public key from instance metadata"
    echo "*****************"
    echo "AUTHORIZED KEYS"
    echo "*****************"
    cat /nsconfig/ssh/authorized_keys
    echo "*****************"
  else
    FAILED=`expr $FAILED + 1`
    if [ $FAILED -ge $ATTEMPTS ]; then
      echo "Failed to retrieve public key from instance metadata after $FAILED attempts, trying via DHCP server(s)"
      break
    fi
    echo "Could not retrieve public key from instance metadata (attempt #$FAILED/$ATTEMPTS), retrying in 5 seconds..."
    ifconfig 0/1
    sleep 5
  fi
done

# If the metadata server is not reachable, try the DHCP server
# Reset failed attempts
FAILED=0

while [ ! -f /nsconfig/ssh/authorized_keys ]; do
   DHCPSERVER=`grep dhcp-server-identifier /var/db/dhclient.leases.1 | awk '{print $NF}' | sed -e 's/;//' | uniq | tail -1`

   curl -f http://$DHCPSERVER/latest/meta-data/public-keys/0/openssh-key --connect-timeout 5 > /tmp/metadata-key 2>/dev/null
   if [ $? -eq 0 ]; then
      cat /tmp/metadata-key >> /nsconfig/ssh/authorized_keys
      chmod 0600 /nsconfig/ssh/authorized_keys
      rm -f /tmp/metadata-key
      echo "Successfully retrieved public key from instance metadata via DHCP server"
      echo "*****************"
      echo "AUTHORIZED KEYS"
      echo "*****************"
      cat /nsconfig/ssh/authorized_keys
      echo "*****************"
      break
   else
      FAILED=`expr $FAILED + 1`
      if [ $FAILED -ge $ATTEMPTS ]; then
        echo "Failed to retrieve public key from instance metadata via DHCP server $DHCPSERVER after $FAILED attempts, quitting"
      fi
      break
      echo "Could not retrieve public key from instance metadata via DHCP server $DHCPSERVER (attempt #$FAILED/$ATTEMPTS), retrying in 5 seconds..."
      sleep 5
   fi
done
