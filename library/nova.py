from clients import nova
import random, time

def random_server_name():
    verbs = ('Squashed','Squeaming','Bouncing','Unkept','Disgusting','Whopping','Joking', 'Running', 'Walking', 'Jumping', 'Bumping', 'Rolling')
    veggies = ('Alfalfa','Anise','Artichoke','Arugula','Asparagus','Aubergine','Azuki','Banana','Basil','Bean','Beet','Beetroot','bell','Black','Borlotti','Broad','Broccoflower','Broccoli','Brussels','Butternut','Cabbage','Calabrese','Capsicum','Caraway','Carrot','Carrots','Cauliflower','Cayenne','Celeriac','Celery','Chamomile','Chard','Chickpeas','Chili','Chives','Cilantro','Collard','Corn','Courgette','Cucumber','Daikon','Delicata','Dill','Eggplant','Endive','Fennel','Fiddleheads','Frisee','fungus','Garlic','Gem','Ginger','Habanero','Herbs','Horseradish','Hubbard','Jalapeno','Jicama','Kale','Kidney','Kohlrabi','Lavender','Leek','Legumes','Lemon','Lentils','Lettuce','Lima','Maize','Mangetout''Marjoram','Marrow','Mung','Mushrooms','Mustard','Nettles','Okra','Onion','Oregano','Paprika','Parsley','Parsley','Parsnip','Patty','Peas','Peppers','pimento','Pinto','plant','Potato','Pumpkin','Purple','Radicchio','Radish','Rhubarb','Root','Rosemary','Runner','Rutabaga','Rutabaga','Sage','Salsify','Scallion','Shallot','Skirret','Snap','Soy','Spaghetti','Spinach','Spring','Squash','Squashes','Swede','Sweet','Sweetcorn','Tabasco','Taro','Tat','Thyme','Tomato','Tubers','Turnip','Turnip','Wasabi','Water','Watercress','White','Yam','Zucchini')
    name = '-'.join([random.choice(verbs), random.choice(veggies)])
    
    return name

def boot_instance(name,image,flavor,az,**kwargs):
    """
    :param name: name to be given to instance
    :param image: image to be used to boot an instance
    :param flavor: flavor to be used to boot an instance
    :param az: availability zone to land in
    :param kwargs: Optional additional arguments for server creation
    """

    # Define optional server arguments
    server_args = {}

    # Check to see if ports have been passed during boot
    # Ports are passed in a specific order based on the server
    if kwargs.get('ports') is not None:
        print kwargs.get('ports')
        server_args['nics'] = []
        for port in kwargs.get('ports'):
            for portname,portid in port.items():
		server_args['nics'].append({'port-id':portid})

    # Check to see if networks have been passed during boot
    # (todo) ensure this doesn't overwrite ports in the dict already
    if kwargs.get('networks') is not None:
	server_args['nics'] = []
        for networkid in kwargs.get('networks'):
            server_args['nics'].append({'net-id':networkid})

    # Check to see if config-drive is enabled
    if kwargs.get('config_drive') is not None:
	server_args['config_drive'] = kwargs.get('config_drive') # Otherwise, use Nova default

    # Check to see if userdata has been passed
    if kwargs.get('userdata') is not None:
	server_args['userdata'] = kwargs.get('userdata')

    # Check to see if file has been injected
    # (todo) support multiple injected files
    if kwargs.get('file_path') is not None:
	server_args['files'] = {'path':kwargs.get('file_path'),
				"contents":kwargs.get('file_contents')}
    print server_args

    server = nova.servers.create(name=name,
		                image=image,
                		flavor=flavor,
		                availability_zone=az,
				**server_args)

    return server

def boot_server(hostname,image_id,flavor_id,ports,file_contents,az,file_path):

    # Convert ports to a list of dictionaries
    nic_ports = []
    for port in ports:
        for portname,portid in port.items():
	    nic_ports.append({'port-id':portid})

    server = nova.servers.create(name=hostname,
                image=image_id,
                flavor=flavor_id,
                availability_zone=az,
                nics=nic_ports,
                config_drive="True",
                files={"path":file_path,"contents":file_contents}
                )

    return server

def boot_lb(hostname,image_id,flavor_id,ports,userdata,az):

    # Convert ports to a list of dictionaries
    nic_ports = []
    for port in ports:
        for portname,portid in port.items():
            nic_ports.append({'port-id':portid})

    server = nova.servers.create(name=hostname,
		image=image_id,
		flavor=flavor_id,
		availability_zone=az,
		nics=nic_ports,
		config_drive="True",
		userdata=userdata
		)

    return server

def boot_vm(hostname,network_id,image_id,flavor_id,az):

    server = nova.servers.create(name=hostname,
                image=image_id,
                flavor=flavor_id,
                availability_zone=az,
                nics=[{'net-id':network_id}]
                )
    return server

def check_status(server_id):
    
    # Returns the status of the instance. Delayed (usually) by busy API.
    server = nova.servers.get(server_id)
    return server.status

def get_console(server):

    # Returns VNC URL
    # (todo) Return novnc or xvpvnc. Or catch the error. What about spice url?
    # nova get-spice-console 5e8c309d-f279-493c-b051-f817ffe4b748 spice-html5
#    vnc = server.get_vnc_console("xvpvnc")
    vnc = server.get_spice_console("spice-html5")
    return vnc['console']['url']

