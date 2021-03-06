from util import Configuration
from play_game import *

#ENV = Configuration('mcts_agent.py', [], 'mcts_agent.py', [], True, 1)
ENV = Configuration('lasalle_agent.py', [], 'knight_agent.py', [], True, 1)

wins = 0

for i in range(ENV.num_games):
    name_one, constructor_one = load_player(ENV.white)
    if len(inspect.signature(constructor_one.__init__).parameters) == len(ENV.white_args) + 1:
        player_one = constructor_one(*ENV.white_args)
    else:
        player_one = constructor_one()

    name_two, constructor_two = load_player(ENV.black)
    if len(inspect.signature(constructor_two.__init__).parameters) == len(ENV.black_args) + 1:
        player_two = constructor_two(*ENV.black_args)
    else:
        player_two = constructor_two()

    players = [player_one, player_two]
    player_names = [name_one, name_two]

    if name_one == "Human":
        color = input("Play as (0)Random (1)White (2)Black: ")
        if color == '2' or (color == '0' and random.uniform(0, 1) < 0.5):
            players.reverse()
            player_names.reverse()

    win_color, win_reason = play_local_game(players[0], players[1], player_names, verbose=ENV.verbose)
    if win_color == chess.WHITE:
        wins += 1
    print('Game Over!')
    if win_color is not None:
        print(win_reason)
    else:
        print('Draw!')
print(f"WHITE win rate: {wins / ENV.num_games}")
