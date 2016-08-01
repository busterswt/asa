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

@app.route("/list", methods=['GET'])
@auth.login_required
def list():
    if request.method == "GET":
        data,status_code = moonshine.list_devices(db_filename,None)
#    return render_template("list.htm", devices=devices)
        return jsonify(**data),status_code

@app.route("/list/<environment>", methods=['GET'])
@auth.login_required
def list_env(environment):
    if request.method == "GET":
        data,status_code = moonshine.list_devices(db_filename,environment_number=environment)
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
        instance = moonshine.create_instance(db_filename,json.dumps(request.json))
        return jsonify(**instance)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port="80")
