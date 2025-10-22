import streamlit as st
import pandas as pd
import sqlite3
import random
import itertools
import csv
import os
from openpyxl import load_workbook
from openpyxl.styles import Alignment
from datetime import datetime

class Player:
    def __init__(self, id, name):
        self.id = id
        self.name = name
        self.points = 0  # Points from wins (1 per win, 0 for bye/draw)
        self.wins = 0  # Number of wins
        self.hoops_scored = 0  # Total hoops scored
        self.hoops_conceded = 0  # Total hoops conceded
        self.opponents = set()

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
        self.result = (int(hoops1), int(hoops2))  # Ensure integer
        if self.player2 is None:  # Bye
            return  # 0 points for bye
        # Update hoops
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

    def get_scores(self):
        return self.result if self.result else (0, 0)

    def __repr__(self):
        return f"Match({self.player1.name} vs {self.player2.name if self.player2 else 'BYE'}, result={self.result})"

class SwissTournament:
    def __init__(self, players, num_rounds):
        self.players = [Player(i, name) for i, name in enumerate(players)]
        self.num_rounds = num_rounds
        self.rounds = []
        self.generate_all_pairings()

    def generate_all_pairings(self):
        self.rounds = []
        player_opponents = {p.id: set() for p in self.players}

        for round_num in range(self.num_rounds):
            round_pairings = []
            available_players = self.players.copy()
            random.shuffle(available_players)
            used_players = set()

            # Generate possible pairs avoiding previous opponents
            possible_pairs = []
            for i in range(len(available_players)):
                for j in range(i + 1, len(available_players)):
                    p1 = available_players[i]
                    p2 = available_players[j]
                    if p2.id not in player_opponents[p1.id]:
                        possible_pairs.append((p1, p2))

            random.shuffle(possible_pairs)

            # Select pairs greedily
            pair_index = 0
            while len(used_players) < len(available_players) and pair_index < len(possible_pairs):
                p1, p2 = possible_pairs[pair_index]
                if p1.id not in used_players and p2.id not in used_players:
                    round_pairings.append(Match(p1, p2))
                    used_players.add(p1.id)
                    used_players.add(p2.id)
                    player_opponents[p1.id].add(p2.id)
                    player_opponents[p2.id].add(p1.id)
                pair_index += 1

            # Handle remaining players (odd number or couldn't pair)
            remaining_players = [p for p in available_players if p.id not in used_players]
            if remaining_players:
                bye_player = random.choice(remaining_players)
                round_pairings.append(Match(bye_player, None))
                used_players.add(bye_player.id)

            self.rounds.append(round_pairings)

            if len(used_players) < len(self.players):
                st.warning(f"Only {len(used_players)}/{len(self.players)} players paired in round {round_num + 1}")

    def record_result(self, round_num, match_num, hoops1, hoops2):
        if 0 <= round_num < len(self.rounds) and 0 <= match_num < len(self.rounds[round_num]):
            match = self.rounds[round_num][match_num]
            # Reset previous results
            old_hoops1, old_hoops2 = match.get_scores()
            if match.result is not None and match.player2 is not None:
                match.player1.hoops_scored -= old_hoops1
                match.player1.hoops_conceded -= old_hoops2
                match.player2.hoops_scored -= old_hoops2
                match.player2.hoops_conceded -= old_hoops1
                if old_hoops1 > old_hoops2:
                    match.player1.wins -= 1
                    match.player1.points -= 1
                elif old_hoops2 > old_hoops1:
                    match.player2.wins -= 1
                    match.player2.points -= 1
            # Set new results
            match.set_result(hoops1, hoops2)
        else:
            st.error(f"Invalid round_num {round_num} or match_num {match_num}")

    def get_standings(self):
        return sorted(self.players, key=lambda p: (p.wins, p.hoops_scored - p.hoops_conceded, p.hoops_scored), reverse=True)

    def get_round_pairings(self, round_num):
        if 0 <= round_num < len(self.rounds):
            return self.rounds[round_num]
        return []

    def __repr__(self):
        return f"SwissTournament(players={len(self.players)}, rounds={self.num_rounds})"

# Database setup
def init_db():
    conn = sqlite3.connect('tournament.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS tournaments
                 (id INTEGER PRIMARY KEY, name TEXT, date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS players
                 (tournament_id INTEGER, player_id INTEGER, name TEXT, points INTEGER, wins INTEGER,
                  hoops_scored INTEGER, hoops_conceded INTEGER,
                  PRIMARY KEY (tournament_id, player_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS matches
                 (tournament_id INTEGER, round_num INTEGER, match_num INTEGER,
                  player1_id INTEGER, player2_id INTEGER, hoops1 INTEGER, hoops2 INTEGER)''')
    conn.commit()
    return conn

# Save tournament data to database
def save_to_db(tournament, tournament_name, conn):
    try:
        c = conn.cursor()
        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("INSERT INTO tournaments (name, date) VALUES (?, ?)", (tournament_name, date))
        tournament_id = c.lastrowid

        for player in tournament.players:
            c.execute("INSERT INTO players (tournament_id, player_id, name, points, wins, hoops_scored, hoops_conceded) VALUES (?, ?, ?, ?, ?, ?, ?)",
                      (tournament_id, player.id, player.name, player.points, player.wins, player.hoops_scored, player.hoops_conceded))

        for round_num, round_pairings in enumerate(tournament.rounds):
            for match_num, match in enumerate(round_pairings):
                hoops1, hoops2 = match.get_scores()
                player2_id = match.player2.id if match.player2 else None
                c.execute("INSERT INTO matches (tournament_id, round_num, match_num, player1_id, player2_id, hoops1, hoops2) VALUES (?, ?, ?, ?, ?, ?, ?)",
                          (tournament_id, round_num, match_num, match.player1.id, player2_id, hoops1, hoops2))

        conn.commit()
    except sqlite3.Error as e:
        st.error(f"Database error: {e}")
    finally:
        conn.close()

# Export to CSV
def export_to_csv(tournament, tournament_name):
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{tournament_name}_{timestamp}.csv"
        with open(filename, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Round', 'Match', 'Player 1', 'Player 2', 'Hoops 1', 'Hoops 2'])
            for round_num, round_pairings in enumerate(tournament.rounds):
                for match_num, match in enumerate(round_pairings):
                    player2 = match.player2.name if match.player2 else 'BYE'
                    hoops1, hoops2 = match.get_scores()
                    writer.writerow([round_num + 1, match_num + 1, match.player1.name, player2, hoops1, hoops2])
        return filename
    except IOError as e:
        st.error(f"Error writing CSV: {e}")
        return None

# Export to Excel
def export_to_excel(tournament, tournament_name):
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{tournament_name}_{timestamp}.xlsx"
        data = []
        for round_num, round_pairings in enumerate(tournament.rounds):
            for match_num, match in enumerate(round_pairings):
                player2 = match.player2.name if match.player2 else 'BYE'
                hoops1, hoops2 = match.get_scores()
                data.append({
                    'Round': round_num + 1,
                    'Match': match_num + 1,
                    'Player 1': match.player1.name,
                    'Player 2': player2,
                    'Hoops 1': hoops1,
                    'Hoops 2': hoops2
                })
        df = pd.DataFrame(data)
        df.to_excel(filename, index=False)
        
        # Format Excel file
        wb = load_workbook(filename)
        ws = wb.active
        for row in ws.iter_rows(min_row=1, max_row=ws.max_row, min_col=1, max_col=ws.max_column):
            for cell in row:
                cell.alignment = Alignment(horizontal='center')
        wb.save(filename)
        return filename
    except Exception as e:
        st.error(f"Error writing Excel: {e}")
        return None

# Custom number input with + and - buttons
def number_input_with_buttons(label, key, value=0, min_value=0, max_value=26, step=1):
    # Initialize session state for this key if not set
    if f"{key}_temp" not in st.session_state:
        st.session_state[f"{key}_temp"] = int(value if isinstance(value, (int, float)) else 0)  # Ensure integer

    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        if st.button("−", key=f"minus_{key}"):
            st.session_state[f"{key}_temp"] = max(min_value, st.session_state[f"{key}_temp"] - step)
    with col2:
        current_value = st.session_state[f"{key}_temp"]
        try:
            current_value = int(current_value)  # Ensure integer
        except (TypeError, ValueError):
            current_value = 0  # Fallback to 0 if invalid
        st.session_state[f"{key}_temp"] = st.number_input(
            label,
            min_value=min_value,
            max_value=max_value,
            value=current_value,
            step=step,
            format="%d",
            key=key
        )
    with col3:
        if st.button("+", key=f"plus_{key}"):
            st.session_state[f"{key}_temp"] = min(max_value, st.session_state[f"{key}_temp"] + step)
    
    return int(st.session_state[f"{key}_temp"])  # Return integer

# Streamlit app
def main():
    st.title("Croquet Tournament Manager")

    # Initialize session state
    if 'tournament' not in st.session_state:
        st.session_state.tournament = None
        st.session_state.tournament_name = ""
        st.session_state.players = []
        st.session_state.num_rounds = 3

    # Input form
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
                # Clear all previous hoop input states
                for key in list(st.session_state.keys()):
                    if key.endswith("_temp"):
                        del st.session_state[key]
                st.session_state.tournament = SwissTournament(st.session_state.players, int(st.session_state.num_rounds))
                st.success("Tournament created!")

    # Display pairings and record results
    if st.session_state.tournament:
        tournament = st.session_state.tournament
        conn = init_db()

        for round_num in range(tournament.num_rounds):
            st.subheader(f"Round {round_num + 1} Pairings")
            pairings = tournament.get_round_pairings(round_num)
            
            for match_num, match in enumerate(pairings):
                with st.container():
                    if match.player2 is None:
                        st.write(f"**{match.player1.name} gets a BYE** (0 points)")
                        continue
                    
                    col1, col2, col3, col4 = st.columns([2, 1.5, 1.5, 2])
                    
                    with col1:
                        st.write(f"**Match {match_num + 1}:**")
                        st.write(f"{match.player1.name} vs {match.player2.name}")
                    
                    with col2:
                        st.write("Hoops Scored")
                        hoops1_key = f"hoops1_r{round_num}_m{match_num}"
                        try:
                            hoops1 = number_input_with_buttons(
                                f"{match.player1.name}",
                                hoops1_key,
                                value=int(match.get_scores()[0] if match.get_scores()[0] is not None else 0),
                                key=f"{hoops1_key}_input",
                                max_value=26
                            )
                        except (TypeError, ValueError) as e:
                            st.error(f"Error setting hoops for {match.player1.name}: {e}")
                            hoops1 = 0
                    
                    with col3:
                        hoops2_key = f"hoops2_r{round_num}_m{match_num}"
                        try:
                            hoops2 = number_input_with_buttons(
                                f"{match.player2.name}",
                                hoops2_key,
                                value=int(match.get_scores()[1] if match.get_scores()[1] is not None else 0),
                                key=f"{hoops2_key}_input",
                                max_value=26
                            )
                        except (TypeError, ValueError) as e:
                            st.error(f"Error setting hoops for {match.player2.name}: {e}")
                            hoops2 = 0
                    
                    with col4:
                        if st.button(f"Update Result", key=f"update_r{round_num}_m{match_num}"):
                            tournament.record_result(round_num, match_num, hoops1, hoops2)
                            st.success("Result updated!")

        # Save to database
        if st.button("Save Tournament"):
            save_to_db(tournament, st.session_state.tournament_name, conn)
            st.success("Tournament saved to database!")

        # Display standings
        st.subheader("Current Standings")
        standings = tournament.get_standings()
        standings_data = [{
            'Rank': i+1,
            'Name': p.name,
            'Wins': p.wins,
            'Net Hoops': p.hoops_scored - p.hoops_conceded,
            'Hoops Scored': p.hoops_scored
        } for i, p in enumerate(standings)]
        st.dataframe(pd.DataFrame(standings_data))

        # Export options
        col_export1, col_export2 = st.columns(2)
        with col_export1:
            if st.button("Export to CSV"):
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
        with col_export2:
            if st.button("Export to Excel"):
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