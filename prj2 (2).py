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
from collections import defaultdict
from flask_restx import Namespace, Resource
from confluent_kafka import Producer





# Add the parent directory of prj1 to the Python path
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(parent_dir)

# Configure the logging
logging.basicConfig(level=logging.DEBUG)  # Set the logging level to DEBUG

app = Flask(__name__)
swagger = Swagger(app)
api = Api(app, version='1.0', title='Reservation API', description='API for Reservation Management')
mongo_client = MongoClient('mongodb://localhost:27017/')
db = mongo_client['reservations_db']
collection = db['reservation']
user_reservation_counts=db['usercounts']



reservation_model = api.model('Reservation', {
    'Reserved_user': fields.String(required=True, description='Name of the user making the reservation'),
    'Reserved_user_email':fields.String(required=True,description='Reserverd user email'),
    'inv_id':fields.String(required=True,description='the inventory id'),
    'Reservation_status': fields.String(description='Status of the reservation'),
    'Reservation_status_comments': fields.String(description='Additional comments on the reservation status'),
    #'inv_type': fields.List(fields.String, description='List of reserved items'),
    #'inv_type': fields.String(required=True, description='Inventory Type'),
    #'inv_blob': fields.String(required=True, description='Inventory Blob'),
    #'count': fields.Integer(required=True, description='Count of the items in the reservation'),
    'inv_copies':fields.Integer(required=True, description='Copies of inventory'),
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

# Define the function to reduce inventory copies
def reduce_inventory_copies(inv_id, num_copies_to_reduce):
    # Lookup the inventory record by inv_id in your inventory data
    inventory_record = find_inventory_record_by_id(inv_id)

    if inventory_record is not None:
        inv_copies = inventory_record.get('inv_copies', 0)
        if int(inv_copies) >= num_copies_to_reduce:
            # Reduce the inventory copies by the specified amount
            #inventory_record['inv_copies'] = int(inv_copies) - num_copies_to_reduce
            # Save the updated inventory record back to your data store
            updated_inv_copies = int(inv_copies) - num_copies_to_reduce
            inventory_record['inv_copies'] = updated_inv_copies

            # Save the updated inventory record back to your data store
            save_inventory_record(inventory_record)  # Implement this function

            # Return True to indicate success
            return True
        else:
            # Return False to indicate not enough copies
            return False
    else:
        # Return False to indicate that the record was not found
        return False

def save_inventory_record(inventory_record):
    # Connect to your MongoDB
    client = MongoClient('mongodb://localhost:27017')
    db = client['inventory_db']  # Replace with your actual database name
    collection = db['inventory_items']  # Replace with your actual collection name

    # Update the inventory record in the collection
    collection.update_one({'inv_id': inventory_record['inv_id']}, {'$set': inventory_record})
    
    # Close the MongoDB connection
    client.close()

# Function to find an inventory record by inv_id (you'll need to implement this)
def find_inventory_record_by_id(inv_id):
    # Implement the logic to find an inventory record by inv_id from your data store
    # Return the inventory record if found, or None if not found
    # Example:
    #inventory_data = fetch_inventory_data()  # Fetch your inventory data
    for record in inventory_data['data']:
        if record['inv_id'] == inv_id:
            return record
    return None

# Initialize Kafka producer configuration
producer_config = {
    'bootstrap.servers': 'localhost:9092',  # Replace with your Kafka broker's address
    # Add more configuration as needed (e.g., security settings, serializer settings)
}

# Create Kafka producer instance
kafka_producer = Producer(producer_config)

# Function to send reservation details to a Kafka topic
def send_to_kafka(reservation_data):
    try:
        # Get the reservation details and convert to JSON
        reservation_json = json.dumps(reservation_data)
        
        # Replace 'reservations' with your desired Kafka topic name
        kafka_producer.produce('name', value=reservation_json)
        
        # Flush the producer to ensure all messages are sent
        kafka_producer.flush()

        print("Reservation details sent to Kafka topic 'reservations'")
    except Exception as e:
        print(f"Failed to send reservation details to Kafka: {str(e)}")
user_inv_reservations={}


@api.route('/reservations/create')
class CreateReservation(Resource):
    @api.doc(description='Create a new reservation', body=reservation_model)
    def post(self):
        reservation_data = api.payload
        #inventory_data = fetch_inventory_data()
        # Ensure a unique reservation_id is generated for each reservation
        reservation_id = generate_reservation_id()
        #user_info_url = 'http://localhost:3010/auth-api/current-user'
        #response = requests.get(user_info_url)

        #if response.status_code != 200:
           #abort(500, error=f"Failed to fetch user information. Status code: {response.status_code}")

        #user_data = response.json()

        #Reserved_user = user_data['employee']['generalInfoInfo'].get('legalName')
        #Reserved_user_email = user_data['employee']['generalInfoInfo'].get('email')

        #if Reserved_user is None or Reserved_user_email is None:
            #abort(500, error="Reserved_user or Reserved_user_email not provided in user information")

         
        # Initialize inv_id_set here
        inv_id_set = set()
        inv_copies = reservation_data.get('inv_copies')
        
        logging.debug(f'reservation_data: {reservation_data}')
        logging.debug(f'inventory_data: {inventory_data}')
        logging.debug(f'reservation_id: {reservation_id}')
        logging.debug(f'inv_id_set: {inv_id_set}')

        # Strip leading and trailing whitespace from inv_id
        inv_id = reservation_data['inv_id'].strip()
        inv_description = None
        inv_name = None
        inv_blob = None
        inv_archive_status = None
        requested_copies = None  # Change inv_copies to requested_copies
        inv_type = None  # Initialize inv_type

        for item in inventory_data['data']:
            if item['inv_id'] == inv_id:
                inv_name = item.get('inv_name', '')
                inv_description = item.get('inv_description', '')
                inv_type = item.get('inv_type', '')  # Initialize inv_type here
                inv_blob = item.get('inv_blob', '')
                inv_archive_status = item.get('inv_archive_status', '')
                break

    
        # Log inv_id values before the check
        logging.debug(f'inv_id from reservation_data: {inv_id}')
        logging.debug(f'inv_id from inventory_data: {inv_id_set}')

        # Log inv_description and inv_type here
        logging.debug(f'inv_description: {inv_description}')
        logging.debug(f'inv_type: {inv_type}')
        logging.debug(f'inv_blob: {inv_blob}')
        logging.debug(f'inv_archive_status: {inv_archive_status}')
       

        # Extract required fields from the inventory data
        if 'data' in inventory_data and len(inventory_data['data']) > 0:
            inv_id_set = set(item['inv_id'] for item in inventory_data['data'])
        else:
            abort(500, error='No inventory data available')

        # Verify that inv_id is in inv_id_set
        if inv_id not in inv_id_set:
            abort(400, error=f'inv_id {inv_id} does not exist in the inventory')

        inv_id = request.json['inv_id']
        


        user = reservation_data.get('Reserved_user')
        if user is None:
           abort(400, error='Reserved_user not provided')

        current_datetime = datetime.datetime.utcnow()
        current_month_end = current_datetime.replace(
            day=calendar.monthrange(current_datetime.year, current_datetime.month)[1],
            hour=23, minute=59, second=59, microsecond=999999
        )


        # Calculate the Reservation_expiry_date (30 days after the creation date)
        reservation_expiry_date = current_datetime + datetime.timedelta(days=30)

        # Query the user reservation count for this month
        user_reservation_count_doc = user_reservation_counts.find_one({
            'Reserved_user': user,
            'counts.reservation_month': current_datetime.month
        })

        if user_reservation_count_doc is None:
            # User doesn't exist in the schema for this month, create a new document with count 1
            user_reservation_counts.insert_one({
                'Reserved_user': user,
                'counts': [
                    {
                        'reservation_month': current_datetime.month,
                        'reservation_count': 1,
                        'inv_names': inv_name,
                        'inv_copies': [requested_copies]
                    }
                ]
            })
            user_reservation_count = 1
        else:
            # User exists for this month, get their current count
            current_counts = user_reservation_count_doc.get('counts', [])
            current_count = 0

            # Find the current reservation count for this month
            for count_entry in current_counts:
                if count_entry['reservation_month'] == current_datetime.month:
                    current_count = count_entry['reservation_count']
            
            current_month=datetime.datetime.now().month
            
            
            if current_count >= 3:
                # If the user exceeds the maximum limit of reservations for this month, return an error
                abort(400, error='Maximum 3 reservations allowed per month')
            
            existing_reservation = collection.find_one({
            'Reserved_user': user,
            'inv_id': inv_id
             })

            if existing_reservation:
                return {'message': 'User already has a reservation for the same inv_id'}, 400
            
        
            if inv_copies > 1:
               return {'message': 'You can only reserve 1 copy of the inventory'}, 400

            


            # Add the inv_id and inv_copies to the last count
            for count_entry in current_counts:
                if count_entry['reservation_month'] == current_datetime.month:
                    count_entry_inv_names = count_entry.get('inv_names', [])
                    if not isinstance(count_entry_inv_names, list):
                        count_entry_inv_names = [count_entry_inv_names]
                    count_entry_inv_names.append(inv_name)
                    count_entry['reservation_count'] += 1
                    count_entry['inv_names'] = count_entry_inv_names
                    user_reservation_counts.update_one(
                        {'Reserved_user': user},
                        {'$set': {'counts': current_counts}}
                    )
                    user_reservation_count = count_entry['reservation_count']
                    break
        
        print(f'Reservation data: {reservation_data}')
        print(f'inv_id: {inv_id}')
        print(f'Reducing inventory copies...')

        if reduce_inventory_copies(inv_id, inv_copies):
            print(f'Inventory copies reduced successfully')
        else:
            abort(400, error='Not enough copies available in inventory')


        #if reduce_inventory_copies(inv_id, 1):
            #print(f'Inventory copies reduced successfully')
        new_reservation = {
            'reservation_id': reservation_id,
            'Reserved_user': user,
            'Reserved_user_email': reservation_data['Reserved_user_email'],
            'Reservation_created_date': current_datetime,
            'inv_id': inv_id,
            'inv_type': inv_type,  # Ensure you have this value
            'inv_name': inv_name,
            'inv_description': inv_description,
            'inv_blob': inv_blob,
            'inv_archive_status': inv_archive_status,
            'Reservation_status': 'Reserved',
            'Reservation_status_comments': 'Requesed and approved',
            'Reservation_expiry_date': reservation_expiry_date,
            'inv_copies': inv_copies
           
        }
        print(reservation_data)
        result = collection.insert_one(new_reservation)

        if result.inserted_id:
                inserted_id = str(result.inserted_id)
                success_message = f'Reservation created successfully for {reservation_data["Reserved_user"]}'
                send_to_kafka(reservation_data)
                return {
                'message': success_message,
                '_id': inserted_id,
                'reservation_count': user_reservation_count
            }, 201
       
       
    
   

@api.route('/reservation/update/<string:reservation_id>')
class UpdateReservation(Resource):
    # Note: Make sure to use the correct reference to the 'api' object here
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

                # If the new status indicates a return (e.g., 'Returned'), update inventory copies
                if new_status == 'Returned':
                    returned_inv_id = reservation.get('inv_id')
                    # Increase the inv_copies in the inventory
                    increase_inventory_copies(returned_inv_id)

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

# ... (remaining code)

def increase_inventory_copies(inv_id):
    # Find the inventory item by inv_id and increment the inv_copies count
    inventory_item = find_inventory_record_by_id(inv_id)
    if inventory_item:
        inventory_item['inv_copies'] = inventory_item.get('inv_copies', 0) + 1
        save_inventory_record(inventory_item)

# Rest of your code

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
                for reservation_id in reservation_ids:
                    reservation = collection.find_one({'reservation_id': reservation_id})
                    if reservation:
                        if new_status == 'Returned':
                            returned_inv_id = reservation.get('inv_id')
                            increase_inventory_copies(returned_inv_id)
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
    reservation_api_url = 'http://127.0.0.1:5002/reservation/view'  # Update URL as needed
    #reservation_api_url='http://10.20.100.30:5002/reservation/view'
    response = requests.get(reservation_api_url)
    reservation_data = response.json()
    return reservation_data

def fetch_reservation_data():
    reservation_api_url = 'http://127.0.0.1:5002/reservation/update/'  # Update URL as needed
    #reservation_api_url='http://10.20.100.30:5002/reservation/update'
    response = requests.get(reservation_api_url)
    reservation_data = response.json()
    return reservation_data
"""
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
"""
# Import necessary libraries
"""
# Your existing reservation code
def fetch_inventory_data():
    # Update the URL based on your inventory API endpoint
    inventory_api_url = 'http://localhost:5001/inventory/view-all'

    try:
        # Make a GET request to fetch inventory data
        response = requests.get(inventory_api_url)

        if response.status_code == 200:
            inventory_data = response.json()

            if inventory_data and 'data' in inventory_data:
                inventory_items = inventory_data['data']

                for item in inventory_items:
                    inv_id = item['inv_id']
                    inv_name = item['inv_name']
                    inv_description = item.get('inv_description', '')

                    # Further processing or integration with your reservation logic
                    # For example, you can store the extracted information, make decisions, etc.
            else:
                print("No or invalid inventory data found in the response.")
        else:
            print("API request failed with status code:", response.status_code)

    except Exception as e:
        print(f"An error occurred while fetching inventory data: {e}")

# Your remaining reservation code

# Your remaining reservation code

if __name__ == '__main__':
    # Your main execution logic

    # Call the function to fetch inventory data
    fetch_inventory_data()

    # Perform further processing or integration with your reservation logic
    # For example, you can store the extracted information, make decisions, etc.

    # Any additional code related to the main execution of your reservation script

    # Update the port to 5002
    app.run(debug=True, port=5002)



def fetch_inventory_data():
    #inventory_api_url = 'http://10.20.100.30:5001/inventory/view-all'
    inventory_api_url = 'http://127.0.0.1:5001/inventory/view-all'  # Update URL as needed
    response = requests.get(inventory_api_url)
    inventory_data = response.json()
    return inventory_data
"""


if __name__ == '__main__':
    #inventory_api_url = 'http://10.20.100.30:5001/inventory/view-all'
    inventory_api_url = 'http://127.0.0.1:5001/inventory/view-all'
    response = requests.get(inventory_api_url)
    

    if response.status_code == 200:
        inventory_data = response.json()
        
        if 'data' in inventory_data:
            inventory_items = inventory_data['data']
            
            for item in inventory_items:
                inv_id = item['inv_id']
                inv_name = item['inv_name']
                inv_description = item.get('inv_description', '')  
            
                
        else:
            print("No inventory data found in the response.")
    else:
        print("API request failed with status code:", response.status_code)

    #app.run(debug=True,host="10.20.100.30",port=5002)
    app.run(debug=True,port=5002)


