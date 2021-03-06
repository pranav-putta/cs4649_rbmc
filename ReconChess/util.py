import chess
from collections import namedtuple

Configuration = namedtuple('Config', 'white, white_args, black, black_args, verbose, num_games')


def mirror(sq: chess.Square):
    if sq is None:
        return sq
    rank = 7 - chess.square_rank(sq)
    file = 7 - chess.square_file(sq)
    return chess.square(file, rank)


def flip_move(move: chess.Move):
    if move is None:
        return move
    return chess.Move(int(mirror(move.from_square)), int(mirror(move.to_square)))

def mirror_sense_result(sense_result):
    new_results = []
    for result in sense_result:
        sq, p = result
        sq = mirror(sq)
        if p is not None:
            p.color = not p.color
        new_results.append((sq, p))
    return new_results
verbose = False
def format_print_board(board, force_verbose=False):
    if verbose and not force_verbose:
        return
    rows = ['8', '7', '6', '5', '4', '3', '2', '1']
    fen = board.board_fen()

    fb = "   A   B   C   D   E   F   G   H  "
    fb += rows[0]
    ind = 1
    for f in fen:
        if f == '/':
            fb += '|' + rows[ind]
            ind += 1
        elif f.isnumeric():
            for i in range(int(f)):
                fb += '|   '
        else:
            fb += '| ' + f + ' '
    fb += '|'

    ind = 0
    for i in range(9):
        for j in range(34):
            print(fb[ind], end='')
            ind += 1
        print('\n', end='')
    print("")


def number_to_square(number):
    file = number % 8
    rank = (number - file) // 8
    return chess.square(file, rank)


def square_to_number(square):
    return 8 * chess.square_rank(square) + chess.square_file(square)


def square_parity(s):
    return (chess.square_file(s) + chess.square_rank(s)) % 2
