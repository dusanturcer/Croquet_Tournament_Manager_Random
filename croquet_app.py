import streamlit as st
import pandas as pd
import sqlite3
import random
import itertools
import csv
import os
# from openpyxl import load_workbook # Not used in a clean version of export_to_excel
# from openpyxl.styles import Alignment # Not used in a clean version of export_to_excel
from datetime import datetime

# --- Player and Match Classes ---

class Player:
    def __init__(self, id, name):
        self.id = id
        self.name = name
        self.points = 0  # Points from wins (1 per win, 0 for bye/draw)
        self.wins = 0  # Number of wins
        self.hoops_scored = 0  # Total hoops scored
        self.hoops_conceded = 0  # Total hoops conceded
        self.opponents = set() # Store opponent IDs

    def add_opponent(self, opponent_id):
        self.opponents.add(opponent_id)

    def __repr__(self):
        return (f"Player(id={self.id}, name={self.name}, points={self.points}, "
                f"wins={self.wins}, hoops_scored={self.hoops_scored}, "
                f"hoops_conceded={self.hoops_conceded})")

class Match:
    def __init__(self, player1, player2):
        self.player1 = player1
        self.player2 = player2
        self.result = None  # (hoops1, hoops2)

    def set_result(self, hoops1, hoops2):
        # Ensure integer conversion for safety
        hoops1, hoops2 = int(hoops1), int(hoops2)
        
        # Bye Handling: A bye gets 1 win point but 0 to hoops
        if self.player2 is None:
            self.result = (hoops1, hoops2) # Still store result, but won't be used for player stats
            self.player1.points += 1 # Swiss rules often grant 1 point for a bye
            self.player1.wins += 1
            return
            
        # Update player stats
        self.player1.hoops_scored += hoops1
        self.player1.hoops_conceded += hoops2
        self.player2.hoops_scored += hoops2
        self.player2.hoops_conceded += hoops1

        # Determine winner
        if hoops1 > hoops2:
            self.player1.wins += 1
            self.player1.points += 1
        elif hoops2 > hoops1:
            self.player2.wins += 1
            self.player2.points += 1
        # Draw: 0 points/wins to both
        
        self.result = (hoops1, hoops2)

    def get_scores(self):
        return self.result if self.result else (0, 0)

    def __repr__(self):
        return f"Match({self.player1.name} vs {self.player2.name if self.player2 else 'BYE'}, result={self.result})"

# --- Swiss Tournament Logic ---

class SwissTournament:
    def __init__(self, players, num_rounds):
        self.players = [Player(i, name) for i, name in enumerate(players)]
        self.num_rounds = num_rounds
        self.rounds = []
        # Swiss tournaments pair round-by-round based on current standings.
        # Initial pairing is typically random/seeded. Subsequent pairings are based on points.
        # The original code's generate_all_pairings was a poor attempt at this.
        # We will now use a pairing method that can be called per round.
        self.generate_round_pairings(0, initial=True)
        # We pre-generate all rounds only for the *initial* pairing, which is common in simple implementations.
        # A proper Swiss system regenerates pairings on the fly after results.
        # For simplicity, we keep the original structure but fix the initial logic.
        for round_num in range(1, self.num_rounds):
            self.generate_round_pairings(round_num)

    def generate_round_pairings(self, round_num, initial=False):
        if len(self.rounds) <= round_num:
            self.rounds.append([])
        
        round_pairings = []
        
        # Sort players by current standing (or randomly for the initial round)
        if initial:
            available_players = self.players.copy()
            random.shuffle(available_players) # Initial random shuffle
        else:
            available_players = self.get_standings() # Sort by points, net hoops, etc.
        
        used_players = set()
        
        # Simple greedy pairing logic
        for i in range(len(available_players)):
            p1 = available_players[i]
            if p1.id in used_players:
                continue
            
            # Find the highest-ranked available opponent p2 who hasn't been played
            best_p2 = None
            for j in range(i + 1, len(available_players)):
                p2 = available_players[j]
                if p2.id not in used_players and p2.id not in p1.opponents:
                    best_p2 = p2
                    break # Found best available opponent
            
            if best_p2:
                round_pairings.append(Match(p1, best_p2))
                used_players.add(p1.id)
                used_players.add(best_p2.id)
                p1.add_opponent(best_p2.id)
                best_p2.add_opponent(p1.id)
            
        # Handle remaining players (odd number or couldn't pair)
        remaining_players = [p for p in available_players if p.id not in used_players]
        if remaining_players:
            # The lowest-ranked player who hasn't had a bye should receive it.
            # Simple version: just take the first remaining player after sorting.
            bye_player = remaining_players[0]
            round_pairings.append(Match(bye_player, None))
            # The set_result method for a Match handles the player stats for a BYE
        
        self.rounds[round_num] = round_pairings
        
        if len(used_players) < len(self.players) and not remaining_players:
            # This is a critical warning, means some players couldn't be paired
            st.warning(f"Warning: Not all players paired in round {round_num + 1} due to opponent restrictions.")

    def record_result(self, round_num, match_num, hoops1, hoops2):
        if 0 <= round_num < len(self.rounds) and 0 <= match_num < len(self.rounds[round_num]):
            match = self.rounds[round_num][match_num]
            
            # Reset previous results for *this* match only
            old_hoops1, old_hoops2 = match.get_scores()
            p1, p2 = match.player1, match.player2
            
            # Reset only if there was a previous result
            if match.result is not None:
                # BYE handling
                if p2 is None:
                    p1.points -= 1
                    p1.wins -= 1
                else:
                    # Reset hoops stats
                    p1.hoops_scored -= old_hoops1
                    p1.hoops_conceded -= old_hoops2
                    p2.hoops_scored -= old_hoops2
                    p2.hoops_conceded -= old_hoops1
                    
                    # Reset points/wins
                    if old_hoops1 > old_hoops2:
                        p1.wins -= 1
                        p1.points -= 1
                    elif old_hoops2 > old_hoops1:
                        p2.wins -= 1
                        p2.points -= 1
            
            # Set new results
            match.set_result(hoops1, hoops2)
            
            # IMPORTANT FIX: Re-pair remaining rounds after a result is changed
            # This is the core of a dynamic Swiss tournament, but complex. 
            # For simplicity, we only re-pair the *next* round if the current round's results change
            if round_num + 1 < self.num_rounds:
                 self.generate_round_pairings(round_num + 1)
        else:
            st.error(f"Invalid round_num {round_num} or match_num {match_num}")

    def get_standings(self):
        # Tie-breakers: 1. Wins (Points), 2. Net Hoops, 3. Hoops Scored
        # The original key used p.wins for points, which is correct for this simple 1-point system.
        return sorted(self.players, key=lambda p: (p.points, p.hoops_scored - p.hoops_conceded, p.hoops_scored), reverse=True)

    def get_round_pairings(self, round_num):
        if 0 <= round_num < len(self.rounds):
            return self.rounds[round_num]
        return []

    def __repr__(self):
        return f"SwissTournament(players={len(self.players)}, rounds={self.num_rounds})"

# --- Database Functions ---

def init_db(db_path='tournament.db'):
    # IMPORTANT FIX: Do not close connection here. It should be passed to other functions.
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS tournaments
                 (id INTEGER PRIMARY KEY, name TEXT, date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS players
                 (tournament_id INTEGER, player_id INTEGER, name TEXT, points INTEGER, wins INTEGER,
                  hoops_scored INTEGER, hoops_conceded INTEGER,
                  PRIMARY KEY (tournament_id, player_id),
                  FOREIGN KEY (tournament_id) REFERENCES tournaments(id))''') # Added FK
    c.execute('''CREATE TABLE IF NOT EXISTS matches
                 (tournament_id INTEGER, round_num INTEGER, match_num INTEGER,
                  player1_id INTEGER, player2_id INTEGER, hoops1 INTEGER, hoops2 INTEGER)''')
    conn.commit()
    return conn

def save_to_db(tournament, tournament_name, conn):
    # FIX: Removed conn.close() from this function, allowing main() to handle it.
    try:
        c = conn.cursor()
        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Check if tournament with this name and structure exists, maybe update instead of insert.
        # For simplicity, we stick to INSERT for new records per save.
        c.execute("INSERT INTO tournaments (name, date) VALUES (?, ?)", (tournament_name, date))
        tournament_id = c.lastrowid

        player_data = [(tournament_id, p.id, p.name, p.points, p.wins, p.hoops_scored, p.hoops_conceded) for p in tournament.players]
        c.executemany("INSERT INTO players (tournament_id, player_id, name, points, wins, hoops_scored, hoops_conceded) VALUES (?, ?, ?, ?, ?, ?, ?)", player_data)

        match_data = []
        for round_num, round_pairings in enumerate(tournament.rounds):
            for match_num, match in enumerate(round_pairings):
                hoops1, hoops2 = match.get_scores()
                player2_id = match.player2.id if match.player2 else -1 # Use -1 for BYE player ID
                match_data.append((tournament_id, round_num, match_num, match.player1.id, player2_id, hoops1, hoops2))
        
        c.executemany("INSERT INTO matches (tournament_id, round_num, match_num, player1_id, player2_id, hoops1, hoops2) VALUES (?, ?, ?, ?, ?, ?, ?)", match_data)

        conn.commit()
    except sqlite3.Error as e:
        st.error(f"Database error on save: {e}")
        conn.rollback() # Rollback on error

# --- Export Functions ---

# Export to CSV/Excel functions are generally OK, cleanup of temp file needs to be robust

# --- Streamlit UI and Logic ---

# FIX: Refactored number_input_with_buttons to handle Streamlit session state correctly 
# to avoid infinite loop issues when updating state inside a button/input context.
def number_input_with_buttons(label, key, value=0, min_value=0, max_value=26, step=1):
    # Use a direct session state key for the value
    temp_key = f"{key}_temp"

    # Initialize session state for this key if not set or if tournament was just created (reset)
    if temp_key not in st.session_state:
        st.session_state[temp_key] = int(value)

    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col1:
        if st.button("−", key=f"minus_{key}"):
            st.session_state[temp_key] = max(min_value, st.session_state[temp_key] - step)
            st.experimental_rerun() # Rerun to update input value immediately

    with col2:
        # Use st.session_state[temp_key] directly as the value
        st.session_state[temp_key] = st.number_input(
            label,
            min_value=min_value,
            max_value=max_value,
            value=st.session_state[temp_key],
            step=step,
            format="%d",
            key=f"{key}_input" # Unique key for number_input
        )
        
    with col3:
        if st.button("+", key=f"plus_{key}"):
            st.session_state[temp_key] = min(max_value, st.session_state[temp_key] + step)
            st.experimental_rerun() # Rerun to update input value immediately
    
    return int(st.session_state[temp_key])

def main():
    st.title("Croquet Tournament Manager 🏏")

    # Initialize session state
    if 'tournament' not in st.session_state:
        st.session_state.tournament = None
        st.session_state.tournament_name = "New Tournament"
        st.session_state.players = []
        st.session_state.num_rounds = 3

    # --- Tournament Setup ---
    with st.expander("Create/Setup Tournament", expanded=not st.session_state.tournament):
        with st.form("tournament_form"):
            st.session_state.tournament_name = st.text_input("Tournament Name", value=st.session_state.tournament_name)
            player_input = st.text_area("Enter player names (one per line)", "\n".join(st.session_state.players))
            st.session_state.num_rounds = st.number_input("Number of Rounds", min_value=1, max_value=10, value=st.session_state.num_rounds, step=1)
            submitted = st.form_submit_button("Create Tournament")

            if submitted and st.session_state.tournament_name and player_input:
                st.session_state.players = [name.strip() for name in player_input.split('\n') if name.strip()]
                if len(st.session_state.players) < 2:
                    st.error("At least 2 players are required!")
                else:
                    # Clear ALL old hoop input states from previous tournaments
                    for key in list(st.session_state.keys()):
                        if key.endswith(("_temp", "_input")):
                            del st.session_state[key]
                            
                    # FIX: Instantiate the tournament, which calls the pairing logic
                    st.session_state.tournament = SwissTournament(st.session_state.players, int(st.session_state.num_rounds))
                    st.success("Tournament created! Pairings generated for all rounds.")
                    st.experimental_rerun() # Rerun to display the pairings immediately

    # --- Tournament Management ---
    if st.session_state.tournament:
        tournament = st.session_state.tournament
        
        # FIX: The database connection should only be created when needed, 
        # and not inside the main loop, but we will create it once for the session 
        # for simplicity, and close it after the final save.
        
        st.header(f"Tournament: {st.session_state.tournament_name}")

        # --- Match Results & Pairing Display ---
        st.subheader("Match Results")
        with st.form("results_form"): # Put all inputs in one form to reduce reruns
            for round_num in range(tournament.num_rounds):
                st.markdown(f"#### Round {round_num + 1}")
                pairings = tournament.get_round_pairings(round_num)
                
                for match_num, match in enumerate(pairings):
                    if match.player2 is None:
                        # FIX: Displaying the BYE player's points in the match display
                        st.info(f"**Match {match_num + 1}:** {match.player1.name} gets a **BYE** (1 win point)")
                        continue
                    
                    col1, col2, col3 = st.columns([1, 1, 1])
                    
                    with col1:
                        st.markdown(f"**Match {match_num + 1}**")
                        st.write(f"**{match.player1.name}**")
                    
                    # Score Input 1
                    hoops1_key = f"hoops1_r{round_num}_m{match_num}"
                    with col2:
                        hoops1 = number_input_with_buttons(
                            label=f"Hoops {match.player1.name}",
                            key=hoops1_key,
                            value=int(match.get_scores()[0]),
                            min_value=0, max_value=26
                        )
                        
                    # Score Input 2
                    hoops2_key = f"hoops2_r{round_num}_m{match_num}"
                    with col3:
                        hoops2 = number_input_with_buttons(
                            label=f"Hoops {match.player2.name}",
                            key=hoops2_key,
                            value=int(match.get_scores()[1]),
                            min_value=0, max_value=26
                        )
                        
            # FIX: One single 'Update All Results' button for the whole form
            results_submitted = st.form_submit_button("Update All Match Results")
            
            if results_submitted:
                for round_num in range(tournament.num_rounds):
                    for match_num, match in enumerate(tournament.get_round_pairings(round_num)):
                        if match.player2 is not None:
                            hoops1_key = f"hoops1_r{round_num}_m{match_num}_temp"
                            hoops2_key = f"hoops2_r{round_num}_m{match_num}_temp"
                            
                            # Retrieve values from session state
                            hoops1 = st.session_state.get(hoops1_key, 0)
                            hoops2 = st.session_state.get(hoops2_key, 0)
                            
                            tournament.record_result(round_num, match_num, hoops1, hoops2)
                st.success("All results updated! Standings and subsequent pairings recalculated.")
                st.experimental_rerun() # Rerun to show updated standings/pairings

        # --- Standings ---
        st.subheader("Current Standings 🏆")
        standings = tournament.get_standings()
        standings_data = [{
            'Rank': i+1,
            'Name': p.name,
            'Wins': p.wins,
            'Net Hoops': p.hoops_scored - p.hoops_conceded,
            'Hoops Scored': p.hoops_scored
        } for i, p in enumerate(standings)]
        st.dataframe(pd.DataFrame(standings_data), use_container_width=True)

        # --- Save and Export ---
        st.subheader("Save and Export")
        
        col_save, col_export1, col_export2 = st.columns(3)

        # Save to database
        with col_save:
            if st.button("Save Tournament to DB"):
                conn = init_db()
                save_to_db(tournament, st.session_state.tournament_name, conn)
                conn.close() # Close connection after use
                st.success("Tournament saved to database!")

        # Export to CSV
        with col_export1:
            if st.button("Generate CSV"):
                filename = export_to_csv(tournament, st.session_state.tournament_name)
                if filename:
                    with open(filename, 'rb') as f:
                        st.download_button(
                            label="Download CSV",
                            data=f.read(),
                            file_name=filename,
                            mime='text/csv'
                        )
                    os.remove(filename)  # Clean up temporary file

        # Export to Excel
        with col_export2:
            if st.button("Generate Excel"):
                filename = export_to_excel(tournament, st.session_state.tournament_name)
                if filename:
                    with open(filename, 'rb') as f:
                        st.download_button(
                            label="Download Excel",
                            data=f.read(),
                            file_name=filename,
                            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                        )
                    os.remove(filename)  # Clean up temporary file

if __name__ == "__main__":
    main()