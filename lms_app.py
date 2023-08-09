from flask import Flask, request
from flask_restx import Api, Resource,fields, reqparse
from pymongo import MongoClient
import csv
from werkzeug.datastructures import FileStorage

app = Flask(__name__)
api = Api(app, version='1.0', title='LMS API', description='API for Library Management System')

mongo_client = MongoClient('mongodb://localhost:27017/')
db = mongo_client['lms_db']
collection = db['lms']

inventory_model = api.model('Inventory', {
    'inv_logo': fields.String(required=True, description='Inventory logo'),
    'inv_id': fields.String(required=True, description='Inventory ID'),
    'inv_name': fields.String(required=True, description='Inventory name'),
    'inv_description': fields.String(required=True, description='Inventory description'),
    'inv_type': fields.String(required=True, description='Inventory type'),
    'inv_blob': fields.String(required=True, description='Inventory blob'),
    'inv_archieve_status': fields.Boolean(required=True, description='Inventory archive status')
})

UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'csv'

upload_model = api.model('UploadCSV', {
    'file': fields.Raw(required=True, description='CSV File')
})

upload_parser = reqparse.RequestParser()
upload_parser.add_argument('file', location='files', type=FileStorage, required=True)

@api.route('/inventory/upload')
class UploadCSV(Resource):
    @api.expect(upload_parser)
    def post(self):
        args = upload_parser.parse_args()
        uploaded_file = args['file']

        try:
            collection.delete_many({})  # Delete existing data
            data = csv.DictReader(uploaded_file.stream.read().decode('utf-8').splitlines())
            inserted_ids = []
            for row in data:
                result = collection.insert_one(row)
                inserted_ids.append(str(result.inserted_id))
            
            return {'message': 'Data uploaded successfully', 'inserted_ids': inserted_ids}, 200
        except Exception as e:
            return {'error': 'An error occurred while uploading data'}, 500

@api.route('/inventory/create')
class CreateInventory(Resource):
    @api.doc(description='Create a new inventory record', body=inventory_model)
    def post(self):
        try:
            inventory_data = api.payload
            inv_logo = inventory_data['inv_logo']
            inv_id = inventory_data['inv_id']
            inv_name = inventory_data['inv_name']
            inv_description = inventory_data['inv_description']
            inv_type = inventory_data['inv_type']
            inv_blob = inventory_data['inv_blob']
            inv_archieve_status = inventory_data['inv_archieve_status']
            
            existing_inventory = collection.find_one({'inv_id': inv_id})
            if existing_inventory:
                return {'message': 'Inventory record with the same ID already exists'}, 400
            result = collection.insert_one({
                'inv_logo': inv_logo,
                'inv_id': inv_id,
                'inv_name': inv_name,
                'inv_description': inv_description,
                'inv_type': inv_type,
                'inv_blob': inv_blob,
                'inv_archieve_status': inv_archieve_status
            })           
            inserted_id = str(result.inserted_id)
            return {'message': 'Inventory record created successfully', 'inventory_id': inserted_id}, 201       
        except Exception as e:
            return {'message': f'Error: {e}'}, 500


@api.route('/inventory/view')
class DisplayUploadedCSV(Resource):
    @api.doc(params={'page': 'Page number', 'limit': 'Items per page'})
    def get(self):
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
        }

@api.route('/inventory/update')
class UpdateResource(Resource):
    @api.doc(params={'inv_id': 'Inventory ID'})
    def get(self):
        inv_id = request.args.get('inv_id')
        if not inv_id:
            return {'error': 'Inventory ID not provided'}, 400
        record = collection.find_one({'inv_id': inv_id}, {'_id': 0})
        if record:
            return record
        return {'message': 'Record not found'}, 404

    @api.doc(params={'inv_id': 'Inventory ID'})
    @api.expect(api.model('UpdateData', {
        'inv_logo': fields.String(required=True,description='Field 1'),
        'inv_name': fields.String(required=True, description='Field 2'),
        'inv_description': fields.String(required=True, description='Field 3'),
        'inv_type': fields.String(required=True, description='Field 4'),
        'inv_blob': fields.String(required=True, description='Field 5'),
        'inv_achive_status': fields.Boolean(required=True, description='Field 6'),
    }))
    def put(self):
        inv_id = request.args.get('inv_id')
        if not inv_id:
            return {'error': 'Inventory ID not provided'}, 400
        data = api.payload
        result = collection.update_one({'inv_id': inv_id}, {'$set': data})
        if result.matched_count:
            return {'message': 'Record updated successfully'}
        return {'message': 'Record not found'}, 404

@api.route('/inventory/delete')
class DeleteResource(Resource):
    @api.doc(params={'inv_id': 'Inventory ID'})
    def delete(self):
        inv_id = request.args.get('inv_id')
        if not inv_id:
            return {'error': 'Inventory ID not provided'}, 400

        try:
            record = collection.find_one({'inv_id': inv_id})
            if record is None:
                return {'message': 'Inventory item not found'}, 404
            result = collection.delete_one({'inv_id': inv_id})

            if result.deleted_count > 0:
                return {'message': 'Inventory item deleted successfully'}, 200
            else:
                return {'message': 'Failed to delete inventory item'}, 500

        except Exception as e:
            return {'message': f'Error: {e}'}, 500

@api.route('/inventory/deletemany')
class DeleteResource(Resource):
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


if __name__ == '__main__':
    app.run(debug=True,port=5001)

