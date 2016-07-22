```
usage: moonshine [-h] {list,find,create} ...

Proof of concept instance deployment tool used to bootstrap and deploy virtual
network devices, including firewalls and load balancers

positional arguments:
  {list,find,create}  commands
    list              List all virtual network instances
    find              Find virtual network instances
    create            Create virtual network device(s)

optional arguments:
  -h, --help          show this help message and exit
```
```
usage: moonshine list [-h]

optional arguments:
  -h, --help  show this help message and exit
```
```
usage: moonshine find [-h] [--env ENV] [--account ACCOUNT_NUMBER]

optional arguments:
  -h, --help            show this help message and exit
  --env ENV             Find instance based on environment number
  --account ACCOUNT_NUMBER
                        Find instance based on account number
```
```
usage: moonshine create [-h] --env ENV --account ACCOUNT_NUMBER
                        [--fw {asav5,asav10,asav30,vsrx}]
                        [--lb {ltm,netscaler}] [--ha] [--vm]

optional arguments:
  -h, --help            show this help message and exit
  --env ENV             Specify DCX environment number
  --account ACCOUNT_NUMBER
                        Specify CORE account number
  --fw {asav5,asav10,asav30,vsrx}
                        Specify firewall type
  --lb {ltm,netscaler}  Specify load balancer type
  --ha                  Builds network instances in a highly-available manner
  --vm                  Builds a virtual machine on the backend
```
  
The script will build a firewall and load balancer in standalone or HA mode. There is still work to do to bootstrap the instances.

Bugs:
https://bugs.launchpad.net/nova/+bug/1572593
