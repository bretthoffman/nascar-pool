import streamlit as st
import requests
import json
import os
import time
from datetime import datetime

# Configuration
API_KEY = 'jcMmf5R1TOTQN3DfkyFYhI6mg0HzQC8WLFK49V1y'
DRIVER_LIST_URL = f"https://api.sportradar.com/nascar-ot3/mc/2024/drivers/list.json?api_key={API_KEY}"
RACE_SCHEDULE_URL = f"https://api.sportradar.com/nascar-ot3/mc/2025/races/schedule.json?api_key={API_KEY}"
RACE_RESULTS_URL = f"https://api.sportradar.com/nascar-ot3/mc/2025/races/results.json?api_key={API_KEY}"
DATA_FILE = "nascar_data.json"

headers = {"accept": "application/json"}

# Load persistent data
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"teams": {}}

# Save persistent data
def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

data = load_data()

# Function to handle API requests with retry logic for 429 errors (rate limit exceeded)
def fetch_data_with_retry(url, headers, retries=3, backoff_factor=2):
    for attempt in range(retries):
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 429:
            wait_time = backoff_factor ** attempt
            st.write(f"Rate limit exceeded. Retrying in {wait_time} seconds...")
            time.sleep(wait_time)  # Exponential backoff
        else:
            st.write(f"Error fetching data: {response.status_code}")
            break
    return {}

# Fetch the race schedule
def fetch_race_schedule():
    return fetch_data_with_retry(RACE_SCHEDULE_URL, headers)

# Fetch the driver list
def fetch_driver_list():
    return fetch_data_with_retry(DRIVER_LIST_URL, headers)

# Fetch race results
def fetch_race_results(race_id):
    return fetch_data_with_retry(f"{RACE_RESULTS_URL}?race_id={race_id}", headers)

# Get the next upcoming race
def get_upcoming_race(schedule):
    today = datetime.now()
    upcoming_race = None
    race_status = None
    race_start_date = None

    # Loop through events and races to find the closest race
    for event in schedule.get("events", []):
        for race in event.get("races", []):
            race_date = datetime.strptime(race["scheduled"], "%Y-%m-%dT%H:%M:%S+00:00")
            if race_date.date() == today.date():
                return race, "RACE IN PROGRESS:", race_date  # If the race is today, check if it's in progress
            if race_date > today and (not upcoming_race or race_date < datetime.strptime(upcoming_race["scheduled"], "%Y-%m-%dT%H:%M:%S+00:00")):
                upcoming_race = race  # Select the closest upcoming race
                race_status = "Upcoming Race:"
                race_start_date = race_date

    return upcoming_race, race_status, race_start_date

# Calculate points based on race results and user picks
def calculate_points(results, user_picks):
    driver_positions = {result["driver_id"]: index + 1 for index, result in enumerate(results["races"][0]["results"])}
    points = 0

    for pick in user_picks:
        driver_position = driver_positions.get(pick["driver_id"])
        if driver_position:
            points += (len(driver_positions) - driver_position + 1)
            if driver_position == 1:
                points += 3  # Bonus points for picking the winner

    return points

# Streamlit UI
today_date = datetime.today().strftime("%m/%d/%Y")
st.sidebar.title("Fantasy NASCAR Pool")
st.markdown("<h2 style='font-size: 8px; color: white;'>NASCAR POOL</h2>", unsafe_allow_html=True)
st.text(today_date, help="Today's Date")

# Assign a unique key to the sidebar radio
page = st.sidebar.radio("Navigate", ["Register & Pick", "Leaderboard"], key="sidebar_radio")

# Fetch race schedule here so that it's available for both sections
schedule = fetch_race_schedule()

# Get the upcoming race and its status
upcoming_race, race_status, race_start_date = get_upcoming_race(schedule)

if page == "Register & Pick":
    st.markdown("""
        <style>
            .stApp {
                background-color: rgba(0, 128, 128, 0.2);
                font-family: Arial, sans-serif;
                border-top: 2px solid black;
                border-bottom: 2px solid black;
            }
        </style>
    """, unsafe_allow_html=True)
    
    st.title("Fantasy NASCAR Registration")
    user_choice = st.selectbox("Who are you?", ["New Member"] + list(data["teams"].keys()))
    
    if user_choice != "New Member":
        if upcoming_race:
            st.subheader(race_status)
            st.write(f"{upcoming_race['name']}")
            st.write(f"Scheduled Start: {race_start_date.strftime('%I:%M%p  %m-%d-%Y')}")

        # Driver selection section
        drivers = fetch_driver_list().get("drivers", [])
        driver_names = [d["full_name"] for d in drivers]  # Extract only the driver names
        
        st.subheader("Pick Your Driver for the Next Race")
        pick = st.selectbox("Select Your Driver", driver_names, key="driver_selectbox")  # Show only driver names in dropdown

        if st.button("Submit Pick"):
            if user_choice not in data["teams"]:
                data["teams"][user_choice] = {"score": 0, "picks": []}
            data["teams"][user_choice]["picks"].append(pick)
            save_data(data)
            st.success(f"You picked {pick} for this race!")

elif page == "Leaderboard":
    st.markdown("""
        <style>
            .stApp {
                background-color: black;
                color: white;
            }
            h1, h2, h3, h4, h5, h6, p, .stText {
                color: white !important;
            }
        </style>
    """, unsafe_allow_html=True)
    
    st.title("Leaderboard")
    
    sorted_teams = sorted(data["teams"].items(), key=lambda x: x[1]["score"], reverse=True)
    if sorted_teams:
        highest_score = sorted_teams[0][1]["score"]
    
    for rank, (team, info) in enumerate(sorted_teams, 1):
        crown = " 👑" if info["score"] == highest_score else ""
        last_pick = info["picks"][-1] if info["picks"] else "None"
        st.write(f"{rank}. {team} - {info['score']} points{crown} | Last Pick: {last_pick}")
    
    # Check if race is over and fetch results
    if upcoming_race and race_status == "RACE IN PROGRESS:" and race_start_date < datetime.now():
        if "results" not in upcoming_race:  # Ensures the race has finished before fetching results
            st.write("Race is still in progress, results cannot be fetched yet.")
        else:
            race_results = fetch_race_results(upcoming_race["id"])
            if race_results:
                # Loop through each team and calculate points for their picks
                for team, info in data["teams"].items():
                    user_picks = [{"driver_id": pick["driver_id"]} for pick in info["picks"]]
                    points = calculate_points(race_results, user_picks)
                    data["teams"][team]["score"] += points
                save_data(data)
                st.success("Leaderboard updated with race results!")
    else:
        st.write("Race has not started yet or is still in progress.")
