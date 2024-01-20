from flask import Flask, request
from flask_restx import Api, Resource, fields, reqparse,Namespace
from pymongo import MongoClient
import csv
from werkzeug.utils import secure_filename
from werkzeug.datastructures import FileStorage
from bson.objectid import ObjectId
import random
import string
import datetime
import requests 
import base64
#from jose import jwt
from flask_jwt_extended import JWTManager, jwt_required,get_jwt_identity
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization


app = Flask(__name__)
api = Api(app, version='1.0', title='Inventory API', description='API for Library Management System')
mongo_client = MongoClient('mongodb://172.18.0.3:27017/')
db = mongo_client['inventory_db']
collection = db['inventory_items']

archived_collection = db['archived_inventory']


encoded_public_key = "LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUlJQ0lqQU5CZ2txaGtpRzl3MEJBUUVGQUFPQ0FnOEFNSUlDQ2dLQ0FnRUE2cWhXQTNjSlhLNGdlQTBNRy8rMgpVQVRuNk5Tb1lxT2lMcWx1UllPbHZ2VHgyWXNwNGhpcEFpaHZDUUdpMEt1ZjlON0tXRFNoR2VIcVRjNUs5TU9DCnBvRlpvWE45SFlVSzVIVUZHV0VDV2djRXRiU1VTZE5VVmZVS2U5SmF6ZElLS3pPQnB2STZ6L0dMZUgyekp5QmcKT0VsNWdiczc3RExLQ05IQVhFRitFa1E4eVQzL1N2V2dINVFWSXl5c2x6NEJ3S0d2WkVtUDE3aVhZS0dsOUI4ZAo0TWpvTjl2SCtMbVJvbEIxeTMvR0lrRHVIM1BGcHJVbExpWVlkblA2bHEyMXpYUTVIU1Y4bmp0TlV0UU9FRG9RCmp3c2hPVE9MUDdLeXl6R3JKM2xEZHJTaFJjc1lHRVBDV0xTUVNPSXd2ZnVOaDh2aEovaW40UGlqdXl4WUphaGIKdFVydjVNandUQVJZbjV4MjE4UTllMHZoa3BaQWgvd3ZCUkJMMGh3d29QL2NtQTNMTHJqVXJmdXlBdlF1SkJYNAp6QXpLTklma3F1dHU3VlpHQThFTWFUdXA0UkxxOCtJZU5QNlc2S1plSmdQbzg3MVdBcjFMWmo4bnU2THp1cTM0Ck0vWEtTVDFubXZKOVJwM3VXdTVTQjEyc0RBdHkrZFJnOFpETGhLMXpDb2s2OTZmWjlOcXl6aTVHY3dxSXNTK1IKSm1kQzhPUzcyOEhCTmhvYThHYVlTUmZLMWRNejFSSGh4ai9FcEU4RWRwWjk2dDRCdktBQTJUYzNJRmE5VGxsago5QzY0VmZXcGtFOFV2RC90a296L0VxR2VocGlzdEUxbE5vNk5QM1hZOHpDRkN3TXZLekhhYlZ0VFhpVWE4ZitlCnU2U2pWU29vNEdsUGpBN25EMExIaitzQ0F3RUFBUT09Ci0tLS0tRU5EIFBVQkxJQyBLRVktLS0tLQ=="

# Decode the public key using US-ASCII encoding
encoding = "ascii"
decoded_public_key = base64.b64decode(encoded_public_key)
public_key = serialization.load_pem_public_key(decoded_public_key, backend=default_backend())


# Configure JWT to use the public key for verification
app.config['JWT_ALGORITHM'] = 'RS256'
app.config['JWT_PUBLIC_KEY'] = public_key
app.config['JWT_IDENTITY_CLAIM'] = '_id'


jwt = JWTManager(app)

def verify_token(fn):
    @jwt_required()
    def wrapper(*args, **kwargs):
        current_user = get_jwt_identity()
        print("Received Token:", request.headers.get('Authorization'))
        return fn(current_user, *args, **kwargs)
    return wrapper



inventory_model = api.model('Inventory', {
    'inv_logo': fields.String(required=True, description='Inventory logo'),
    'inv_name': fields.String(required=True, description='Inventory name'),
    'inv_description': fields.String(required=True, description='Inventory description'),
    'inv_type': fields.String(required=True, description='Inventory type'),
    'inv_blob': fields.String(required=True, description='Inventory blob'),
    'inv_archive_status': fields.Boolean(required=True, description='Inventory archive status'),
    'inv_copies': fields.Integer(required=True,description='Inventory number of Copies')
})

authorizations={
    "jsonWebToken":{
        "type":"apiKey",
        "in":"header",
        "name":"Authorization",
        "description": 'Type `Bearer` followed by your token',
    }
}

api.authorizations = {
    "jsonWebToken": {
        "type": "apiKey",
        "in": "header",
        "name": "Authorization",
        "description": 'Type `Bearer` followed by your token',
    }
}



ns = Namespace("api", authorizations=authorizations)  
api.security = 'jsonWebToken'



UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'csv'

upload_model = api.model('UploadCSV', {
    'file': fields.Raw(required=True, description='CSV File')
})

upload_parser = reqparse.RequestParser()
upload_parser.add_argument('file', location='files', type=FileStorage, required=True)

def generate_inventory_id():
    timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    random_suffix = ''.join(random.choices(string.digits, k=4))
    return f'r{timestamp}{random_suffix}'

@api.route('/inventory/upload')
class UploadCSV(Resource):
    @jwt_required()  # Add the authorization decorator
    @api.expect(upload_parser)
    def post(self):
        try:
            current_user = get_jwt_identity()  # Retrieve the user identity
            args = upload_parser.parse_args()
            uploaded_file = args['file']

            data = csv.DictReader(uploaded_file.stream.read().decode('utf-8').splitlines())
            inserted_ids = []

            for row in data:
                row['inv_id'] = str(ObjectId())  # Generate unique inv_id

                # Convert inv_archive_status to boolean
                inv_archive_status = row.get('inv_archive_status', '').upper() == 'TRUE'
                row['inv_archive_status'] = inv_archive_status

                # Convert "inv_copies" to integer if possible
                inv_copies = row.get('inv_copies', '')
                try:
                    row['inv_copies'] = int(inv_copies)
                except ValueError:
                    row['inv_copies'] = 0  # Default to 0 if conversion to int fails

                if inv_archive_status:
                    result = collection.insert_one(row)
                else:
                    result = archived_collection.insert_one(row)

                inserted_ids.append(str(result.inserted_id))

            return {'message': 'Data uploaded successfully', 'inserted_ids': inserted_ids, 'user': current_user}, 200
        except Exception as e:
            return {'error': f'An error occurred while uploading data: {e}'}, 500



@api.route('/inventory/create')
class CreateInventory(Resource):
    @jwt_required()
    @api.doc(description='Create a new inventory record', body=inventory_model)
    def post(self):
        try:
            current_user = get_jwt_identity()  # Retrieve the user identity
            inventory_data = api.payload
            inv_logo = inventory_data['inv_logo']
            inv_name = inventory_data['inv_name']
            inv_description = inventory_data['inv_description']
            inv_type = inventory_data['inv_type']
            inv_blob = inventory_data['inv_blob']
            inv_archive_status = inventory_data['inv_archive_status']
            inv_copies = inventory_data['inv_copies']
            
            inv_id = generate_inventory_id()  # Generate unique integer inv_id

            if inv_archive_status:
                result = collection.insert_one({
                    'inv_logo': inv_logo,
                    'inv_id': inv_id,
                    'inv_name': inv_name,
                    'inv_description': inv_description,
                    'inv_type': inv_type,
                    'inv_blob': inv_blob,
                    'inv_archive_status': inv_archive_status,
                    'inv_copies': inv_copies,
                    'created_by': current_user  # Include the user who created the record
                })
            else:
                result = archived_collection.insert_one({
                    'inv_logo': inv_logo,
                    'inv_id': inv_id,
                    'inv_name': inv_name,
                    'inv_description': inv_description,
                    'inv_type': inv_type,
                    'inv_blob': inv_blob,
                    'inv_archive_status': inv_archive_status,
                    'inv_copies': inv_copies,
                    'created_by': current_user  # Include the user who created the record
                })

            inserted_id = str(result.inserted_id)
            return {'message': 'Inventory record created successfully', 'inventory_id': inv_id}, 201       
        except Exception as e:
            return {'message': f'Error: {e}'}, 500

        
@api.route('/inventory/view-all')
class DisplayAllInventory(Resource):
    
    def get(self):
        try:
              # Get the current user's identity
            cursor = collection.find({'inv_archive_status': {'$ne': 'FALSE'}}, {'_id': 0})
            data = list(cursor)
            total_records = len(data)
            return {
                'total_records': total_records,
                'data': data,
                  # Include the current user information
            }
        except Exception as e:
            return {'message': f'Error: {e}'}, 500


@api.route('/archived_inventory/view-all')
class DisplayAllArchivedInventory(Resource):
    @jwt_required()
    def get(self):
        try:
            current_user = get_jwt_identity()  # Get the current user's identity
            cursor = archived_collection.find({}, {'_id': 0})
            data = list(cursor)
            total_records = len(data)
            return {
                'total_records': total_records,
                'data': data,
                'user': current_user  # Include the current user information
            }
        except Exception as e:
            return {'message': f'Error: {e}'}, 500


@api.route('/inventory/update/<string:inv_id>')
class UpdateResource(Resource):
    @jwt_required()
    @api.expect(api.model('UpdateData', {
        'inv_logo': fields.String(required=True, description='Field 1'),
        'inv_name': fields.String(required=True, description='Field 2'),
        'inv_description': fields.String(required=True, description='Field 3'),
        'inv_type': fields.String(required=True, description='Field 4'),
        'inv_blob': fields.String(required=True, description='Field 5'),
        'inv_archive_status': fields.Boolean(required=True, description='Field 6'),
        'inv_copies': fields.Integer(required=True,description='Field 7'),
    }))
    def put(self, inv_id):
        try:
            data = api.payload
            result = collection.update_one({'inv_id': inv_id}, {'$set': data})
            if result.matched_count:
                return {'message': 'Record updated successfully'}, 200
            return {'message': 'Record not found'}, 404
        except Exception as e:
            return {'message': f'Error: {e}'}, 500

@api.route('/inventory/delete/<string:inv_id>')
class DeleteResource(Resource):
    @jwt_required()
    def delete(self, inv_id):
        try:
            result = collection.delete_one({'inv_id': inv_id})

            if result.deleted_count > 0:
                return {'message': 'Inventory item deleted successfully'}, 200
            else:
                return {'message': 'Failed to delete inventory item'}, 500

        except Exception as e:
            return {'message': f'Error: {e}'}, 500


           
@api.route('/inventory/delete-many')
class DeleteManyResource(Resource):
    @jwt_required()
    @api.doc(description='Delete inventory records in bulk')
    @api.expect(api.model('BulkDeleteData', {
        'inventory_ids': fields.List(fields.String, required=True, description='List of inventory IDs to delete')
    }))
    def delete(self):
        data = api.payload
        inventory_ids = data.get('inventory_ids', [])

        if not inventory_ids:
            return {'error': 'No inventory IDs provided for deletion'}, 400

        try:
            result = collection.delete_many({'inv_id': {'$in': inventory_ids}})
            if result.deleted_count > 0:
                return {'message': f'{result.deleted_count} inventory items deleted successfully'}, 200
            else:
                return {'message': 'No inventory items deleted'}, 404
        except Exception as e:
            return {'message': f'Error: {e}'}, 500
        

@api.route('/inventory/delete-all')
class DeleteAllResource(Resource):
    @jwt_required()
    @api.doc(description='Delete all inventory records')
    def delete(self):
        try:
            result = collection.delete_many({})
            if result.deleted_count > 0:
                return {'message': f'{result.deleted_count} inventory items deleted successfully'}, 200
            else:
                return {'message': 'No inventory items deleted'}, 404
        except Exception as e:
            return {'message': f'Error: {e}'}, 500
        

@api.route('/inventory/view')
class DisplayUploadedCSV(Resource):
    @jwt_required()
    @api.doc(params={'page': 'Page number', 'limit': 'Items per page'})
    def get(self):
        try:
            page = int(request.args.get('page', 1))
            limit = int(request.args.get('limit', 10))
            total_records = collection.count_documents({})
            
            if page < 1:
                page = 1
            skip = (page - 1) * limit
            cursor = collection.find({}, {'_id': 0}).skip(skip).limit(limit)
            data = list(cursor)
            
            return {
                'page': page,
                'limit': limit,
                'total_records': total_records,
                'data': data
            }, 200
        except Exception as e:
            return {'message': f'Error: {e}'}, 500

@api.route('/archived_inventory/delete-all')
class DeleteAllArchivedInventory(Resource):
    @jwt_required()
    @api.doc(description='Delete all archived inventory records')
    def delete(self):
        try:
            current_user = get_jwt_identity()
            result = archived_collection.delete_many({})
            if result.deleted_count > 0:
                return {'message': f'{result.deleted_count} archived inventory items deleted successfully'}, 200
            else:
                return {'message': 'No archived inventory items deleted'}, 404
        except Exception as e:
            return {'message': f'Error: {e}'}, 500



if __name__ == '__main__':
    app.run(debug=True, host= "0.0.0.0",port=5001)
