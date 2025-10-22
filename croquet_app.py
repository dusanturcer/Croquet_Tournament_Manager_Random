import random
from itertools import combinations

class Player:
    def __init__(self, id, name):
        self.id = id
        self.name = name
        self.points = 0
        self.opponents = set()

    def add_opponent(self, opponent_id):
        self.opponents.add(opponent_id)

    def __repr__(self):
        return f"Player(id={self.id}, name={self.name}, points={self.points})"

class Match:
    def __init__(self, player1, player2):
        self.player1 = player1
        self.player2 = player2
        self.result = None

    def set_result(self, result):
        self.result = result
        if result == 1:
            self.player1.points += 1
        elif result == 2:
            self.player2.points += 1
        elif result == 0:
            self.player1.points += 0.5
            self.player2.points += 0.5

    def __repr__(self):
        return f"Match({self.player1.name} vs {self.player2.name}, result={self.result})"

class SwissTournament:
    def __init__(self, players, num_rounds):
        self.players = [Player(i, name) for i, name in enumerate(players)]
        self.num_rounds = num_rounds
        self.rounds = []
        self.generate_all_pairings()

    def generate_all_pairings(self):
        self.rounds = []
        available_players = self.players.copy()
        random.shuffle(available_players)
        player_opponents = {p.id: p.opponents for p in self.players}

        for round_num in range(self.num_rounds):
            round_pairings = []
            used_players = set()
            # Create a list of possible pairings, prioritizing minimal repetitions
            possible_pairs = []
            for p1, p2 in combinations(available_players, 2):
                if p2.id not in player_opponents[p1.id] and p1.id not in player_opponents[p2.id]:
                    possible_pairs.append((p1, p2))

            random.shuffle(possible_pairs)
            # Greedily select pairs with minimal repetitions
            while possible_pairs and len(used_players) < len(available_players):
                for pair in possible_pairs[:]:
                    p1, p2 = pair
                    if p1.id not in used_players and p2.id not in used_players:
                        round_pairings.append(Match(p1, p2))
                        used_players.add(p1.id)
                        used_players.add(p2.id)
                        p1.add_opponent(p2.id)
                        p2.add_opponent(p1.id)
                        possible_pairs.remove(pair)
                # If not all players are paired, reshuffle and try again
                if len(used_players) < len(available_players) and possible_pairs:
                    random.shuffle(possible_pairs)

            # Handle odd number of players
            if len(used_players) < len(available_players):
                for player in available_players:
                    if player.id not in used_players:
                        # Assign a bye
                        round_pairings.append(Match(player, None))
                        used_players.add(player.id)
                        player.points += 1  # Bye gives 1 point

            self.rounds.append(round_pairings)
            # Update opponents for next round
            player_opponents = {p.id: p.opponents for p in self.players}

    def record_result(self, round_num, match_num, result):
        match = self.rounds[round_num][match_num]
        if match.player2 is not None:  # Not a bye
            match.set_result(result)

    def get_standings(self):
        return sorted(self.players, key=lambda p: (-p.points, p.id))

    def get_round_pairings(self, round_num):
        return self.rounds[round_num]

    def __repr__(self):
        return f"SwissTournament(players={len(self.players)}, rounds={self.num_rounds})"

# Example usage
if __name__ == "__main__":
    players = ["Alice", "Bob", "Charlie", "David", "Eve", "Frank"]
    tournament = SwissTournament(players, 3)
    
    # Print all rounds' pairings
    for i in range(tournament.num_rounds):
        print(f"\nRound {i + 1} Pairings:")
        for j, match in enumerate(tournament.get_round_pairings(i)):
            if match.player2 is None:
                print(f"Match {j + 1}: {match.player1.name} gets a bye")
            else:
                print(f"Match {j + 1}: {match.player1.name} vs {match.player2.name}")

    # Simulate some results
    for i in range(tournament.num_rounds):
        for j, match in enumerate(tournament.get_round_pairings(i)):
            if match.player2 is not None:  # Not a bye
                result = random.choice([0, 1, 2])  # 0=draw, 1=player1 wins, 2=player2 wins
                tournament.record_result(i, j, result)

    # Print final standings
    print("\nFinal Standings:")
    for player in tournament.get_standings():
        print(f"{player.name}: {player.points} points")