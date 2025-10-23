import sqlite3
import os

DB_PATH = 'tournament.db'

def create_fresh_db(db_path=DB_PATH):
    """
    Deletes the old database file if it exists and creates a new one with the 
    required table schemas for the tournament application.
    """
    
    # 1. Delete existing file if present
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"Removed existing database file: {db_path}")
    
    # 2. Connect (creates a new file) and set up schema
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        # Create 'tournaments' table
        c.execute('''CREATE TABLE tournaments
                     (id INTEGER PRIMARY KEY, name TEXT, date TEXT)''')
                     
        # Create 'players' table
        c.execute('''CREATE TABLE players
                     (tournament_id INTEGER, player_id INTEGER, name TEXT, 
                      points INTEGER, wins INTEGER, 
                      hoops_scored INTEGER, hoops_conceded INTEGER,
                      PRIMARY KEY (tournament_id, player_id),
                      FOREIGN KEY (tournament_id) REFERENCES tournaments(id))''')
                      
        # Create 'matches' table
        c.execute('''CREATE TABLE matches
                     (tournament_id INTEGER, round_num INTEGER, match_num INTEGER,
                      player1_id INTEGER, player2_id INTEGER, hoops1 INTEGER, hoops2 INTEGER)''')
        
        conn.commit()
        conn.close()
        print(f"Successfully created a fresh, empty database: {db_path}")
        
    except sqlite3.Error as e:
        print(f"An error occurred while creating the database: {e}")

if __name__ == "__main__":
    create_fresh_db()