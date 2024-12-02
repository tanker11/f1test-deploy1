import sqlite3
import requests
import time
import pandas as pd
from flask import Flask, jsonify
import threading

class LoadService:
    '''
    Handles db and tables creation
    '''
    def __init__(self, slave_url, local_db_name="/app/db/transformdata.db"):
        self.slave_url = slave_url
        self.local_db_name = local_db_name
        self.status = "waiting for loading service"  # Initial status
        self.init_db()

    def init_db(self):
        #Initialize the local SQLite database
        with sqlite3.connect(self.local_db_name) as conn:
            cursor = conn.cursor()
            #Create table for transferred data
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS session_data (
                    location TEXT,
                    session_name TEXT,
                    meeting_key INTEGER,
                    session_key INTEGER,
                    driver_number INTEGER,
                    position INTEGER,
                    datetime DATETIME
                   
                )
            ''')
            conn.commit()

    def check_slave_status(self):
        #Cehck API endpoint for status
        try:
            response = requests.get(f"{self.slave_url}/health", timeout=5)
            response.raise_for_status()
            status = response.json().get("status", "unknown")
            return status == "ready"
        except requests.RequestException as e:
            print(f"Failed to reach loading service: {e}")
            return False

    def transfer_data(self):
        #Fetch data from /data API endpoint from slave service
        api_endpoint = f"{self.slave_url}/data"
        try:
            response = requests.get(api_endpoint, timeout=10)
            response.raise_for_status()

            # Parse the data as a DataFrame
            data = pd.DataFrame(response.json())
            if data.empty:
                print("No data returned from slave API.")
                return

            # Write data to local SQLite database
            with sqlite3.connect(self.local_db_name) as local_conn:
                data.to_sql('session_data', local_conn, if_exists='replace', index=False)

            self.status = "ready"  # Update status to ready
            print(f"Transferred {len(data)} rows to the local database.")
        except Exception as e:
            self.status = "error"  # Update status to error
            print(f"Error during data transfer: {e}")




    def run(self):
        #Monitor the slave service and transfer data when ready
        success = False
        print("Starting up")
        while not success:
            time.sleep(5)
            print("Checking loading service status...")
            if self.check_slave_status():
                print("Loading service is ready. Transferring data...")
                self.transfer_data()
                success = True
            else:
                print("Loading is not ready. Waiting...")

    def internal_query(self):

        '''
        Query for the data requested on /data endpoint from the internal database tables
        '''

        query = '''
            SELECT location, driver_number, position,
                DENSE_RANK() OVER(ORDER BY datetime ASC) AS event_no
            FROM session_data
            WHERE session_name='Race' AND location='Melbourne'
        '''
        try:
            with sqlite3.connect(self.local_db_name) as conn:
                cursor = conn.cursor()
                cursor.execute(query)
                rows = cursor.fetchall()

            # Convert data to list of dictionaries
            data = [
                {"location": row[0], "driver_number": row[1], "position": row[2], "event_no": row[3]}
                for row in rows
            ]
            return jsonify(data)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

app = Flask(__name__)
service = LoadService(slave_url="http://apiload1:5000") 


@app.route('/health', methods=['GET'])
def health():
    #Return the current status of the Monitor Service
    return jsonify({"status": service.status})

@app.route('/data', methods=['GET'])
def get_data():
    #Fetch data from the SQLite database.
    return service.internal_query()

if __name__ == "__main__":
    #Starting background task
    threading.Thread(target=service.run, daemon=True).start()
    #Starting Flask
    app.run(host="0.0.0.0", port=5001)


