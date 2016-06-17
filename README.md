```
usage: nfv.py [-h] --fw {asav5,asav10,asav30,vsrx} [--lb {ltm,netscaler}]
              [--ha]

nfv.py - NFV PoC that build virtual firewalls and load balancers

optional arguments:
  -h, --help            show this help message and exit
  --fw {asav5,asav10,asav30,vsrx}
                        Specify firewall type
  --lb {ltm,netscaler}  Specify load balancer type
  --ha                  Builds network devices in a highly-available manner
```
  
The script will build a firewall and load balancer in standalone or HA mode. There is still work to do to bootstrap the instances.
