from prettytable import PrettyTable
from flask import Flask
from pprint import pprint
import moonshine
from flask import Blueprint, render_template, jsonify, json, request, make_response
from flask_httpauth import HTTPBasicAuth

auth = HTTPBasicAuth()
app = Flask(__name__,
	template_folder='templates')
db_filename = "./moonshine_db.sqlite"

users = {
    "moonshine": "openstack12345"
}

@auth.get_password
def get_pw(username):
    if username in users:
        return users.get(username)
    return None

@app.route("/")
@auth.login_required
def hello():
    return None

@app.route("/environments", methods=['GET'])
@app.route("/devices", methods=['GET'])
@auth.login_required
def list():
    if request.method == "GET":
        data,status_code = moonshine.list_devices(db_filename,None)
        if request.args.get('html'):
            return render_template("list.htm", devices=data['data'])
        else:
	    return jsonify(**data),status_code

@app.route("/environment/<environment>", methods=['GET','DELETE'])
@auth.login_required
def env(environment):
    if request.method == "GET":
        data,status_code = moonshine.list_devices(db_filename,environment_number=environment)
        return jsonify(**data),status_code
    if request.method == "DELETE":
	data,status_code = moonshine.delete_environment(db_filename,environment_number=environment)
        return jsonify(**data),status_code

@app.route("/networks", methods=['POST'])
@auth.login_required
def c_networks():
    if request.method == "POST":
        networks = moonshine.create_networks(db_filename,json.dumps(request.json))
        return jsonify(**networks)

@app.route("/ports", methods=['POST'])
@auth.login_required
def c_ports():
    if request.method == "POST":
        ports = moonshine.create_ports(db_filename,json.dumps(request.json))
        return jsonify(**ports)

@app.route("/instance", methods=['POST'])
@auth.login_required
def c_instance():
    if request.method == "POST":
        data,status_code = moonshine.create_instance(db_filename,json.dumps(request.json))
        return jsonify(**data), status_code

@app.route("/device/<device>", methods=['GET'])
@auth.login_required
def c_device(device):
    if request.method == "GET":
        data,status_code = moonshine.list_devices(db_filename,device_number=device)
	if request.args.get('html'):
            return render_template("list.htm", devices=data['data'])
	else:
            return jsonify(**data),status_code


if __name__ == "__main__":
    app.run(host="0.0.0.0", port="80")
