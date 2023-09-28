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


logging.basicConfig(
    level=logging.DEBUG,  
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def generate_notification_id(reservation_id):
    timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    random_suffix = ''.join(random.choices(string.digits, k=4))
    notification_id = f'r{reservation_id}_{timestamp}{random_suffix}'
    notification_id_collection.insert_one({'notification_id': notification_id, 'reservation_id': reservation_id})
    return notification_id


parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(parent_dir)
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

notification_id_model = api.model('NotificationID', {
    'notification_id': fields.String(required=True, description='Unique notification ID'),
})


from prj1.prj1 import fetch_inventory_data
from prj2.prj2 import fetch_reservation_data


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
    send_email(Reserved_user_email, email_subject, email_body)
    notification_id = generate_notification_id(reservation_id)
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_message = f"{timestamp}: Sent confirmation email for reservation {reservation_id} to {Reserved_user_email}.\n"
    logging.info(log_message)
    
def has_sent_confirmation(email, reservation_id):
    return confirmation_collection.find_one({'email': email, 'reservation_id': reservation_id}) is not None

def record_confirmation(email, reservation_id):
    confirmation_collection.insert_one({'email': email, 'reservation_id': reservation_id})
    logging.info(f"Recorded confirmation for reservation {reservation_id} sent to {email}.\n")


@api.route('/notification/create')
class ReservationConfirmation(Resource):
    @api.doc(description='Send reservation confirmation notifications to all users')
    def post(self):
        try:
            reservation_api_url = 'http://localhost:5002/reservation/viewall'
            #reservation_api_url='http://10.20.100.30:5002/reservation/viewall'
            response_reservation = requests.get(reservation_api_url)
            if response_reservation.status_code == 200:
                reservation_data = response_reservation.json()
                for reservation in reservation_data['data']:
                    Reserved_user_email = reservation['Reserved_user_email']
                    reservation_id = reservation['reservation_id']
                    if not has_sent_confirmation(Reserved_user_email, reservation_id):
                        send_reservation_confirmation(Reserved_user_email, reservation['Reserved_user'], reservation_id, reservation['inv_id'], reservation['inv_name'], reservation['inv_description'])
                        record_confirmation(Reserved_user_email, reservation_id)
                return {'message': 'Reservation confirmation notifications sent successfully'}, 200
            else:
                return {'error': f"Failed to fetch reservation data. Status Code: {response_reservation.status_code}"}, 500
        except Exception as e:
            return {'error': f'An error occurred: {str(e)}'}, 500


def send_due_date_reminder(Reserved_user_email, Reserved_user, reservation_id, inv_id, inv_name,  Reservation_expiry_date):
    email_subject = f'Due Date Reminder for {inv_name}'
    email_body = f"Dear {Reserved_user}\n"\
                 f"your borrowed book '{inv_name}' for (ID: '{inv_id}')  is due to be returned on '{Reservation_expiry_date}'. Please ensure timely return to avoid late fees.\n"\
                 f"Thank you "
    logger.info(f"Sending due date reminder for reservation ID: {reservation_id} to {Reserved_user_email}")
    logger.debug(f"Email Body:\n{email_body}")
    notification_id = generate_notification_id(reservation_id)
    logger.info(f"Sending due date reminder for reservation ID: {reservation_id} to {Reserved_user_email}")
    send_email(Reserved_user_email, email_subject, email_body)
    
    
    
def has_sent_today(email, reservation_id, inv_id, reminder_type):
    last_sent_reminder = due_collection.find_one(
        {'email': email, 'reservation_id': reservation_id, 'inv_id': inv_id, 'notification_type': 'reminder', 'reminder_type': reminder_type},
        sort=[('_id', pymongo.DESCENDING)]
    )
    if last_sent_reminder:
        last_sent_date = last_sent_reminder.get('sent_date')
        threshold_date = last_sent_reminder.get('threshold_date')
        current_datetime = datetime.datetime.utcnow().date()
        if last_sent_date and last_sent_date.date() == current_datetime:
            print(f"{reminder_type} Reminder already sent today for {email}, reservation_id {reservation_id}, and inv_id {inv_id}.")
            return True

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
            inventory_api_url = 'http://localhost:5001/inventory/view-all'
            #inventory_api_url='http://10.20.100.30.5001/inventory/view-all'
            response_inventory = requests.get(inventory_api_url)

            if response_inventory.status_code == 200:
                inventory_data = response_inventory.json()

                reservation_api_url = 'http://127.0.0.1:5002/reservation/viewall'
                #reservation_api_url='http://10.20.100.30:5002/reservation/viewall'
                response_reservation = requests.get(reservation_api_url)

                if response_reservation.status_code == 200:
                    reservation_data = response_reservation.json()

                    for reservation in reservation_data['data']:
                        Reserved_user = reservation['Reserved_user']
                        Reserved_user_email = reservation['Reserved_user_email']
                        reservation_id = reservation['reservation_id']
                        inv_id = reservation['inv_id']
                        Reservation_expiry_date_str = reservation['Reservation_expiry_date']
                        Reservation_expiry_date = datetime.datetime.strptime(Reservation_expiry_date_str, '%Y-%m-%dT%H:%M:%S.%f')
                        current_datetime = datetime.datetime.utcnow()
                        logging.debug(current_datetime)

                        time_until_expiry = Reservation_expiry_date - current_datetime
                        logging.debug('time_until_expiry: %s', time_until_expiry)

                        threshold_duration_1 = timedelta(days=1)
                        logging.debug(threshold_duration_1)

                        if time_until_expiry <= threshold_duration_1:
                            matching_inventory_item = next((item for item in inventory_data['data'] if item['inv_id'] == inv_id), None)
                            if matching_inventory_item:
                                inv_name = matching_inventory_item['inv_name']
                                inv_description = matching_inventory_item.get('inv_description', '')
                                print(f"Checking reminder for {Reserved_user_email}, reservation_id {reservation_id}, and inv_id {inv_id}.", '\n')
                                reminder_date_day1 = Reservation_expiry_date - threshold_duration_1
                                reminder_id_day1 = f'{Reserved_user_email}_{reservation_id}_{inv_id}_day1'
                                logging.debug(reminder_date_day1)
                                reminder_date_day2 = Reservation_expiry_date
                                reminder_id_day2 = f'{Reserved_user_email}_{reservation_id}_{inv_id}_day2'
                                logging.debug('Reservation_expiry_date: %s', Reservation_expiry_date)
                                logging.debug('threshold_duration_1: %s', threshold_duration_1)
                                logging.debug('reminder_date_day1: %s', reminder_date_day1)
                                if current_datetime.date() <= reminder_date_day1.date():
                                    if not has_sent_today(Reserved_user_email, reservation_id, inv_id, 'day1'):
                                        send_due_date_reminder(Reserved_user_email, Reserved_user, reservation_id, inv_id, inv_name, Reservation_expiry_date)
                                        current_date = datetime.datetime.utcnow()
                                        due_collection.insert_one({'_id': reminder_id_day1, 'email': Reserved_user_email, 'reservation_id': reservation_id, 'inv_id': inv_id, 'notification_type': 'reminder', 'sent_date': current_date, 'threshold_date': reminder_date_day1, 'reminder_type': 'day1'})
                                if current_datetime.date() == reminder_date_day2.date():
                                    if not has_sent_today(Reserved_user_email, reservation_id, inv_id, 'day2'):
                                        send_due_date_reminder(Reserved_user_email, Reserved_user, reservation_id, inv_id, inv_name, Reservation_expiry_date)
                                        current_date = datetime.datetime.utcnow()
                                        due_collection.insert_one({'_id': reminder_id_day2, 'email': Reserved_user_email, 'reservation_id': reservation_id, 'inv_id': inv_id, 'notification_type': 'reminder', 'sent_date': current_date, 'threshold_date': Reservation_expiry_date, 'reminder_type': 'day2'})
                            else:
                                print(f"No matching inventory item found for inv_id: {inv_id}. Not sending reminder.")
                        else:
                            print(f"Due date for {Reserved_user_email} is not within the threshold.")
                    return {'message': 'Due date reminder notifications sent successfully'}, 200
        except Exception as e:
            return {'error': f'An error occurred: {str(e)}'}, 50
 
 
 
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
        last_sent_date = last_sent_reminder.get('sent_date')
        threshold_date = last_sent_reminder.get('threshold_date')
        current_datetime = datetime.datetime.utcnow().date()
        if last_sent_date and last_sent_date.date() == current_datetime:
            print(f"{reminder_type} Overdue Reminder already sent today for {email}, reservation_id {reservation_id}, and inv_id {inv_id}.")
            return True
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
            inventory_api_url = 'http://localhost:5001/inventory/view-all'
            #inventory_api_url='http://10.20.100.30.5001/inventory/view-all'
            response_inventory = requests.get(inventory_api_url)

            if response_inventory.status_code == 200:
                inventory_data = response_inventory.json()
                reservation_api_url = 'http://127.0.0.1:5002/reservation/viewall'
                #reservation_api_url='http://10.20.100.30:5002/reservation/viewall'
                response_reservation = requests.get(reservation_api_url)

                if response_reservation.status_code == 200:
                    reservation_data = response_reservation.json()
                    for reservation in reservation_data['data']:
                        Reserved_user = reservation['Reserved_user']
                        Reserved_user_email = reservation['Reserved_user_email']
                        reservation_id = reservation['reservation_id']
                        inv_id = reservation['inv_id']
                        Reservation_expiry_date_str = reservation['Reservation_expiry_date']
                        Reservation_expiry_date = datetime.datetime.strptime(Reservation_expiry_date_str, '%Y-%m-%dT%H:%M:%S.%f')
                        current_datetime = datetime.datetime.utcnow()
                        time_until_expiry = Reservation_expiry_date - current_datetime
                        logging.debug(time_until_expiry)
                        
                        threshold_duration = timedelta(days=0)  
                        reminder_id_daily = f'{Reserved_user_email}_{reservation_id}_{inv_id}_daily'              
                        if time_until_expiry < threshold_duration:
                            matching_inventory_item = next((item for item in inventory_data['data'] if item['inv_id'] == inv_id), None)
                            if matching_inventory_item:
                                inv_name = matching_inventory_item['inv_name']
                                inv_description = matching_inventory_item.get('inv_description', '')
                                print(f"Checking overdue reminder for {Reserved_user_email}, reservation_id {reservation_id}, and inv_id {inv_id}.",'\n')
                                if not has_sent_overdue_notification(Reserved_user_email, reservation_id, inv_id):
                                    send_overdue_notification(Reserved_user_email, Reserved_user, reservation_id, inv_id, inv_name,Reservation_expiry_date)
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
    existing_document = overdue_collection1.find_one({'email': email, 'reservation_id': reservation_id, 'inv_id': inv_id, 'notification_type': 'overdue'})
    
    if existing_document:
        print(f"Overdue notification already exists for {email}, reservation_id {reservation_id}, and inv_id {inv_id}.")
        return       
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


@api.route('/notification/track')
class TrackNotificationIDs(Resource):
    @api.doc(description='Track notification IDs')
    def get(self):
        notification_ids = [doc['notification_id'] for doc in notification_id_collection.find()]
        return {'notification_ids': notification_ids}, 200
    
    
@api.route('/delete/<string:notification_id>')
class DeleteNotificationResource(Resource):
    @api.doc(description='Delete a notification by ID')
    def delete(self, notification_id):
        try:
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
            result = notification_id_collection.delete_many({'notification_id': {'$in': notification_ids}})
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
        timestamp_before = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        logging.debug(f"Timestamp before send_notifications: {timestamp_before}")
        logging.info("Executing send_notifications function.\n")
        send_reservationconfirmation_resource = ReservationConfirmation()
        send_reservationconfirmation_resource.post()
        send_duedatereminder_resource =DueDateReminder()
        send_duedatereminder_resource.post()
        send_overduedatereminder_resource =OverdueNotification()
        send_overduedatereminder_resource.post()

        timestamp_after = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        logging.debug(f"Timestamp after send_notifications: {timestamp_after}")
        logging.debug("After sending reservation confirmation emails.\n")
        print("Sending notifications...")
    except Exception as e:
        print(f'An error occurred: {str(e)}')



scheduler = BackgroundScheduler()
scheduler.add_job(
    func=send_notifications,
    trigger=IntervalTrigger(minutes=4),
    id='notification_job',
    replace_existing=True
)   
scheduler.start()

if __name__ == '__main__':
    inventory_api_url = 'http://localhost:5001/inventory/view-all'
    #inventory_api_url='http://10.20.100.30.5001/inventory/view-all'
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
        
    reservation_api_url = 'http://127.0.0.1:5002/reservation/viewall'
    #reservation_api_url='http://10.20.100.30.5002/reservation/viewall'
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
    #app.run(debug=True,host="10.20.100.30",port=5003)
    app.run(debug=True,port=5003)
