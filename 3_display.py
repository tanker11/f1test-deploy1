import requests
import time
import pandas as pd
from flask import Flask, jsonify, render_template
from bokeh.plotting import figure, show
from bokeh.palettes import Category20
from bokeh.embed import components
import threading


class MonitorService:
    def __init__(self, slave_url):
        self.slave_url = slave_url
        self.status = "waiting for transform service"  # Initial status
        self.data = pd.DataFrame() #Data loaded from the transform service
        self.data_to_plot = {} #Data in the fromat of plotting example below
        self.numdrivers = 0

        """        data_to_plot = {
                    "events": ["1", "2", "3", "4"],
                    "1": [1, 2, 3, 1],
                    "44": [2, 1, 1, 2],
                    "16": [3, 3, 2, None],  # Padding of missing values with None
                }
                #This data structure is requested by the plot method we cerated as a Proof of Concept earlier
        """

    def check_slave_status(self):
        #Cehck API endpoint for status
        try:
            response = requests.get(f"{self.slave_url}/health", timeout=5)
            response.raise_for_status()
            status = response.json().get("status", "unknown")
            return status == "ready"
        except requests.RequestException as e:
            print(f"Failed to reach transform service: {e}")
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
            self.status = "ready"  # Update status to ready
            self.data = data
            print(f"Transferred {len(data)} rows to the local database.")
        except Exception as e:
            self.status = "error"  # Update status to error
            print(f"Error during data transfer: {e}")

    def format_data(self):
        '''
        Formats the data in the way it needs to feed the plot method
        Example data format is in __init__ method
        
        '''        
        max_event_no = self.data["event_no"].max() #event numbers will be iterated throught to build up the dataset for plot

        lineup = self.data[self.data["event_no"] == 1] #First event lists the starting positions
        #Separation and title for the first block in console log
        print("LINEUP:")
        print(lineup)
        print("*" * 48)
        #Create the first items in the plot dict
        self.data_to_plot["events"] = []
        self.data_to_plot["events"].append("1")

        drivers_list = [] #Create list to track all the drivers even if no event fro the given driver

        for row in lineup.itertuples():
            self.data_to_plot[str(row.driver_number)] = [] #Create empty list
            self.data_to_plot[str(row.driver_number)].append(row.position) #Add starting position to the list
            drivers_list.append(row.driver_number) #Build list of drivers (first row of positions always shows this)

        self.numdrivers = len(drivers_list) #Store number of drivers to handle colors

        for i in range(2, max_event_no + 1): 
            #Iterate through from second up to the end
            self.data_to_plot["events"].append(str(i)) #Append actual event number to event data
            event_subset = self.data[self.data["event_no"] == i] #Select rows those showing the actual event (position changes at the same time)
            for driver in drivers_list: 
                #Iterate through the drivers list
                driverpos = event_subset[event_subset["driver_number"] == driver] #Filter for the actual driver in the list
                if driverpos.empty: 
                    #If the dataframe is empty for the given driver, add the previous position
                    self.data_to_plot[str(driver)].append(self.data_to_plot[str(driver)][-1])
                else: 
                    #Otherwise add the value of the new position
                    found_pos = driverpos["position"].values
                    self.data_to_plot[str(driver)].append(int(found_pos[0]))
            print(event_subset)
            print("*"*48)

    def plot_data(self):
        # Create diagram area
        data = self.data_to_plot
        p = figure(title="Position of drivers", x_axis_label="Overtakes", y_axis_label="Position",
                   x_range=data["events"], y_range=(20, 0), height=500, width=1000)  # y range is the possible positions


        # Add lines
        colors = Category20[self.numdrivers]
        for i, driver in enumerate(data.keys() - {"events"}):
            p.line(data["events"], data[driver], line_width=2, color=colors[i], legend_label=driver)

        # Add details
        p.legend.title = "Driver \nnumbers"
        p.legend.location = "top_left"

        p.xaxis.major_label_text_font_size = "0pt"
        p.yaxis.ticker = list(range(1, len(data) + 1))

        leg = p.legend[0]
        p.add_layout(leg, 'right')

        # Embed Bokeh plot into HTML
        script, div = components(p)
        return render_template("plot.html", bokeh_script=script, bokeh_div=div)

    def run(self):
        # Monitor the slave service and transfer data when ready
        success = False
        print("Starting up")
        while not success:
            time.sleep(1)
            print("Checking loading service status...")
            if self.check_slave_status():
                print("Loading service is ready. Transferring data...")
                self.transfer_data()
                success = True
                self.format_data()

            else:
                print("Loading is not ready. Waiting...")


# Flask app for the /health endpoint
app = Flask(__name__)
monitor_service = MonitorService(slave_url="http://transform2:5001")  # Update URL as needed


@app.route('/health', methods=['GET'])
def health():
    #Return the current status of the Monitor Service
    return jsonify({"status": monitor_service.status})

@app.route('/plot', methods=['GET'])
def plot():
    #Serve the plot request by executing the plot creation
    return monitor_service.plot_data()

if __name__ == "__main__":
    #Start monitoring and run the Flask API
    threading.Thread(target=monitor_service.run, daemon=True).start()
    #Starting Flask
    app.run(host="0.0.0.0", port=5002)
