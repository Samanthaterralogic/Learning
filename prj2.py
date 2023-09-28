from flask import Flask, request
from flask_restx import Api, Resource, fields, reqparse, abort
from pymongo import MongoClient
from bson.objectid import ObjectId
from flasgger import Swagger
import datetime
import csv, os, random, string
from bson import json_util
from werkzeug.datastructures import FileStorage
import calendar
import requests
import sys
import logging
from bson import ObjectId
import json
from flask import jsonify


# Add the parent directory of prj1 to the Python path
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(parent_dir)

# Configure the logging
logging.basicConfig(level=logging.DEBUG)  # Set the logging level to DEBUG

from prj1.prj1 import fetch_inventory_data

app = Flask(__name__)
swagger = Swagger(app)
api = Api(app, version='1.0', title='Reservation API', description='API for Reservation Management')
mongo_client = MongoClient('mongodb://localhost:27017/')
db = mongo_client['reservations_db']
collection = db['reservation11']

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'csv'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

upload_model = api.model('UploadCSV', {
    'file': fields.Raw(required=True, description='CSV File')
})

reservation_model = api.model('Reservation', {
    'Reserved_user': fields.String(required=True, description='Name of the user making the reservation'),
    'Reserved_user_email':fields.String(required=True,description='Reserverd user email'),
    'inv_id':fields.String(required=True,description='the inventory id'),
    'Reservation_status': fields.String(description='Status of the reservation'),
    'Reservation_status_comments': fields.String(description='Additional comments on the reservation status'),
    #'inv_type': fields.List(fields.String, description='List of reserved items'),
    'count': fields.Integer(required=True, description='Count of the items in the reservation'),
})

def generate_reservation_id():
    timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    random_suffix = ''.join(random.choices(string.digits, k=4))
    return f'r{timestamp}{random_suffix}'

class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime, ObjectId)):  # Add ObjectId if needed
            return obj.isoformat()
        return super().default(obj)

app.json_encoder = CustomJSONEncoder

@api.route('/reservations/create')
class CreateReservation(Resource):
    @api.doc(description='Create a new reservation', body=reservation_model)
    def post(self):
        reservation_data = api.payload
        inventory_data = fetch_inventory_data()
        # Ensure a unique reservation_id is generated for each reservation
        reservation_id = generate_reservation_id()

        # Initialize inv_id_set here
        inv_id_set = set()

        # Add logging statements to inspect variable values
        logging.debug(f'reservation_data: {reservation_data}')
        logging.debug(f'inventory_data: {inventory_data}')
        logging.debug(f'reservation_id: {reservation_id}')
        logging.debug(f'inv_id_set: {inv_id_set}')

        # Strip leading and trailing whitespace from inv_id
        inv_id = reservation_data['inv_id'].strip()

        # Extract required fields from the inventory data
        if 'data' in inventory_data and len(inventory_data['data']) > 0:
            inv_id_set = set(item['inv_id'] for item in inventory_data['data'])
        else:
            abort(500, error='No inventory data available')

        inv_id = reservation_data['inv_id']

        inv_description = None
        inv_type = None
        inv_name = None
        #inv_logo = None
        inv_blob = None
        inv_archieve_status = None
        
        for item in inventory_data['data']:
            if item['inv_id'] == inv_id:
                inv_name = item.get('inv_name', '')
                inv_description = item.get('inv_description', '')
                inv_type = item.get('inv_type', '')
                #inv_logo = item.get('inv_logo', '')  # Fetch inv_logo
                inv_blob = item.get('inv_blob', '')  # Fetch inv_blob
                inv_archieve_status = item.get('inv_archieve_status', '')  # Fetch inv_archieve_status
                logging.debug(f'Matched inventory item: {item}')
                break

        # Log inv_id values before the check
        logging.debug(f'inv_id from reservation_data: {inv_id}')
        logging.debug(f'inv_id from inventory_data: {inv_id_set}')

        # Log inv_description and inv_type here
        logging.debug(f'inv_description: {inv_description}')
        logging.debug(f'inv_type: {inv_type}')
        #logging.debug(f'inv_logo: {inv_logo}')  # Log inv_logo
        logging.debug(f'inv_blob: {inv_blob}')  # Log inv_blob
        logging.debug(f'inv_archieve_status: {inv_archieve_status}')  # Log inv_archieve_status

        if inv_id not in inv_id_set:
            abort(400, error=f'inv_id {inv_id} does not exist in the inventory')

        count = reservation_data['count']

        if count <= 0:
            abort(400, error='Count must be greater than 0')

        if count > 3:
            abort(400, error='Maximum of three items allowed per reservation')

        # Ensure that the user has not exceeded the maximum reservations per month
        user = reservation_data['Reserved_user']
        current_datetime = datetime.datetime.utcnow()
        current_month_end = current_datetime.replace(
            day=calendar.monthrange(current_datetime.year, current_datetime.month)[1],
            hour=23, minute=59, second=59, microsecond=999999
        )

        # Calculate the Reservation_expiry_date (30 days after the creation date)
        reservation_expiry_date = current_datetime + datetime.timedelta(days=30)

        user_reservations_count = collection.count_documents({
            'Reserved_user': user,
            'Reservation_created_date': {
                '$gte': current_month_end.replace(day=1),
                '$lte': current_month_end
            }
        })

        if user_reservations_count >= 3:
            abort(400, error='Maximum reservations reached for this month')

        new_reservation = {
            'reservation_id': reservation_id,
            'Reserved_user': user,
            'Reserved_user_email': reservation_data['Reserved_user_email'],
            'Reservation_created_date': current_datetime,
            'inv_id': inv_id,
            'inv_type': inv_type,
            'inv_name': inv_name,
            'inv_description': inv_description,
            #'inv_logo': inv_logo,  # Add inv_logo to the reservation
            'inv_blob': inv_blob,  # Add inv_blob to the reservation
            'inv_archieve_status': inv_archieve_status,  # Add inv_archieve_status to the reservation
            'Reservation_status': 'Requested',
            'Reservation_status_comments': 'Waiting for approval',
            'Reservation_expiry_date': reservation_expiry_date,
            'count': count
        }

        if inventory_data:
            logging.debug(f'inventory_item: {inventory_data}')

        result = collection.insert_one(new_reservation)
        if result.inserted_id:
            inserted_id = str(result.inserted_id)
            return {'message': 'Reservation created successfully', '_id': inserted_id}, 201
        else:
            return {'message': 'Reservation creation failed'}, 500


@api.route('/reservation/update/<string:reservation_id>')
class UpdateReservation(Resource):
    @api.doc(description='Update a reservation')
    @api.expect(api.model('UpdateReservation', {
        'Reservation_status': fields.String(description='New status for the reservation'),
        'Reservation_status_comments': fields.String(description='Comments for the status update')
    }))
    def put(self, reservation_id):
        # Find the reservation by reservation_id
        reservation = collection.find_one({'reservation_id': reservation_id})

        if reservation:
            update_data = api.payload
            new_status = update_data.get('Reservation_status')
            new_comments = update_data.get('Reservation_status_comments')

            if new_status:
                # Update the Reservation_status
                reservation['Reservation_status'] = new_status

            if new_comments and reservation['Reservation_status'] != new_status:
                # Update the Reservation_status_comments
                reservation['Reservation_status_comments'] = new_comments

            if new_status or new_comments:
                updated_result = collection.update_one(
                    {'reservation_id': reservation_id},
                    {'$set': {
                        'Reservation_status': reservation['Reservation_status'],
                        'Reservation_status_comments': reservation['Reservation_status_comments']
                    }}
                )

            if updated_result.modified_count > 0:
                return {'message': 'Reservation updated successfully'}, 200
            else:
                return {'message': 'Failed to update reservation'}, 500
        else:
            return {'message': 'Reservation not found'}, 404
        

@api.route('/reservations/update-many')
class UpdateManyReservations(Resource):
    @api.doc(description='Update multiple reservations')
    @api.expect(api.model('UpdateManyReservations', {
        'reservation_ids': fields.List(fields.String, required=True, description='List of reservation IDs to update'),
        'Reservation_status': fields.String(description='New status for the reservations'),
        'Reservation_status_comments': fields.String(description='Comments for the status update')
    }))
    def put(self):
        update_data = api.payload
        reservation_ids = update_data.get('reservation_ids', [])
        new_status = update_data.get('Reservation_status')
        new_comments = update_data.get('Reservation_status_comments')

        if not reservation_ids:
            return {'error': 'No reservation IDs provided for update'}, 400

        try:
            updated_result = collection.update_many(
                {'reservation_id': {'$in': reservation_ids}},
                {'$set': {
                    'Reservation_status': new_status,
                    'Reservation_status_comments': new_comments
                }}
            )

            if updated_result.modified_count > 0:
                return {'message': f'{updated_result.modified_count} reservations updated successfully'}, 200
            else:
                return {'message': 'No reservations updated'}, 404
        except Exception as e:
            return {'error': f'An error occurred while updating reservations: {str(e)}'}, 500



@api.route('/reservation/delete/<string:reservation_id>')
class DeleteReservation(Resource):
    @api.doc(description='Cancel a reservation')
    def delete(self, reservation_id):
        # Find the reservation by reservation_id
        reservation = collection.find_one({'reservation_id': reservation_id})

        if reservation:
            # Perform the cancellation logic
            # You can update the Reservation_status, Reservation_status_comments, and Reservation_expiry_date here
            # For example, set Reservation_status to 'Cancelled', add cancellation comments, update expiry date

            # Update the reservation document
            # Update your cancellation logic here, for example:
            # updated_result = collection.update_one(
            #     {'reservation_id': reservation_id},
            #     {
            #         '$set': {
            #             'Reservation_status': 'Cancelled',
            #             'Reservation_status_comments': 'Reservation has been cancelled',
            #             'Reservation_expiry_date': datetime.datetime.utcnow(),
            #         }
            #     }
            # )

            # Delete the reservation
            result = collection.delete_one({'reservation_id': reservation_id})
            if result.deleted_count > 0:
                return {'message': 'Reservation cancelled successfully'}, 200
            else:
                return {'message': 'Failed to cancel reservation'}, 500
        else:
            return {'message': 'Reservation not found'}, 404

@api.route('/reservations/delete-all')
class DeleteAllReservations(Resource):
    @api.doc(description='Delete all reservation records')
    def delete(self):
        try:
            result = collection.delete_many({})  # Assuming you want to delete all reservation records
            if result.deleted_count > 0:
                return {'message': f'{result.deleted_count} reservation records deleted successfully'}, 200
            else:
                return {'message': 'No reservation records deleted'}, 404
        except Exception as e:
            return {'message': f'Error: {e}'}, 500
        
@api.route('/reservation/view')
class DisplayUploadedCSV(Resource):
    @api.doc(params={'page': 'Page number', 'limit': 'Items per page'})
    def get(self):
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 100))
        total_records = collection.count_documents({})
        if page < 1:
            page = 1
        skip = (page - 1) * limit

        # Set a practical upper limit for the limit parameter
        if limit > 10000:
            limit = 10000

        cursor = collection.find({}, {'_id': 0}).skip(skip).limit(limit)
        data = list(cursor)

        # Convert datetime objects to ISO formatted strings
        for item in data:
            if 'Reservation_created_date' in item:
                item['Reservation_created_date'] = item['Reservation_created_date'].isoformat()
            if 'Reservation_expiry_date' in item:
                item['Reservation_expiry_date'] = item['Reservation_expiry_date'].isoformat()
        return {
            'page': page,
            'limit': limit,
            'total_records': total_records,
            'data': data
        }

@api.route('/reservation/viewall')
class DisplayUploadedCSV(Resource):
    def get(self):
        try:
            # Retrieve all reservations from the database
            cursor = collection.find({}, {'_id': 0})
            data = list(cursor)

            # Convert datetime objects to ISO formatted strings
            for item in data:
                if 'Reservation_created_date' in item:
                    item['Reservation_created_date'] = item['Reservation_created_date'].isoformat()
                if 'Reservation_expiry_date' in item:
                    item['Reservation_expiry_date'] = item['Reservation_expiry_date'].isoformat()

            return {
                'total_records': len(data),
                'data': data
            }
        except Exception as e:
            return {'message': f'Error: {str(e)}'}, 500

def fetch_reservation_data():
    #reservation_api_url = 'http://127.0.0.1:5002/reservation/view'  # Update URL as needed
    reservation_api_url='http://10.20.100.30:5002/reservation/view'
    response = requests.get(reservation_api_url)
    reservation_data = response.json()
    return reservation_data

def fetch_reservation_data():
    #reservation_api_url = 'http://127.0.0.1:5002/reservation/update/'  # Update URL as needed
    reservation_api_url='http://10.20.100.30:5002/reservation/update'
    response = requests.get(reservation_api_url)
    reservation_data = response.json()
    return reservation_data



if __name__ == '__main__':
    #inventory_api_url = 'http://10.20.100.30:5001/inventory/view-all'
    inventory_api_url = 'http://localhost:5001/inventory/view-all'
    response = requests.get(inventory_api_url)

    if response.status_code == 200:
        inventory_data = response.json()
        
        if 'data' in inventory_data:
            inventory_items = inventory_data['data']
            
            for item in inventory_items:
                inv_id = item['inv_id']
                inv_name = item['inv_name']
                inv_description = item.get('inv_description', '')  # Use get() to handle optional fields
                
                # Further processing or integration with your reservation logic
                # For example, you can store the extracted information, make decisions, etc.
                
        else:
            print("No inventory data found in the response.")
    else:
        print("API request failed with status code:", response.status_code)

    #app.run(debug=True,host="10.20.100.30",port=5002)
    app.run(debug=True,port=5002)

