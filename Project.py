from flask import Flask, request, Blueprint
from flask_restx import Api, Resource, fields, reqparse, abort
from pymongo import MongoClient
from flasgger import Swagger
import csv, os, random, string
from bson.objectid import ObjectId
from bson import json_util
from werkzeug.datastructures import FileStorage
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate
import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

#Intializing Flask app
app = Flask(__name__)
swagger = Swagger(app)
scheduler = BackgroundScheduler()
scheduler.start()

api = Api(app, version='1.0', title='API', description='Library Management Service')

# Connect to the Inventory database
inventory_mongo_client = MongoClient('mongodb://localhost:27017/')
inventory_db = inventory_mongo_client['combinedlms_db']
inventory_collection = inventory_db['lms']

# Connect to the Reservation database
reservation_mongo_client = MongoClient('mongodb://localhost:27017/')
reservation_db = reservation_mongo_client['combinedreservation_db']
reservation_collection = reservation_db['reservations']


#Defining models For inventory
inventory_model = api.model('Inventory', {
    'inv_logo': fields.String(required=True, description='Inventory logo'),
    'inv_id': fields.Integer(required=True, description='Inventory ID'),
    'inv_name': fields.String(required=True, description='Inventory name'),
    'inv_description': fields.String(required=True, description='Inventory description'),
    'inv_type': fields.String(required=True, description='Inventory type'),
    'inv_blob': fields.String(required=True, description='Inventory blob'),
    'inv_archieve_status': fields.Boolean(required=True, description='Inventory archive status')
})


##Defining models For Reservation and notification

reservation_model = api.model('Reservation', {
    'reservation_id': fields.Integer(description='Reservation ID (Primary Key)'),
    'Reserved_user': fields.String(required=True, description='Name of the user making the reservation'),
    'Reservation_created_date': fields.DateTime(required=True, description='Date/Time of reservation creation'),
    'reserved_user_mail': fields.String(description='Email of the reserved user'),
    'inv_id': fields.Integer(required=True,description='inventory id'),
    #'Inv_logo': fields.String(required=True, description='URL of the inventory logo'),
    'inv_name': fields.String(required=True, description='Name of the inventory (URL)'),
    'inv_description': fields.String(required=True, description='Description of the inventory'),
    'Reservation_status': fields.String(required=True, description='Status of the reservation'),
    'Reservation_status_comments': fields.String(description='Additional comments on the reservation status'),
    'Reservation_expiry_date': fields.DateTime(required=True, description='Date/Time of reservation expiry'),
    'Books': fields.List(fields.String, description='List of reserved items')  # Include the contents field
})



#Uploading csv file for inventory
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'csv'

upload_model = api.model('UploadCSV', {
    'file': fields.Raw(required=True, description='CSV File')
})
upload_parser = reqparse.RequestParser()
upload_parser.add_argument('file', location='files', type=FileStorage, required=True)



#uploading csv file for reservation
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'csv'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

upload_model = api.model('UploadCSV', {
    'file': fields.Raw(required=True, description='CSV File')
})

def generate_reservation_id():
    timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    random_suffix = ''.join(random.choices(string.digits, k=4))
    return f'r{timestamp}{random_suffix}'

upload_parser = reqparse.RequestParser()
upload_parser.add_argument('file', location='files', type=FileStorage, required=True)


#Inventory routes CURD Operations

@api.route('/inventory/upload')
class UploadCSV(Resource):
    @api.expect(upload_parser)
    def post(self):
        args = upload_parser.parse_args()
        uploaded_file = args['file']

        try:
            inventory_collection.delete_many({})  # Delete existing data
            data = csv.DictReader(uploaded_file.stream.read().decode('utf-8').splitlines())
            inserted_ids = []
            for row in data:
                row['inv_id'] = int(row['inv_id']) 
                result = inventory_collection.insert_one(row)
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
            
            existing_inventory = inventory_collection.find_one({'inv_id': inv_id})
            if existing_inventory:
                return {'message': 'Inventory record with the same ID already exists'}, 400
            result = inventory_collection.insert_one({
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
        total_records = inventory_collection.count_documents({})
        if page < 1:
            page = 1
        skip = (page - 1) * limit
        cursor = inventory_collection.find({}, {'_id': 0}).skip(skip).limit(limit)
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
        try:
            inv_id = int(inv_id)  # Convert inv_id to integer
        except ValueError:
            return {'error': 'Invalid Inventory ID'}, 400
        record = inventory_collection.find_one({'inv_id': inv_id}, {'_id': 0})
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
        data['inv_id'] = int(inv_id) 
        result = inventory_collection.update_one({'inv_id': int(inv_id)}, {'$set': data})
        #result = collection.update_one({'inv_id': inv_id}, {'$set': data})
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
            inv_id_int = int(inv_id)  # Convert to integer
            record = inventory_collection.find_one({'inv_id': inv_id_int})
            if record is None:
                return {'message': 'Inventory item not found'}, 404
            result = inventory_collection.delete_one({'inv_id': inv_id_int})

            if result.deleted_count > 0:
                return {'message': 'Inventory item deleted successfully'}, 200
            else:
                return {'message': 'Failed to delete inventory item'}, 500

        except ValueError:
            return {'error': 'Invalid Inventory ID format'}, 400
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
            inventory_ids = [int(inv_id) for inv_id in inventory_ids]  # Convert to integers
        except ValueError:
            return {'error': 'Invalid Inventory IDs provided'}, 400

        try:
            result = inventory_collection.delete_many({'inv_id': {'$in': inventory_ids}})
            if result.deleted_count > 0:
                return {'message': f'{result.deleted_count} inventory items deleted successfully'}, 200
            else:
                return {'message': 'No inventory items deleted'}, 404
        except Exception as e:
            return {'message': f'Error: {e}'}, 500
        
        
        
        
def send_email(user_email, email_subject, email_body):
    # Implement your email sending logic here
    msg = MIMEMultipart()
    msg['Subject'] = email_subject
    msg['From'] = 'noreply@library.com'
    msg['To'] = user_email

    body = MIMEText(email_body, 'plain')
    msg.attach(body)

    smtp_server = 'smtp.gmail.com'  # Update with your SMTP server details
    smtp_port = 587
    smtp_username = 'anushahs2112001@gmail.com'  # Replace with your Gmail email address
    smtp_password = 'rikp fpjk zfdm jmsf'  # Replace with your Gmail password or app-specific password

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.sendmail('noreply@library.com', user_email, msg.as_string())
        server.quit()
        print('Email sent successfully!')
    except Exception as e:
        print('An error occurred while sending the email:', str(e))
        



UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'csv'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

upload_model = api.model('UploadCSV', {
    'file': fields.Raw(required=True, description='CSV File')
})

def generate_reservation_id():
    timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    random_suffix = ''.join(random.choices(string.digits, k=4))
    return f'r{timestamp}{random_suffix}'

upload_parser = reqparse.RequestParser()
upload_parser.add_argument('file', location='files', type=FileStorage, required=True)


@api.route('/reservation/upload')
class UploadCSV(Resource):
    @api.expect(upload_parser)
    def post(self):
        args = upload_parser.parse_args()
        uploaded_file = args['file']

        try:
            reservation_collection.delete_many({})  # Delete existing data
            data = csv.DictReader(uploaded_file.stream.read().decode('utf-8').splitlines())
            inserted_ids = []
            for row in data:
                # Convert reservation_id to integer
                row['reservation_id'] = int(row['reservation_id'])
                row['inv_id'] = int(row['inv_id'])
                result = reservation_collection.insert_one(row)
                inserted_ids.append(str(result.inserted_id))
            
            return {'message': 'Data uploaded successfully', 'inserted_ids': inserted_ids}, 200
        except Exception as e:
            return {'error': 'An error occurred while uploading data'}, 500



@api.route('/reservations')
class Reservations(Resource):
    @api.doc(params={'page': 'Page number', 'limit': 'Reservations per page'}, description='View all reservations')
    def get(self):
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 5))

        total_reservations = reservation_collection.count_documents({})

        if page < 1:
            page = 1

        skip = (page - 1) * limit

        reservations = list(reservation_collection.find({}).skip(skip).limit(limit))

        for reservation in reservations:
            reservation['_id'] = str(reservation['_id'])
            #reservation['Reservation_created_date'] = reservation['Reservation_created_date'].isoformat()
            #reservation['Reservation_expiry_date'] = reservation['Reservation_expiry_date'].isoformat()

        return {
            'page': page,
            'limit': limit,
            'total_reservations': total_reservations,
            'reservations': reservations
        }

@api.route('/reservations/<string:reservation_id>')
class Reservation(Resource):
    @api.doc(description='View a reservation by ID')
    def get(self, reservation_id):
        reservation = reservation_collection.find_one({'reservation_id': int(reservation_id)})
        if reservation:
            reservation['_id'] = str(reservation['_id'])
            return {'reservation': reservation} 
        return {'message': 'Reservation not found'}, 404
    
    @api.doc(description='Update a reservation by ID', body=reservation_model)
    def put(self, reservation_id):
        reservation_data = api.payload
        existing_reservation = reservation_collection.find_one({'reservation_id': int(reservation_id)})
        if not existing_reservation:
            return {'message': 'Reservation not found'}, 404
        
        result = reservation_collection.update_one({'reservation_id': int(reservation_id)}, {'$set': reservation_data})
        if result.modified_count == 1:
            return {'message': 'Reservation updated successfully'}
        return {'message': 'Failed to update reservation'}, 500
    
    @api.doc(description='Delete a reservation by ID')
    def delete(self, reservation_id):
        existing_reservation = reservation_collection.find_one({'reservation_id': int(reservation_id)})
        if not existing_reservation:
            return {'message': 'Reservation not found'}, 404
        
        result = reservation_collection.delete_one({'reservation_id': int(reservation_id)})
        if result.deleted_count == 1:
            return {'message': 'Reservation deleted successfully'}
        return {'message': 'Failed to delete reservation'}, 500

@api.route('/reservations/notification/create')
class CreateReservation(Resource):
    @api.doc(description='Create a new reservation', body=reservation_model)
    def post(self):
        reservation_data = api.payload
        reservation_id = reservation_data.get('reservation_id')
        if not reservation_id:
            abort(400, error='reservation_id is required')

         # Check if the reservation_id already exists in the CSV data
        csv_data = reservation_collection.find_one({'reservation_id': reservation_id})
        if csv_data:
            abort(400, error='A reservation with the same reservation_id already exists in the CSV data')

        # Check if the reservation_id already exists in the MongoDB collection
        existing_reservation = reservation_collection.find_one({'reservation_id': reservation_id})
        if existing_reservation:
            abort(400, error='A reservation with the same reservation_id already exists in the MongoDB collection')

        inv_id = reservation_data.get('inv_id')
        if not inv_id:
            abort(400, error='inv_id is required')

        inventory_record = inventory_collection.find_one({'inv_id': inv_id})
        if not inventory_record:
            abort(400, error=f'Inventory with inv_id {inv_id} does not exist')

        user = reservation_data['Reserved_user']
        reserved_user_mail = reservation_data['reserved_user_mail']  
        reservation_created_date = datetime.datetime.strptime(
            reservation_data['Reservation_created_date'], '%Y-%m-%dT%H:%M:%S.%fZ'
        )

        # Check if the user has reached the maximum reservations for this month
        current_month_start = reservation_created_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        current_month_end = current_month_start + datetime.timedelta(days=30)

        user_reservations_count = reservation_collection.count_documents({
            'Reserved_user': user,
            'Reservation_created_date': {
                '$gte': current_month_start,
                '$lt': current_month_end
            }
        })

        if user_reservations_count >= 3:
            abort(400, error='Maximum reservations reached for this month')

        if len(reservation_data['Books']) > 3:
                abort(400, error='Maximum of three Books allowed per reservation')
       

        new_reservation = {
            'reservation_id': reservation_id,
            'Reserved_user': user,
            'reserved_user_mail': reserved_user_mail,
            'Reservation_created_date': reservation_created_date,
            'inv_id': reservation_data['inv_id'],
            #'Inv_logo': reservation_data['Inv_logo'],
            'inv_name': reservation_data['inv_name'],
            'inv_description': reservation_data['inv_description'],
            'Reservation_status': 'Requested',
            'Reservation_status_comments': 'Waiting for approval',
            'Reservation_expiry_date': current_month_end,  # Expiry at the end of the month
            'Books': reservation_data['Books']
        }

        result = reservation_collection.insert_one(new_reservation)
        if result.inserted_id:
            inserted_id = str(result.inserted_id)
           
        # Reservation Confirmation
        reservation_confirmation_subject = "Reservation Confirmation"
        reservation_confirmation_body = f"Dear {user},\n\n" \
            f"Your reservation for {new_reservation['inv_name']} (ID: {reservation_id}) " \
            f"has been successfully created.\n\n" \
            f"Reservation details:\n" \
            f"Inventory: {new_reservation['inv_name']}\n" \
            f"Reservation ID: {reservation_id}\n" \
            f"Inventory ID: {new_reservation['inv_id']}\n" \
            f"Inventory Description: {new_reservation['inv_description']}\n" \
            f"Due Date: {current_month_end}\n" \
            f"Reservation Expiry: {new_reservation['Reservation_expiry_date']}\n\n" \
            f"Thank you for using our reservation service!\n\n" \
            f"Best regards,\nThe Library"

        send_email(reserved_user_mail, reservation_confirmation_subject, reservation_confirmation_body)
        return {'message': 'Reservation created successfully', 'reservation_id': inserted_id}, 201


        
def send_due_date_reminder_email(data):
    reserved_user = data['Reserved_user']
    reserved_user_mail = data['Reserved_user_mail']
    inv_id = data['inv_id']
    inv_name = data['inv_name']
    inv_description = data['inv_description']
    due_date = data['Reservation_expiry_date']
    reminder_date = data['Reminder_date']  # Added reminder_date field
    reservation_expiry = data['Reservation_expiry_date']  # Added reservation_expiry field

    email_subject = f"Due date reminder for {inv_name} (ID: {inv_id})"
    email_body = f"Dear {reserved_user},\n\n" \
                  f"This is a reminder that your reservation for {inv_name} (ID: {inv_id}) is due on {due_date}.\n\n" \
                  f"Resource Details:\n" \
                  f"Inventory ID: {inv_id}\n" \
                  f"Inventory Name: {inv_name}\n" \
                  f"Inventory Description: {inv_description}\n" \
                  f"Due Date: {due_date}\n" \
                  f"Reminder Date: {reminder_date}\n" \
                  f"Reservation Expiry: {reservation_expiry}\n\n" \
                  f"Please return the resource to the library by the due date.\n\n" \
                  f"If you are unable to return the resource by the due date, please contact the library to extend your reservation.\n\n" \
                  f"Thank you,\nThe Library"

    send_email(reserved_user_mail, email_subject, email_body)  
    
def send_overdue_notification_email(data):
    reserved_user = data['Reserved_user']
    reserved_user_mail= data['Reserved_user_mail']
    inv_id = data['inv_id']
    inv_name = data['inv_name']
    due_date = data['Reservation_expiry_date']
    overdue_days = data['Overdue_days']
    
    email_subject = f"Overdue notification for {inv_name} (ID: {inv_id})"
    email_body = f"Dear {reserved_user},\n\n" \
                  f"Your reservation for {inv_name} (ID: {inv_id}) is overdue by {overdue_days} days.\n\n" \
                  f"The due date for the resource is {due_date}.\n\n" \
                  f"Please return the resource to the library as soon as possible.\n\n" \
                  f"If you have already returned the resource, please disregard this email.\n\n" \
                  f"Thank you,\nThe Library"
    
    send_email(reserved_user_mail, email_subject, email_body)
    
    

def check_due_date_reminders():
    current_time = datetime.datetime.now()
    upcoming_due_reservations = reservation_collection.find({
        'Reservation_expiry_date': {'$gt': current_time - datetime.timedelta(days=2)},  # Adjust the timing as needed
        'Reservation_status': 'Borrowed'
    })

    for reservation in upcoming_due_reservations:
        due_date = reservation['Reservation_expiry_date']
        reminder_date = due_date - datetime.timedelta(days=2)  # Adjust the timing as needed

        reminder_data = {
            'Reserved_user': reservation['Reserved_user'],
            'reserved_user_mail': reservation['reserved_user_mail'],
            'inv_id': reservation['inv_id'],
            'inv_name': reservation['inv_name'],
            'inv_description': reservation['inv_description'],
            'Reservation_expiry_date': due_date,
            'Reminder_date': reminder_date,
        }
        send_due_date_reminder_email(reminder_data)

        

def check_overdue_reservations():
    current_time = datetime.datetime.now() 
    overdue_reservations = reservation_collection.find({
        'Reservation_expiry_date': {'$lte': current_time},
        'Reservation_status': 'Requested'  
    })

    for reservation in overdue_reservations:
        overdue_notification_data = {
            'Reserved_user': reservation['Reserved_user'],
            'reserved_user_mail': reservation['reserved_user_mail'],
            'inv_id': reservation['reservation_id'],
            'inv_name': reservation['inv_name'],
            'Reservation_expiry_date': reservation['Reservation_expiry_date'],
            'Overdue_days': (current_time - reservation['Reservation_expiry_date']).days
        }
        send_overdue_notification_email(overdue_notification_data)
     
REMINDER_INTERVAL_DAYS = 14
OVERDUE_INTERVAL_DAYS = 1

def setup_scheduler():
    # Create a job to send reminder notifications every REMINDER_INTERVAL_DAYS days
    reminder_trigger = IntervalTrigger(days=REMINDER_INTERVAL_DAYS)
    scheduler.add_job(check_due_date_reminders, trigger=reminder_trigger)

    # Create a job to send overdue notifications daily
    overdue_trigger = IntervalTrigger(days=OVERDUE_INTERVAL_DAYS)
    scheduler.add_job(check_overdue_reservations, trigger=overdue_trigger)

   
@api.route('/reservations/deletemany')
class DeleteReservations(Resource):
    @api.doc(description='Delete reservation records in bulk')
    @api.expect(api.model('BulkDeleteData', {
        'reservation_ids': fields.List(fields.Integer(required=True, description='List of reservation IDs to delete'))
    }))
    def delete(self):
        data = api.payload
        reservation_ids = data.get('reservation_ids', [])

        if not reservation_ids:
            return {'error': 'No reservation IDs provided for deletion'}, 400

        try:
            result = reservation_collection.delete_many({'reservation_id': {'$in': reservation_ids}})
            if result.deleted_count > 0:
                return {'message': f'{result.deleted_count} reservations deleted successfully'}, 200
            else:
                return {'message': 'No reservations deleted'}, 404
        except Exception as e:
            return {'message': f'Error: {e}'}, 500

        
if __name__ == '__main__':
    setup_scheduler()
    app.run(debug=True)

        



