usage: python nfv.py [-h] [--lb] [--ha]

nfv.py - NFV PoC that build virtual firewalls and load balancers

optional arguments:
  -h, --help  show this help message and exit
  --lb        Builds a firewall and load balancer (routed mode)
  --ha        Builds network devices in a highly-available manner
  
Right now, image and flavor IDs are hardcoded throughout, but the plan is to eventually search for IDs by specific name or provide IDs or net device type at the command line. Network IDs are also hard-coded, for now.

The script will build a Cisco ASA in standalone or HA mode, and can support building F5s in standalone or HA mode. Work is being done to build out some virtual machines behind the F5. F5 configuration is currently limited to interface config only.
