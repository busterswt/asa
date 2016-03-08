from clients import nova
import random, time

def random_server_name():
    verbs = ('Squashed','Squeaming','Bouncing','Unkept','Disgusting','Whopping','Joking', 'Running', 'Walking', 'Jumping', 'Bumping', 'Rolling')
    veggies = ('Alfalfa','Anise','Artichoke','Arugula','Asparagus','Aubergine','Azuki','Banana','Basil','Bean','Beet','Beetroot','bell','Black','Borlotti','Broad','Broccoflower','Broccoli','Brussels','Butternut','Cabbage','Calabrese','Capsicum','Caraway','Carrot','Carrots','Cauliflower','Cayenne','Celeriac','Celery','Chamomile','Chard','Chickpeas','Chili','Chives','Cilantro','Collard','Corn','Courgette','Cucumber','Daikon','Delicata','Dill','Eggplant','Endive','Fennel','Fiddleheads','Frisee','fungus','Garlic','Gem','Ginger','Habanero','Herbs','Horseradish','Hubbard','Jalapeno','Jicama','Kale','Kidney','Kohlrabi','Lavender','Leek','Legumes','Lemon','Lentils','Lettuce','Lima','Maize','Mangetout''Marjoram','Marrow','Mung','Mushrooms','Mustard','Nettles','Okra','Onion','Oregano','Paprika','Parsley','Parsley','Parsnip','Patty','Peas','Peppers','pimento','Pinto','plant','Potato','Pumpkin','Purple','Radicchio','Radish','Rhubarb','Root','Rosemary','Runner','Rutabaga','Rutabaga','Sage','Salsify','Scallion','Shallot','Skirret','Snap','Soy','Spaghetti','Spinach','Spring','Squash','Squashes','Swede','Sweet','Sweetcorn','Tabasco','Taro','Tat','Thyme','Tomato','Tubers','Turnip','Turnip','Wasabi','Water','Watercress','White','Yam','Zucchini')
    name = '-'.join([random.choice(verbs), random.choice(veggies)])
    
    return name

def boot_server(hostname,ports,file_contents,az=None):
    file_path = "day0"

#    print ports

    server = nova.servers.create(name=hostname,
                    image="2e86a35d-ee9f-4dcb-981b-a9d3b25a3fc8",
                    flavor="23252bd3-dd93-47cf-a8c1-e70eef6827e3",
                    availability_zone=az,
                    nics=[{'port-id':ports['mgmt']},{'port-id':ports['failover']},{'port-id':ports['outside']},{'port-id':ports['inside']}],
                    config_drive="True",
                    files={"path":file_path,"contents":file_contents}
#                    files={"path":"day0","contents":"hostname ASA1"}
               )

    return server

def check_status(server_id):
    
    # Returns the status of the instance. Delayed (usually) by busy API.
    server = nova.servers.get(server_id)
    return server.status

def get_console(server):

    # Returns VNC URL
    vnc = server.get_vnc_console("novnc")
    return vnc['console']['url']
