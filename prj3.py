from flask import Flask, request,Response
from flask_restx import Api, Resource
from pymongo import MongoClient
from flasgger import Swagger
import datetime
import requests
import sys,os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta


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
notification_collection = db['notifications']  

#Fecthing the data from api
from prj1.new import fetch_inventory_data
from prj2.ss import fetch_reservation_data

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


def add_sent_confirmation(email, reservation_id, inv_id):
    notification_collection.insert_one({'email': email, 'reservation_id': reservation_id, 'inv_id': inv_id})

def has_sent_confirmation(email, reservation_id):
    return notification_collection.find_one({'email': email, 'reservation_id': reservation_id}) is not None

@api.route('/notification/create')
class ReservationConfirmation(Resource):
    @api.doc(description='Send reservation confirmation notifications to all users')
    def post(self):
        try:
            # Fetch inventory data
            #inventory_api_url = 'http://127.0.0.1:5001/inventory/view'
            inventory_api_url = 'http://10.20.100.30:5001/inventory/view'
            response_inventory = requests.get(inventory_api_url)

            if response_inventory.status_code == 200:
                inventory_data = response_inventory.json()

                # Fetch reservation data
                #reservation_api_url = 'http://127.0.0.1:5002/reservation/view'
                reservation_api_url='http://10.20.100.30.5002/reservation/view'
                response_reservation = requests.get(reservation_api_url)

                if response_reservation.status_code == 200:
                    reservation_data = response_reservation.json()

                    # Loop through each reservation
                    for reservation in reservation_data['data']:
                        Reserved_user = reservation['Reserved_user']
                        Reserved_user_email = reservation['Reserved_user_email']
                        reservation_id = reservation['reservation_id']
                        inv_id = reservation['inv_id']  # Use the correct field name for inventory ID
                        inv_name = reservation['inv_name']

                        if not has_sent_confirmation(Reserved_user_email, reservation_id):
                           send_reservation_confirmation(Reserved_user_email, Reserved_user, reservation_id, inv_id, inv_name)
                           add_sent_confirmation(Reserved_user_email, reservation_id, inv_id)  # Store the confirmation in the database
                        else:
                           print(f"Confirmation already sent for {Reserved_user_email} and reservation_id {reservation_id}.")

                    return {'message': 'Reservation confirmation notifications sent successfully'}, 200
                else:
                    return {'error': f"Failed to fetch reservation data. Status Code: {response_reservation.status_code}"}, 500
            else:
                return {'error': f"Failed to fetch inventory data. Status Code: {response_inventory.status_code}"}, 500
        except Exception as e:
            return {'error': f'An error occurred: {str(e)}'}, 500

def send_reservation_confirmation(Reserved_user_email, Reserved_user, reservation_id, inv_id, inv_name):
    # Construct the notification content
    email_subject = 'Reservation Confirmation'
    email_body = f"Dear {Reserved_user}, your reservation for {inv_name} (ID: {inv_id}) has been confirmed. Thank you!"  # Use inv_id here

    # Send the email notification using your email sending logic
    send_email(Reserved_user_email, email_subject, email_body)
    
    
def send_due_date_reminder(Reserved_user_email, Reserved_user, reservation_id, inv_id, inv_name, inv_description, Reservation_expiry):
    # Construct the notification content
    email_subject = 'Due Date Reminder'
    email_body = f"Dear {Reserved_user}, your borrowed book '{inv_name}' (ID: {inv_id}) with description '{inv_description}' is due to be returned on {Reservation_expiry}. Please ensure timely return to avoid late fees."

    # Send the email notification using your email sending logic
    send_email(Reserved_user_email, email_subject, email_body)    

def add_sent_reminder(email, reservation_id, inv_id):
    print(f"Adding reminder for {email}, reservation_id {reservation_id}, and inv_id {inv_id} to the database.")
    notification_collection.insert_one({'email': email, 'reservation_id': reservation_id, 'inv_id': inv_id})
    print("Reminder added to the database.")

def has_sent_reminder(email, reservation_id, inv_id):
    reminder_found = notification_collection.find_one({'email': email, 'reservation_id': reservation_id, 'inv_id': inv_id}) is not None
    if reminder_found:
        print(f"Reminder found for {email}, reservation_id {reservation_id}, and inv_id {inv_id}.")
    else:
        print(f"No reminder found for {email}, reservation_id {reservation_id}, and inv_id {inv_id}.")
    return reminder_found

@api.route('/Notifications/due')
class DueDateReminder(Resource):
    @api.doc(description='Send notification')
    def post(self):
        try:
            # Fetch inventory data
            #inventory_api_url = 'http://127.0.0.1:5001/inventory/view'
            inventory_api_url='http://10.20.100.30.5001/inventory/view'
            response_inventory = requests.get(inventory_api_url)

            if response_inventory.status_code == 200:
                inventory_data = response_inventory.json()
                print("Inventory Data:", inventory_data)

                # Fetch reservation data
                #reservation_api_url = 'http://127.0.0.1:5002/reservation/view'
                reservation_api_url='http://10.20.100.30.5002/reservation/view'
                response_reservation = requests.get(reservation_api_url)
                
                if response_reservation.status_code == 200:
                    reservation_data = response_reservation.json()
                    print("Reservation_data", reservation_data)
                    
                    print("Number of reservations:", len(reservation_data['data']))

                    # Loop through each reservation
                    for reservation in reservation_data['data']:
                        print("Processing reservation:", reservation)
                        Reserved_user = reservation['Reserved_user']
                        Reserved_user_email = reservation['Reserved_user_email']
                        reservation_id = reservation['reservation_id']
                        inv_id = int(reservation['inv_id'])
                        reservation_expiry_date_str = reservation['Reservation_expiry_date']
                        reservation_expiry_date = datetime.strptime(reservation_expiry_date_str, '%Y-%m-%dT%H:%M:%S.%f')
                        current_datetime = datetime.utcnow()

                        # Calculate the time difference between reservation expiry and current date
                        time_until_expiry = reservation_expiry_date - current_datetime
                        
                        # Calculate the threshold duration (e.g., 3 days)
                        threshold_duration = timedelta(days=3)
                        time_until_expiry = reservation_expiry_date - datetime.now()
                        print("reservation_expiry_date_str:", reservation_expiry_date_str)
                        print("reservation_expiry_date:", reservation_expiry_date)
                        print("current_datetime:", current_datetime)
                        print("time_until_expiry:", time_until_expiry)
                        
                        
                        
                        if time_until_expiry <= threshold_duration:
                            print(f"time_until_expiry ({time_until_expiry}) is less than or equal to threshold_duration ({threshold_duration})")
                            matching_inventory_item = next((item for item in inventory_data['data'] if item['inv_id'] == inv_id), None)
                            if matching_inventory_item:
                                inv_name = matching_inventory_item['inv_name']
                                inv_description = matching_inventory_item.get('inv_description', '')
                                if not has_sent_reminder(Reserved_user_email, reservation_id, inv_id):
                                    send_due_date_reminder(Reserved_user_email, Reserved_user, reservation_id, inv_id, inv_name, inv_description, reservation_expiry_date)
                                    add_sent_reminder(Reserved_user_email, reservation_id, inv_id)  # Store the reminder in the database
                                else:
                                    
                                    print(f"Reminder already sent for {Reserved_user_email}, reservation_id {reservation_id}, and inv_id {inv_id}.")
                            else:
                                print(f"No matching inventory item found for inv_id: {inv_id}. Not sending reminder.")
                                print(f"Not sending reminder for {Reserved_user_email}. Due date is not within threshold.")
                        else:
                            print(f"time_until_expiry ({time_until_expiry}) is greater than threshold_duration ({threshold_duration})")
                            print(f"Due date for {Reserved_user_email} is not within the threshold.")
                else:
                    print(f"Failed to fetch reservation data. Status Code: {response_reservation.status_code}")
            else:
                print("Failed to fetch inventory data. Status Code:", response_inventory.status_code)

            return {'message': 'Due date reminder notifications sent successfully'}, 200
        except Exception as e:
            return {'error': f'An error occurred: {str(e)}'}, 500
     

        
def add_sent_overdue_notification(email, reservation_id,inv_id):
    notification_collection.insert_one({'email': email, 'reservation_id': reservation_id, 'notification_type': 'overdue','inv_id':inv_id})
    print(f"Adding reminder for {email}, reservation_id {reservation_id}, and inv_id {inv_id} to the database.")

def has_sent_overdue_notification(email, reservation_id):
    return notification_collection.find_one({'email': email, 'reservation_id': reservation_id, 'notification_type': 'overdue','inv_id':inv_id}) is not None
    

@api.route('/Notifications/overdue')
class Overdue_Notification(Resource):
    @api.doc(description='Send overdue book notifications')
    def post(self):
        try:
            # Fetch reservation data
            #reservation_api_url = 'http://127.0.0.1:5002/reservation/view'
            reservation_api_url='http://10.20.100.30.5002/reservation/view'
            response_reservation = requests.get(reservation_api_url)

            if response_reservation.status_code == 200:
                reservation_data = response_reservation.json()
                print(response_reservation.status_code)

                # Loop through each reservation
                for reservation in reservation_data['data']:
                    Reserved_user = reservation['Reserved_user']
                    Reserved_user_email = reservation['Reserved_user_email']
                    reservation_id = reservation['reservation_id']
                    inv_id = int(reservation['inv_id'])
                    Reservation_expiry_date_str = reservation['Reservation_expiry_date']
                    Reservation_expiry_date = datetime.strptime(Reservation_expiry_date_str, '%Y-%m-%dT%H:%M:%S.%f')

                    current_date = datetime.now().date()

                    # Check if the reservation is overdue and not already notified
                    if current_date > Reservation_expiry_date.date() and reservation['Reservation_status'] == 'reserved' and not has_sent_overdue_notification(Reserved_user_email, reservation['inv_id']):
                        inv_id = reservation['inv_id']
                        matching_inventory_item = next((item for item in inventory_data['data'] if item['inv_id'] == inv_id), None)
                        if matching_inventory_item:
                            inv_name = matching_inventory_item['inv_name']
                            overdue_days = (current_date - Reservation_expiry_date.date()).days
                            send_overdue_notification(Reserved_user_email, Reserved_user,reservation_id, inv_id, inv_name, Reservation_expiry_date, overdue_days)
                            add_sent_overdue_notification(Reserved_user_email, reservation['inv_id'],reservation_id)  # Store the overdue notification in the database
                        else:
                            print(f"Not sending overdue notification for {Reserved_user_email}. Inventory item not found.")
                    else:
                        print(f"Not sending overdue notification for {Reserved_user_email}. Reservation not overdue or already notified.")
            else:
                print(f"Failed to fetch reservation data. Status Code: {response_reservation.status_code}")
        except Exception as e:
            return {'error': f'An error occurred: {str(e)}'}, 500

def send_overdue_notification(Reserved_user_email, Reserved_user, inv_id, inv_name, Reservation_expiry_date, overdue_days):
    # Construct the notification content
    email_subject = 'Overdue Book Reminder'
    email_body = f"Dear {Reserved_user}, the book '{inv_name}' (ID: {inv_id}) that you have reserved is overdue by {overdue_days} days. The due date was {Reservation_expiry_date}. Please return the book as soon as possible."

    # Send the email notification using your email sending logic
    send_email(Reserved_user_email, email_subject, email_body)

   
def send_notifications():
    send_reservationconfirmation_resource =ReservationConfirmation()
    send_reservationconfirmation_resource.post()
    
    
    # Due Date Reminders
    due_date_reminder_resource = DueDateReminder()
    due_date_reminder_resource.post()

    # Overdue Notifications
    overdue_notification_resource = Overdue_Notification()
    overdue_notification_resource.post()

    print("Sending notifications...")
   



scheduler = BackgroundScheduler()
scheduler.add_job(
    func=send_notifications,
    trigger=IntervalTrigger(minutes=1),  # Run every hour
    id='notification_job',
    replace_existing=True
)
scheduler.start()



if __name__ == '__main__':
    #inventory_api_url = 'http://127.0.0.1:5001/inventory/view'
    inventory_api_url='http:10.20.100.30:5001/inventory/view'
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
    app.run(debug=True,port=5003)
