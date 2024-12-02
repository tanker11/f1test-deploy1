import sqlite3
import pandas as pd
import json
import time
from urllib.request import urlopen
from flask import Flask, jsonify
import threading
import os
import logging

class LoadService:
    '''
    Handles db and table creation
    '''
    def __init__(self, loggervar, db_name="/home/loaddata.db"):
        #Logger needed for console logs in the cloud
        logging.basicConfig(level=logging.INFO)
        self.logger = loggervar
        self.db_name = db_name
        self.status = "init"  # Inicializált állapot
        self.init_db()

    def init_db(self):
        #Initialize the local SQLite database
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                # Tables: meetings, sessions, positions, weather
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS meetings (
                        id INTEGER PRIMARY KEY,
                        meeting_key TEXT,
                        meeting_name TEXT,
                        date TEXT,
                        location TEXT
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS sessions (
                        id INTEGER PRIMARY KEY,
                        session_key TEXT,
                        session_name TEXT,
                        meeting_key TEXT,
                        date TEXT,
                        FOREIGN KEY (meeting_key) REFERENCES meetings(meeting_key)
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS positions (
                        id INTEGER PRIMARY KEY,
                        session_key TEXT,
                        driver TEXT,
                        position INTEGER,
                        time TEXT,
                        FOREIGN KEY (session_key) REFERENCES sessions(session_key)
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS weather (
                        id INTEGER PRIMARY KEY,
                        meeting_key TEXT,
                        temperature TEXT,
                        condition TEXT,
                        date TEXT,
                        FOREIGN KEY (meeting_key) REFERENCES meetings(meeting_key)
                    )
                ''')
                conn.commit()
            self.logger.info("Database initialized.")
            self.logger.info(f"Database path: {os.path.abspath(self.db_name)}")
        except Exception as e:
            self.status = "error"
            self.logger.info(f"Error initializing database: {e}")
            raise

    def fetch_and_store(self):
        '''
        Handles API access to the data tables and iterates through sessions if needed
        '''
        self.status = "loading"  # Set actual state of the service
        try:
            # Accessing meeting (weekend) list
            self.logger.info('Accessing meeting list...')
            response = urlopen('https://api.openf1.org/v1/meetings?year=2023')
            mtg_data = json.loads(response.read().decode('utf-8'))
            mtg_df = pd.DataFrame(mtg_data)

            # Storing meeting in database
            with sqlite3.connect(self.db_name) as conn:
                mtg_df.to_sql('meetings', conn, if_exists='replace', index=False)
            self.logger.info(f'{len(mtg_df)} meetings stored.')

            time.sleep(1) # Access frequency limit

            # Empty dataframes for Session and Position data
            session_df = pd.DataFrame()
            position_df = pd.DataFrame()

            # Accessing Session and Position data based on meeting_key
            for meeting in mtg_data:
                self.logger.info(f"Fetching {meeting['meeting_name']} session data...")
                response = urlopen(f"https://api.openf1.org/v1/sessions?meeting_key={meeting['meeting_key']}")
                session_data = json.loads(response.read().decode('utf-8'))
                session_actual = pd.DataFrame(session_data)
                session_df = pd.concat([session_df, session_actual], ignore_index=True)

                for session in session_data:
                    '''
                    Iterates through all sessions to get all positions
                    '''
                    self.logger.info(f"    {session['session_key']} position details...")
                    position_details = urlopen(f"https://api.openf1.org/v1/position?session_key={session['session_key']}")
                    position_data = json.loads(position_details.read().decode('utf-8'))
                    position_actual = pd.DataFrame(position_data)
                    position_df = pd.concat([position_df, position_actual], ignore_index=True)
                    time.sleep(0.3)

            # Storing session és position in database
            with sqlite3.connect(self.db_name) as conn:
                session_df.to_sql('sessions', conn, if_exists='replace', index=False)
                position_df.to_sql('positions', conn, if_exists='replace', index=False)

            time.sleep(1) # Access frequency limit

            # Accessing Weather data
            weather_df = pd.DataFrame()
            for meeting in mtg_data:
                self.logger.info(f"Fetching {meeting['meeting_name']} weather data...")
                response = urlopen(f"https://api.openf1.org/v1/weather?meeting_key={meeting['meeting_key']}")
                weather_data = json.loads(response.read().decode('utf-8'))
                weather_actual = pd.DataFrame(weather_data)
                weather_df = pd.concat([weather_df, weather_actual], ignore_index=True)

            # Storing Weather in database
            with sqlite3.connect(self.db_name) as conn:
                weather_df.to_sql('weather', conn, if_exists='replace', index=False)

            self.logger.info("All data successfully fetched and stored.")
            self.status = "ready"  # Update status to ready

        except Exception as e:
            self.status = "error"  # Update status to error
            self.logger.info(f"Error fetching or storing data: {e}")
            raise
    def internal_query(self):
        '''
        Query for the data requested on /data endpoint from the internal database tables
        '''

        query = '''
            SELECT m.location, s.session_name, m.meeting_key, s.session_key, p.driver_number, p.position, p.date
            FROM meetings m
            JOIN sessions s
            ON s.meeting_key=m.meeting_key
            JOIN positions p
            ON p.session_key=s.session_key
        '''
        try:
            # Access rows in internal database
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute(query)
                rows = cursor.fetchall()

            # Convert data to list of dictionaries
            data = [
                {"location": row[0], "session_name": row[1], "meeting_key": row[2], "session_key": row[3], "driver_number": row[4], "position": row[5], "datetime": row[6]}
                for row in rows
            ]
            return jsonify(data)
        except Exception as e:
            #Show if any error
            return jsonify({"error": str(e)}), 500

logging.basicConfig(level=logging.INFO)
mylogger = logging.getLogger(__name__)
app = Flask(__name__)
service = LoadService(mylogger)

@app.route('/health', methods=['GET'])
def health_check():
    #API endpoint for status check
    return jsonify({"status": service.status})

@app.route('/data', methods=['GET'])
def get_data():
    #API endpoint for fetching data from the internal SQLite database
    return service.internal_query()

def background_task():
    #Background task to fetch and store data
    try:
        service.fetch_and_store()
    except Exception as e:
        mylogger.info(f"Background task error: {e}")

if __name__ == "__main__":
    #Starting background task
    threading.Thread(target=background_task, daemon=True).start()
    
    #Getting port info from environmental variable, run the app with that
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
