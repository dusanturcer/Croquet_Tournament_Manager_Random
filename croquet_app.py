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
        if self.player2 is None:  # Bye
            return
        if result == 1:
            self.player1.points += 1
        elif result == 2:
            self.player2.points += 1
        elif result == 0:
            self.player1.points += 0.5
            self.player2.points += 0.5

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
            available_players = [p for p in self.players if len(player_opponents[p.id]) < round_num]
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
                # Give bye to one player
                bye_player = random.choice(remaining_players)
                round_pairings.append(Match(bye_player, None))
                used_players.add(bye_player.id)
                bye_player.points += 1  # Bye gives 1 point, but will be set in set_result if needed

            self.rounds.append(round_pairings)

            # Ensure all players are used in this round
            if len(used_players) < len(self.players):
                print(f"Warning: Only {len(used_players)}/{len(self.players)} players paired in round {round_num + 1}")

    def record_result(self, round_num, match_num, result):
        if 0 <= round_num < len(self.rounds) and 0 <= match_num < len(self.rounds[round_num]):
            match = self.rounds[round_num][match_num]
            match.set_result(result)
        else:
            print(f"Invalid round_num {round_num} or match_num {match_num}")

    def get_standings(self):
        return sorted(self.players, key=lambda p: (-p.points, p.id))

    def get_round_pairings(self, round_num):
        if 0 <= round_num < len(self.rounds):
            return self.rounds[round_num]
        return []

    def __repr__(self):
        return f"SwissTournament(players={len(self.players)}, rounds={self.num_rounds})"

# Example usage
if __name__ == "__main__":
    players = ["Alice", "Bob", "Charlie", "David", "Eve", "Frank"]
    tournament = SwissTournament(players, 3)
    
    # Print all rounds' pairings
    for i in range(tournament.num_rounds):
        print(f"\nRound {i + 1} Pairings:")
        pairings = tournament.get_round_pairings(i)
        for j, match in enumerate(pairings):
            if match.player2 is None:
                print(f"Match {j + 1}: {match.player1.name} gets a bye")
            else:
                print(f"Match {j + 1}: {match.player1.name} vs {match.player2.name}")

    # Simulate some results
    for i in range(tournament.num_rounds):
        pairings = tournament.get_round_pairings(i)
        for j, match in enumerate(pairings):
            if match.player2 is not None:  # Not a bye
                result = random.choice([0, 1, 2])  # 0=draw, 1=player1 wins, 2=player2 wins
                tournament.record_result(i, j, result)

    # Print final standings
    print("\nFinal Standings:")
    for player in tournament.get_standings():
        print(f"{player.name}: {player.points} points")