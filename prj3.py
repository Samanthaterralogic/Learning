from flask import Flask, request,Response,jsonify
from flask_restx import Api, Resource,fields
from pymongo import MongoClient
from flasgger import Swagger
import requests
import sys,os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta
import datetime
import random
import string
import logging
import pymongo


import json
from datetime import date

class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, date):
            return obj.strftime('%Y-%m-%d')
        return super().default(obj)


# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Set the logging level to DEBUG to capture all log messages
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# Create a logger for your module
logger = logging.getLogger(__name__)
'''
def generate_notification_id(identifier='notification'):
    timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    random_suffix = ''.join(random.choices(string.digits, k=4))
    notification_id = f'{identifier}_{timestamp}{random_suffix}'
    
    # Store the notification ID in MongoDB
    notification_id_collection.insert_one({'notification_id': notification_id})
    
    return notification_id
'''
def generate_notification_id(reservation_id):
    timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    random_suffix = ''.join(random.choices(string.digits, k=4))
    notification_id = f'r{reservation_id}_{timestamp}{random_suffix}'
    
    # Store the notification ID in MongoDB (optional, depending on your use case)
    notification_id_collection.insert_one({'notification_id': notification_id, 'reservation_id': reservation_id})
    
    return notification_id


#Add the parent directory
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(parent_dir)
#Intialiazing the app
app = Flask(__name__)
swagger = Swagger(app)
api = Api(app, version='1.0', title='Notification API', description='API for Notification Service')
#connecting to mongodb
mongo_client = MongoClient('mongodb://localhost:27017/')  
db = mongo_client['notification_db']  
confirmation_collection = db['reservation']  
notification_id_collection = db['notification_ids']
due_collection = db['due']
overdue_collection1 = db['overdue']


# Update the notification collection schema to include a 'last_sent_date' field
#notification_collection.create_index([("email", 1), ("reservation_id", 1), ("inv_id", 1)], unique=True)


# Create a data model for notification IDs
notification_id_model = api.model('NotificationID', {
    'notification_id': fields.String(required=True, description='Unique notification ID'),
})

#Fecthing the data from api
from prj1 import fetch_inventory_data
from prj2 import fetch_reservation_data





#Email sending configuration
def send_email(Reserved_user_email, email_subject, email_body):
    msg = MIMEMultipart()
    msg['Subject'] = email_subject
    msg['From'] = 'noreply@library.com'
    msg['To'] = Reserved_user_email

    body = MIMEText(email_body, 'plain')
    msg.attach(body)

    smtp_server = 'smtp.gmail.com'  
    smtp_port = 587
    smtp_username = 'anushahs2112001@gmail.com' 
    smtp_password = 'rikp fpjk zfdm jmsf' 
    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.sendmail('noreply@library.com', Reserved_user_email, msg.as_string())
        server.quit()
        print('Email sent successfully!')
    except Exception as e:
        print('An error occurred while sending the email:', str(e))



def send_reservation_confirmation(Reserved_user_email, Reserved_user, reservation_id, inv_id, inv_name,inv_description):
    
    email_subject = f'Reservation Confirmation for {inv_name}'
    email_body = f"Dear {Reserved_user},\n\n"\
      f"Thank you for your reservation.\n"\
      f"Inventory name:{inv_name}.\n"\
      f"Inventory id : {inv_id}.\n"\
      f"Description: {inv_description}\n"\
      f"Your reservation has been confirmed.\n\n"\
      f"Best regards,\nYour Reservation Team"

    # Send the email notification.
    send_email(Reserved_user_email, email_subject, email_body)
    notification_id = generate_notification_id(reservation_id)
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_message = f"{timestamp}: Sent confirmation email for reservation {reservation_id} to {Reserved_user_email}.\n"

    # Log the unique log message
    logging.info(log_message)
    
# Function to check if a confirmation has been sent
def has_sent_confirmation(email, reservation_id):
    return confirmation_collection.find_one({'email': email, 'reservation_id': reservation_id}) is not None

# Function to record a sent confirmation in MongoDB
def record_confirmation(email, reservation_id):
    confirmation_collection.insert_one({'email': email, 'reservation_id': reservation_id})
    logging.info(f"Recorded confirmation for reservation {reservation_id} sent to {email}.\n")




    

@api.route('/notification/create')
class ReservationConfirmation(Resource):
    @api.doc(description='Send reservation confirmation notifications to all users')
    def post(self):
        try:
            # Fetch reservation data
            reservation_api_url = 'http://10.20.100.30:5002/reservation/view'
            response_reservation = requests.get(reservation_api_url)

            if response_reservation.status_code == 200:
                reservation_data = response_reservation.json()
                
                # Loop through each reservation
                for reservation in reservation_data['data']:
                    Reserved_user_email = reservation['Reserved_user_email']
                    reservation_id = reservation['reservation_id']
                    #notification_id= generate_notification_id()
                    #notification_id = generate_notification_id(reservation_id)
                    # Check if a confirmation has already been sent for this reservation
                    if not has_sent_confirmation(Reserved_user_email, reservation_id):
                        # Send the reservation confirmation
                        send_reservation_confirmation(Reserved_user_email, reservation['Reserved_user'], reservation_id, reservation['inv_id'], reservation['inv_name'], reservation['inv_description'])
                        
                        # Record the sent confirmation in the MongoDB collection
                        record_confirmation(Reserved_user_email, reservation_id)

                return {'message': 'Reservation confirmation notifications sent successfully'}, 200
            else:
                return {'error': f"Failed to fetch reservation data. Status Code: {response_reservation.status_code}"}, 500
        except Exception as e:
            return {'error': f'An error occurred: {str(e)}'}, 500




################################################################################################################



def send_due_date_reminder(Reserved_user_email, Reserved_user, reservation_id, inv_id, inv_name,  Reservation_expiry_date):
    email_subject = f'Due Date Reminder for {inv_name}'
    email_body = f"Dear {Reserved_user}\n"\
                 f"your borrowed book '{inv_name}' for (ID: '{inv_id}')  is due to be returned on '{Reservation_expiry_date}'. Please ensure timely return to avoid late fees.\n"\
                 f"Thank you "
    logger.info(f"Sending due date reminder for reservation ID: {reservation_id} to {Reserved_user_email}")
    logger.debug(f"Email Body:\n{email_body}")
    notification_id = generate_notification_id(reservation_id)

    # Send the email notification using your email sending logic
    # Log after sending the email
    logger.info(f"Sending due date reminder for reservation ID: {reservation_id} to {Reserved_user_email}")
    send_email(Reserved_user_email, email_subject, email_body)
    
    
    
def has_sent_today(email, reservation_id, inv_id, reminder_type):
    # Retrieve the last sent reminder from the MongoDB collection based on the reminder type
    last_sent_reminder = due_collection.find_one(
        {'email': email, 'reservation_id': reservation_id, 'inv_id': inv_id, 'notification_type': 'reminder', 'reminder_type': reminder_type},
        sort=[('_id', pymongo.DESCENDING)]
    )

    if last_sent_reminder:
        # Get the date the last reminder was sent and the threshold date
        last_sent_date = last_sent_reminder.get('sent_date')
        threshold_date = last_sent_reminder.get('threshold_date')
        # Get the current date
        current_datetime = datetime.datetime.utcnow().date()

        if last_sent_date and last_sent_date.date() == current_datetime:
            print(f"{reminder_type} Reminder already sent today for {email}, reservation_id {reservation_id}, and inv_id {inv_id}.")
            return True

        # Check if threshold_date is not None and it's the threshold date (one day before due date)
        if threshold_date and threshold_date.date() == current_datetime:
            print(f"{reminder_type} Reminder sent today for {email}, reservation_id {reservation_id}, and inv_id {inv_id}.")
            return True

    print(f"No {reminder_type} reminder sent today for {email}, reservation_id {reservation_id}, and inv_id {inv_id}.")
    return False


@api.route('/Notifications/due')
class DueDateReminder(Resource):
    @api.doc(description='Send notification')
    def post(self):
        try:
            # Fetch inventory data
            inventory_api_url = 'http://10.20.100.30:5001/inventory/view-all'
            response_inventory = requests.get(inventory_api_url)

            if response_inventory.status_code == 200:
                inventory_data = response_inventory.json()

                # Fetch reservation data
                reservation_api_url = 'http://10.20.100.30:5002/reservation/view'
                response_reservation = requests.get(reservation_api_url)

                if response_reservation.status_code == 200:
                    reservation_data = response_reservation.json()

                    # Loop through each reservation
                    for reservation in reservation_data['data']:
                        Reserved_user = reservation['Reserved_user']
                        Reserved_user_email = reservation['Reserved_user_email']
                        reservation_id = reservation['reservation_id']
                        inv_id = reservation['inv_id']
                        Reservation_expiry_date_str = reservation['Reservation_expiry_date']
                        Reservation_expiry_date = datetime.datetime.strptime(Reservation_expiry_date_str, '%Y-%m-%dT%H:%M:%S.%f')
                        current_datetime = datetime.datetime.utcnow()
                        logging.debug(current_datetime)

                        # Calculate the time difference between reservation expiry and current date
                        time_until_expiry = Reservation_expiry_date - current_datetime
                        logging.debug('time_until_expiry: %s', time_until_expiry)

                        # Calculate the threshold duration (e.g., 1 day)
                        threshold_duration_1 = timedelta(days=1)
                        logging.debug(threshold_duration_1)

                        # Check if it's within 1 day of expiry (tomorrow or earlier)
                        if time_until_expiry <= threshold_duration_1:
                            matching_inventory_item = next((item for item in inventory_data['data'] if item['inv_id'] == inv_id), None)
                            if matching_inventory_item:
                                inv_name = matching_inventory_item['inv_name']
                                inv_description = matching_inventory_item.get('inv_description', '')
                                print(f"Checking reminder for {Reserved_user_email}, reservation_id {reservation_id}, and inv_id {inv_id}.", '\n')

                                # Calculate the reminder date for "day1" (day before or on the day of expiry)
                                reminder_date_day1 = Reservation_expiry_date - threshold_duration_1
                                reminder_id_day1 = f'{Reserved_user_email}_{reservation_id}_{inv_id}_day1'
                                logging.debug(reminder_date_day1)

                                # Calculate the reminder date for "day2" (on the day of expiry)
                                reminder_date_day2 = Reservation_expiry_date
                                reminder_id_day2 = f'{Reserved_user_email}_{reservation_id}_{inv_id}_day2'
                                logging.debug('Reservation_expiry_date: %s', Reservation_expiry_date)
                                logging.debug('threshold_duration_1: %s', threshold_duration_1)
                                logging.debug('reminder_date_day1: %s', reminder_date_day1)

                                # Check if it's the day before or on the day of expiry for "day1"
                                if current_datetime.date() <= reminder_date_day1.date():
                                    # Check if the reminder has not been sent today for "day1"
                                    if not has_sent_today(Reserved_user_email, reservation_id, inv_id, 'day1'):
                                        send_due_date_reminder(Reserved_user_email, Reserved_user, reservation_id, inv_id, inv_name, Reservation_expiry_date)

                                        # Mark the reminder as sent in MongoDB for "day1"
                                        current_date = datetime.datetime.utcnow()
                                        due_collection.insert_one({'_id': reminder_id_day1, 'email': Reserved_user_email, 'reservation_id': reservation_id, 'inv_id': inv_id, 'notification_type': 'reminder', 'sent_date': current_date, 'threshold_date': reminder_date_day1, 'reminder_type': 'day1'})
                                if current_datetime.date() == reminder_date_day2.date():
                                    # Check if the reminder has not been sent today for "day2"
                                    if not has_sent_today(Reserved_user_email, reservation_id, inv_id, 'day2'):
                                        send_due_date_reminder(Reserved_user_email, Reserved_user, reservation_id, inv_id, inv_name, Reservation_expiry_date)

                                        # Mark the reminder as sent in MongoDB for "day2"
                                        current_date = datetime.datetime.utcnow()
                                        due_collection.insert_one({'_id': reminder_id_day2, 'email': Reserved_user_email, 'reservation_id': reservation_id, 'inv_id': inv_id, 'notification_type': 'reminder', 'sent_date': current_date, 'threshold_date': Reservation_expiry_date, 'reminder_type': 'day2'})

                            else:
                                print(f"No matching inventory item found for inv_id: {inv_id}. Not sending reminder.")
                        else:
                            print(f"Due date for {Reserved_user_email} is not within the threshold.")

                    return {'message': 'Due date reminder notifications sent successfully'}, 200
        except Exception as e:
            return {'error': f'An error occurred: {str(e)}'}, 500

 
 #####################################################################################################################################
 
 
 
def send_overdue_notification(Reserved_user_email, Reserved_user, reservation_id, inv_id, inv_name,  Reservation_expiry_date):
    email_subject = f'Overdue Reminder for {inv_name}'
    email_body = f"Dear {Reserved_user}\n"\
                 f"your borrowed book '{inv_name}' for '(ID: {inv_id})'  is overdue. It was due to be returned on '{Reservation_expiry_date}' Please return it as soon as possible to avoid further charges.\n"\
                 f"Thank you "
    logger.info(f"Sending overdue reminder for reservation ID: {reservation_id} to {Reserved_user_email}")
    logger.debug(f"Email Body:\n{email_body}")
    notification_id = generate_notification_id(reservation_id)

    # Send the email notification using your email sending logic
    send_email(Reserved_user_email, email_subject, email_body)
    
def has_sent_overdue_notification(email, reservation_id, inv_id, reminder_type):
    # Retrieve the last sent reminder from the MongoDB collection based on the reminder type
    last_sent_reminder = overdue_collection1.find_one(
        {'email': email, 'reservation_id': reservation_id, 'inv_id': inv_id, 'notification_type': 'overdue', 'reminder_type': reminder_type},
        sort=[('_id', pymongo.DESCENDING)]
    )

    if last_sent_reminder:
        # Get the date the last reminder was sent and the threshold date
        last_sent_date = last_sent_reminder.get('sent_date')
        threshold_date = last_sent_reminder.get('threshold_date')
        # Get the current date
        current_datetime = datetime.datetime.utcnow().date()

        if last_sent_date and last_sent_date.date() == current_datetime:
            print(f"{reminder_type} Overdue Reminder already sent today for {email}, reservation_id {reservation_id}, and inv_id {inv_id}.")
            return True

        # Check if threshold_date is not None and it's the threshold date (daily check)
        if threshold_date and threshold_date.date() == current_datetime:
            print(f"{reminder_type} Overdue Reminder sent today for {email}, reservation_id {reservation_id}, and inv_id {inv_id}.")
            return True

    print(f"No {reminder_type} overdue reminder sent today for {email}, reservation_id {reservation_id}, and inv_id {inv_id}.")
    return False






@api.route('/Notifications/overdue')
class OverdueNotification(Resource):
    @api.doc(description='Send overdue notification reminders')
    def post(self):
        try:
            # Fetch inventory data
            inventory_api_url = 'http://10.20.100.30:5001/inventory/view-all'
            response_inventory = requests.get(inventory_api_url)

            if response_inventory.status_code == 200:
                inventory_data = response_inventory.json()

                # Fetch reservation data
                reservation_api_url = 'http://10.20.100.30:5002/reservation/view'
                response_reservation = requests.get(reservation_api_url)

                if response_reservation.status_code == 200:
                    reservation_data = response_reservation.json()

                    # Loop through each reservation
                    for reservation in reservation_data['data']:
                        Reserved_user = reservation['Reserved_user']
                        Reserved_user_email = reservation['Reserved_user_email']
                        reservation_id = reservation['reservation_id']
                        inv_id = reservation['inv_id']
                        Reservation_expiry_date_str = reservation['Reservation_expiry_date']
                        Reservation_expiry_date = datetime.datetime.strptime(Reservation_expiry_date_str, '%Y-%m-%dT%H:%M:%S.%f')
                        current_datetime = datetime.datetime.utcnow()
                        #notification_id = generate_notification_id(reservation_id)
                        # Calculate the time difference between reservation expiry and current date
                        time_until_expiry = Reservation_expiry_date - current_datetime
                        logging.debug(time_until_expiry)
                        
                        # Calculate the threshold duration (e.g., 1 day and 2 days)
                        threshold_duration = timedelta(days=0)  # Change this threshold as needed for overdue reminders
                        reminder_id_daily = f'{Reserved_user_email}_{reservation_id}_{inv_id}_daily'

                        
                        if time_until_expiry < threshold_duration:
                            matching_inventory_item = next((item for item in inventory_data['data'] if item['inv_id'] == inv_id), None)
                            if matching_inventory_item:
                                inv_name = matching_inventory_item['inv_name']
                                inv_description = matching_inventory_item.get('inv_description', '')
                                print(f"Checking overdue reminder for {Reserved_user_email}, reservation_id {reservation_id}, and inv_id {inv_id}.",'\n')
                                if not has_sent_overdue_notification(Reserved_user_email, reservation_id, inv_id):
                                    send_overdue_notification(Reserved_user_email, Reserved_user, reservation_id, inv_id, inv_name,Reservation_expiry_date)
                                     #Mark the reminder as sent in MongoDB for daily
                                    current_date = datetime.datetime.utcnow()
                                    overdue_collection1.insert_one({'_id': reminder_id_daily, 'email': Reserved_user_email, 'reservation_id': reservation_id, 'inv_id': inv_id, 'notification_type': 'overdue', 'sent_date': current_date, 'threshold_date': current_datetime, 'reminder_type': 'daily'})
                                else:
                                    print(f"Overdue reminder already sent for {Reserved_user_email}, reservation_id {reservation_id}, and inv_id {inv_id}.")
                            else:
                                print(f"No matching inventory item found for inv_id: {inv_id}. Not sending overdue reminder.")
                        else:
                            print(f"Due date for {Reserved_user_email} is not within the threshold for overdue notification.")
                else:
                    print(f"Failed to fetch reservation data. Status Code: {response_reservation.status_code}")
            else:
                print("Failed to fetch inventory data. Status Code:", response_inventory.status_code)

            return {'message': 'Overdue notification reminders sent successfully'}, 200
        except Exception as e:
            return {'error': f'An error occurred: {str(e)}'}, 500
   
def add_sent_overdue_notification(email, reservation_id, inv_id):
    # Check if a document with the same values already exists
    existing_document = overdue_collection1.find_one({'email': email, 'reservation_id': reservation_id, 'inv_id': inv_id, 'notification_type': 'overdue'})
    
    if existing_document:
        print(f"Overdue notification already exists for {email}, reservation_id {reservation_id}, and inv_id {inv_id}.")
        return  # Skip insertion
        
    # If the document doesn't exist, insert it
    print(f"Adding overdue notification for {email}, reservation_id {reservation_id}, and inv_id {inv_id} to the database.")
    overdue_collection1.insert_one({'email': email, 'reservation_id': reservation_id, 'inv_id': inv_id, 'notification_type': 'overdue'})
    print("Overdue notification added to the database.")



def has_sent_overdue_notification(email, reservation_id, inv_id):
    overdue_notification_found = overdue_collection1.find_one({'email': email, 'reservation_id': reservation_id, 'inv_id': inv_id, 'notification_type': 'overdue'}) is not None
    if overdue_notification_found:
        print(f"Overdue notification found for {email}, reservation_id {reservation_id}, and inv_id {inv_id}.")
    else:
        print(f"No overdue notification found for {email}, reservation_id {reservation_id}, and inv_id {inv_id}.")
    return overdue_notification_found



####################################################################################################################






@api.route('/notification/track')
class TrackNotificationIDs(Resource):
    @api.doc(description='Track notification IDs')
    def get(self):
        # Query the MongoDB collection to retrieve all notification IDs
   
        notification_ids = [doc['notification_id'] for doc in notification_id_collection.find()]
        return {'notification_ids': notification_ids}, 200
    
    
    
    
    
@api.route('/delete/<string:notification_id>')
class DeleteNotificationResource(Resource):
    @api.doc(description='Delete a notification by ID')
    def delete(self, notification_id):
        try:
            # Find and remove the notification by ID
            deleted_notification = notification_id_collection.find_one_and_delete({'notification_id': notification_id})
            
            if deleted_notification:
                return {'message': 'Notification deleted successfully'}, 200
            else:
                return {'message': 'Notification not found'}, 404

        except Exception as e:
            return {'message': f'Error: {e}'}, 500
@api.route('/delete-many')
class DeleteManyNotificationsResource(Resource):
    @api.doc(description='Delete multiple notifications by their IDs')
    @api.expect(api.model('BulkDeleteData', {
        'notification_ids': fields.List(fields.String, required=True, description='List of notification IDs to delete')
    }))
    def delete(self):
        data = api.payload
        notification_ids = data.get('notification_ids', [])

        if not notification_ids:
            return {'error': 'No notification IDs provided for deletion'}, 400

        try:
            # Use the $in operator to find and remove notifications by their IDs efficiently
            result = notification_id_collection.delete_many({'notification_id': {'$in': notification_ids}})
            
            # Check the number of deleted documents in the result
            if result.deleted_count > 0:
                return {'message': f'{result.deleted_count} notifications deleted successfully'}, 200
            else:
                return {'message': 'No notifications deleted'}, 404
        except Exception as e:
            return {'message': f'Error: {e}'}, 500
        
        
@api.route('/notification/delete-all')
class DeleteAllNotificationsResource(Resource):
    @api.doc(description='Delete all notification IDs')
    def delete(self):
        try:
            result = notification_id_collection.delete_many({})
            if result.deleted_count > 0:
                return {'message': f'{result.deleted_count} notification IDs deleted successfully'}, 200
            else:
                return {'message': 'No notification IDs deleted'}, 404
        except Exception as e:
            return {'message': f'Error: {e}'}, 500


def send_notifications():
    try:
        # Log when the function starts
        timestamp_before = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        logging.debug(f"Timestamp before send_notifications: {timestamp_before}")
        logging.info("Executing send_notifications function.\n")

        # Call the reservation confirmation API
        send_reservationconfirmation_resource = ReservationConfirmation()
        send_reservationconfirmation_resource.post()
        
        send_duedatereminder_resource =DueDateReminder()
        send_duedatereminder_resource.post()
        
        send_overduedatereminder_resource =OverdueNotification()
        send_overduedatereminder_resource.post()


        # Log when the function finishes
        timestamp_after = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        logging.debug(f"Timestamp after send_notifications: {timestamp_after}")
        logging.debug("After sending reservation confirmation emails.\n")

        # Add other notification logic here if needed

        print("Sending notifications...")
    except Exception as e:
        print(f'An error occurred: {str(e)}')



scheduler = BackgroundScheduler()
scheduler.add_job(
    func=send_notifications,
    trigger=IntervalTrigger(minutes=4),  # Run every hour
    id='notification_job',
    replace_existing=True
)   
scheduler.start()



if __name__ == '__main__':
   
    
    #inventory_api_url = 'http://localhost:5001/inventory/view-all'
    inventory_api_url='http://10.20.100.30.5001/inventory/view-all'
    response = requests.get(inventory_api_url)

    if response.status_code == 200:
        inventory_data = response.json()
        
        if 'data' in inventory_data:
            inventory_items = inventory_data['data']
            
            for item in inventory_items:
                inv_id = item['inv_id']
                inv_name = item['inv_name']
                inv_description = item.get('inv_description')  
        else:
            print("No inventory data found in the response.")
    else:
        print("API request failed with status code:", response.status_code)


# Fetch the reservation api

    #reservation_api_url = 'http://127.0.0.1:5002/reservation/view'
    reservation_api_url='http://10.20.100.30.5002/reservation/view'
    response = requests.get(reservation_api_url)

    if response.status_code == 200:
        reservation_data = response.json()

        if 'data' in reservation_data:
            reservation_items = reservation_data['data']

            for item in reservation_items:
                Reserved_user = item['Reserved_user']
                Reserved_user_email = item ['Reserved_user_email']
                Reservation_status = item['Reservation_status']
                Reservation_created_date= item ['Reservation_created_date']
                Reservation_expiry_date = item['Reservation_expiry_date']
               
        else:
            print("No reservation data found in the response.")
    else:
        print("API request failed with status code:", response.status_code)
    app.run(debug=True,host="10.20.100.30",port=5003)
