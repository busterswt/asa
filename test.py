import base64, os, tempfile, commands
from library.clients import nova
from library.nova import random_server_name

#print nova.servers.list()

hostname = random_server_name()

data = {'hostname': hostname, 'security_level': '80'}

file_contents = """hostname {hostname}
interface management0/0
nameif management
security-level {security_level}
ip address dhcp setroute
""".format(**data)

file_path = "day0"

server = nova.servers.create(name=hostname,
                    image="1499479f-80d9-4f39-9129-eec7b6c8d976",
                    flavor="0b105c5e-62d5-4212-8538-afb3f45c34b9",
                    nics=[{"net-id":"463bbed0-a84a-4c7c-8783-d73113d7e830"}],
                    config_drive="True",
                    files={"path":file_path,"contents":file_contents}
#                    files={"path":"day0","contents":"hostname ASA1"}
                   )

#server = nova.servers.find(id=server.id)
