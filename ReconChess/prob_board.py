from typing import List, Tuple

import chess
import numpy as np

import random
import math

# to convolve uncertainties
from scipy import signal

#order = [4, 20, 3, 19, 7, 23, 0, 16, 6, 22, 1, 17, 5, 21, 2, 18, 8, 24, 9, 25, 10, 26, 11, 27, 12, 28, 13, 29, 14, 30,
         #15, 31]
order = [20, 19, 23, 16, 22, 17, 21, 18, 24, 25, 26, 27, 28, 29, 30, 31, 4, 3, 7, 0, 6, 1, 5, 2, 8, 9, 10, 11, 12, 13, 14, 15]

import copy

class PiecewiseGrid:
    def __copy__(self):
        newgrid = PiecewiseGrid(chess.Board())
        newgrid.piece_grids = np.copy(self.piece_grids)
        newgrid.piece_types = copy.deepcopy(self.piece_types)
        newgrid.own_pieces = copy.deepcopy(self.own_pieces)
        newgrid.captured = copy.deepcopy(self.captured_list)
        newgrid.promoted = copy.deepcopy(self.promoted)
        newgrid.enemy_moves = copy.deepcopy(self.enemy_moves)
        newgrid.enemy_pawn_columns = copy.deepcopy(self.enemy_pawn_columns)
        newgrid.base_uncertainty = self.base_uncertainty.copy()
        newgrid.last_sensed = self.last_sensed.copy()
        return newgrid

    def mirror(self):
        self.piece_grids = np.flip(self.piece_grids, axis=0)
        self.piece_grids = np.flip(self.piece_grids, axis=1)

        temp = self.piece_grids[:, :, :16].copy()
        self.piece_grids[:, :, :16] = self.piece_grids[:, :, 16:]
        self.piece_grids[:, :, 16:] = temp

        self.swap(self.captured_list, slice(0, 16), slice(16, 32))
        self.swap(self.promoted, slice(0, 16), slice(16, 32))
        self.enemy_moves = []

        self.base_uncertainty = np.zeros((8, 8))
        self.last_sensed = np.zeros((8, 8))

        # give enemy perfect information about our pawns
        self.enemy_pawn_columns = []
        for i in range(8):
            rank, file = np.unravel_index(np.argmax(self.piece_grids[:, :, i + 24]), (8, 8))
            self.enemy_pawn_columns.append([file])


    def swap(self, arr, slice1: slice, slice2: slice):
        temp = copy.deepcopy(arr[slice1])
        arr[slice1] = arr[slice2]
        arr[slice2] = temp

    def __init__(self, board: chess.Board):
        self.piece_grids = np.zeros((8, 8, 32))
        self.piece_types = ['r', 'n', 'b', 'q', 'k', 'b', 'n', 'r'] + ['p'] * 8
        self.piece_types = self.piece_types + [x.upper() for x in self.piece_types]

        self.own_pieces = [False] * 16 + [True] * 16
        self.captured_list = [None] * 32
        self.promoted = [False] * 32
        self.enemy_moves = []
        self.enemy_pawn_columns = [ [i] for i in range(8) ] # possible columns the enemy's pawns could be in

        self.base_uncertainty = np.zeros((8, 8))
        self.last_sensed = np.zeros((8, 8))

        for i in range(32):
            piece = chess.Piece.from_symbol(self.piece_types[i])
            pieces = list(board.pieces(piece.piece_type, piece.color))
            if len(pieces) > 0:
                file = chess.square_file(pieces[0])
                rank = chess.square_rank(pieces[0])
                self.piece_grids[rank, file, i] = 1.0
                board.set_piece_at(pieces[0], None)
            else:
                self.captured_list[i] = []

    # possible moves represents a probability distribution. it is stored as a list of tuples of the form (move, piece_type, chance)
    # move chances are stored as numpy array
    def update_prob_board_from_moves(self, possible_moves):
        for move, piece_type, chance in possible_moves:
            # todo: add possibility of pawn switching columns
            # self.piece_types = ['r', 'n', 'b', 'q', 'k', 'b', 'n', 'r'] + ['p'] * 8

            move_indices = []
            if piece_type == 'r':
                move_indices.append(0)
                move_indices.append(7)
            elif piece_type == 'n':
                move_indices.append(1)
                move_indices.append(6)
            elif piece_type == 'b':
                move_indices.append(2)
                move_indices.append(5)
            elif piece_type == 'q':
                move_indices.append(3)
            elif piece_type == 'k':
                move_indices.append(4)
            else:  # pawn
                file = chess.square_file(move.from_square)
                move_indices.append(8 + file)

            for move_index in move_indices:
                from_file = chess.square_file(move.from_square)
                from_rank = chess.square_rank(move.from_square)

                to_file = chess.square_file(move.to_square)
                to_rank = chess.square_rank(move.to_square)

                prob = self.piece_grids_temp[from_rank, from_file, move_index] * chance
                self.piece_grids[from_rank, from_file, move_index] -= prob
                self.piece_grids[to_rank, to_file, move_index] += prob

    # possible moves represents a probability distribution. it is stored as a list of tuples of the form (move, piece_type, chance)
    def handle_enemy_move(self, possible_moves: List[Tuple[chess.Move, chess.PieceType, float]], captured_piece: bool, captured_square: chess.Square):
        self.piece_grids_temp = self.piece_grids.copy()
        self.enemy_moves = possible_moves if not captured_piece else []
        if captured_piece: # TODO: Fix this, something here is not quite working
            # print("The enemy captured our piece")
            file = chess.square_file(captured_square)
            rank = chess.square_rank(captured_square)

            # consider possibility, no matter how small, that an enemy pawn captured the piece
            for column in self.enemy_pawn_columns:
                if file - 1 in column or file + 1 in column and not file in column:
                    column.append(file)

            piece_chances = np.array([0.0] * 32)
            board = self.gen_certain_board()

            # take our own piece out of the game
            our_piece = np.argmax(self.piece_grids[rank, file, 16:32]) + 16
            # print("The enemy has captured our piece of " + self.piece_types[our_piece])
            self.captured_list[our_piece] = []
            self.piece_grids[:, :, our_piece] = 0.0

            for i in range(16):
                piece_grid = self.piece_grids[:, :, i]
                if not self.captured_list[i] is None:
                    continue

                if self.piece_types[i] == 'r' or self.piece_types[i] == 'q':
                    x = file
                    while x < 8 and board.piece_at(chess.square(x, rank)) == None:
                        piece_chances[i] += piece_grid[rank, x]
                        x += 1
                    x = file
                    while x >= 0 and board.piece_at(chess.square(x, rank)) == None:
                        piece_chances[i] += piece_grid[rank, x]
                        x -= 1

                    y = rank
                    while y < 8 and board.piece_at(chess.square(file, y)) == None:
                        piece_chances[i] += piece_grid[y, file]
                        y += 1

                    y = rank
                    while y >= 0 and board.piece_at(chess.square(file, y)) == None:
                        piece_chances[i] += piece_grid[y, file]
                        y -= 1

                if self.piece_types[i] == 'b' or self.piece_types[i] == 'q':
                    i = 0
                    while file + i < 8 and rank + i < 8 and board.piece_at(chess.square(file + i, rank + i)) == None:
                        piece_chances[i] += piece_grid[rank + i, file + i]
                        i += 1
                    i = 0
                    while file - i >= 0 and rank + i < 8 and board.piece_at(chess.square(file - i, rank + i)) == None:
                        piece_chances[i] += piece_grid[rank + i, file - i]
                        i += 1
                    i = 0
                    while file - i >= 0 and rank - i >= 0 and board.piece_at(chess.square(file - i, rank - i)) == None:
                        piece_chances[i] += piece_grid[rank - i, file - i]
                        i += 1
                    i = 0
                    while file + i < 8 and rank - i >= 0 and board.piece_at(chess.square(file + i, rank - i)) == None:
                        piece_chances[i] += piece_grid[rank - i, file + i]
                        i += 1

                if self.piece_types[i] == 'n':
                    if file + 2 < 8 and rank + 1 < 8:
                        piece_chances[i] += piece_grid[rank + 1, file + 2]
                    if file + 1 < 8 and rank + 2 < 8:
                        piece_chances[i] += piece_grid[rank + 2, file + 1]

                    if file - 1 >= 0 and rank + 2 < 8:
                        piece_chances[i] += piece_grid[rank + 2, file - 1]
                    if file - 2 >= 0 and rank + 1 < 8:
                        piece_chances[i] += piece_grid[rank + 1, file - 2]

                    if file + 1 < 8 and rank - 2 >= 0:
                        piece_chances[i] += piece_grid[rank - 2, file + 1]
                    if file + 2 < 8 and rank - 1 >= 0:
                        piece_chances[i] += piece_grid[rank - 1, file + 2]

                    if file - 2 >= 0 and rank - 1 >= 0:
                        piece_chances[i] += piece_grid[rank - 1, file - 2]
                    if file - 1 >= 0 and rank - 2 >= 0:
                        piece_chances[i] += piece_grid[rank - 2, file - 1]

                if self.piece_types[i] == 'p' and rank - 1 >= 0 and file - 1 >= 0:
                    piece_chances[i] += piece_grid[rank - 1, file - 1]
                if self.piece_types[i] == 'p' and rank - 1 >= 0 and file + 1 < 8:
                    piece_chances[i] += piece_grid[rank - 1, file + 1]

            if np.sum(piece_chances > 0.001):
                piece_chances /= np.sum(piece_chances)
                piece_chances.reshape(32, 1)
            else: # we really have no clue which piece captured ours so we distribute it evenly among enemy pieces
                # print("We have no idea which enemy piece captured ours")
                self.base_uncertainty[rank, file] = 0.8 # We really want to figure out what happened
                possible_capturors = [i for i in range(16) if self.captured_list[i] is None and \
                                      (i < 8 or file - 1 in self.enemy_pawn_columns[i-8] or file + 1 in self.enemy_pawn_columns[i-8])]
                piece_chances = np.zeros(32)
                piece_chances[possible_capturors] = 1.0 / len(possible_capturors)
                #piece_chances = np.array([1.0 / 16.0] * 16 + [0] * 16)

            self.piece_grids = self.piece_grids * (1 - piece_chances)

            piece_mask = np.ones((8, 8))
            piece_mask[rank, file] = 0
            piece_mask = np.repeat(piece_mask[:, :, np.newaxis], 32, axis=2)

            self.piece_grids = self.piece_grids * piece_mask

            for i in range(32):
                if self.captured_list[i] is None:
                    self.piece_grids[rank, file, i] = piece_chances[i]
        else:
            self.update_prob_board_from_moves(self.enemy_moves)

    def get_board_uncertainty(self):
        KING_ATTACK = 0.25
        PIECE_PIN = 0.15

        uncertainty = 0.5 - np.abs(0.5 - self.piece_grids)

        board = self.gen_certain_board()

        # find location of your own king
        rank, file = np.unravel_index(np.argmax(self.piece_grids[:, :, 20]), (8, 8))

        # add uncertainty from knight attacks
        knights = [self.piece_types[i] == 'n' and self.captured_list[i] is None for i in range(32)]
        knight_directions = [(2, 1), (1, 2), (-1, 2), (-2, 1), (1, -2), (2, -1), (-2, -1), (-1, -2)]
        for dir in knight_directions:
            x = file + dir[0]
            y = rank + dir[1]
            if x < 8 and y < 8 and x >= 0 and y >= 0 and board.piece_at(chess.square(x,y)) == None:
                try:
                    uncertainty[y, x, knights] += KING_ATTACK
                except IndexError as ie:
                    # print("ERROR WHEN TRYING TO INDEX KNIGHTS")
                    # print(knights)
                    pass

        # add uncertainty from sliding attacks
        straight_attackers = [(self.piece_types[i] == 'q' or self.piece_types[i] == 'r') and self.captured_list[i] is None for i in range(32)]
        diagonal_attackers = [(self.piece_types[i] == 'q' or self.piece_types[i] == 'b') and self.captured_list[i] is None for i in range(32)]
        directions = [(0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)]
        for i, dir in enumerate(directions):
            x = file + dir[0]
            y = rank + dir[1]
            num_hits = 0

            while x < 8 and x >= 0 and y < 8 and y >= 0 and num_hits < 2:
                piece = board.piece_at(chess.square(x, y))
                if not piece is None:
                    num_hits += 1 if piece.color == chess.WHITE else 2
                else:
                    try:
                        uncertainty[y, x, straight_attackers if i < 4 else diagonal_attackers] += KING_ATTACK if num_hits == 0 else PIECE_PIN
                    except IndexError as ie:
                        # print("ERROR WHEN TRYING TO INDEX SLIDING")
                        # print(straight_attackers)
                        # print(diagonal_attackers)
                        pass
                x += dir[0]
                y += dir[1]

        uncertainty = np.max(uncertainty, axis=2)

        # update count of when certain pieces were last sensed
        certainties = np.max(self.piece_grids[:, :, :16], axis=2)
        certainties[certainties < 0.99] = 0.0
        certainties[certainties >= 0.99] = 0.1
        self.last_sensed += certainties
        self.last_sensed[self.last_sensed > 1.0] = 1.0

        #uncertainty += self.last_sensed
        uncertainty += self.base_uncertainty

        return uncertainty

    def get_total_uncertainty(self):
        return np.sum(self.get_board_uncertainty())

    def choose_sense(self):
        """
        This function is called to choose a square to perform a sense on.
        :param possible_sense: List(chess.SQUARES) -- list of squares to sense around
        :param possible_moves: List(chess.Moves) -- list of acceptable moves based on current board
        :param seconds_left: float -- seconds left in the game
        :return: chess.SQUARE -- the center of 3x3 section of the board you want to sense
        :example: choice = chess.A1
        """

        # finds which 3x3 squares have the highest uncertainties
        uncertainties = signal.convolve2d(self.get_board_uncertainty(), np.ones((3, 3)), mode="same")

        rank, file = np.unravel_index(np.argmax(uncertainties), (8, 8))
        return chess.square(file, rank)

    def handle_sense_result(self, sense_result):
        """
        This is a function called after your picked your 3x3 square to sense and gives you the chance to update your
        board.
        :param sense_result: A list of tuples, where each tuple contains a :class:`Square` in the sense, and if there
                             was a piece on the square, then the corresponding :class:`chess.Piece`, otherwise `None`.
        :example:
        [
            (A8, Piece(ROOK, BLACK)), (B8, Piece(KNIGHT, BLACK)), (C8, Piece(BISHOP, BLACK)),
            (A7, Piece(PAWN, BLACK)), (B7, Piece(PAWN, BLACK)), (C7, Piece(PAWN, BLACK)),
            (A6, None), (B6, None), (C8, None)
        ]
        """

        if len(self.enemy_moves) > 0:
            maxes = self.piece_grids_temp.max(axis=2)

            # prune enemy moves that are no longer possible
            # might not be the most efficient algorithm for this, but it works for now
            for loc in sense_result:
                if not loc[1] is None and loc[1].color == chess.WHITE:
                    continue

                file = chess.square_file(loc[0])
                rank = chess.square_rank(loc[0])

                # if there was no piece in the square previously and there is one there now, we know that piece moved
                if maxes[rank, file] < 0.001 and not loc[1] is None:
                    piece_type = loc[1].symbol()
                    self.enemy_moves = [x for x in self.enemy_moves if x[1] == piece_type and x[0].to_square == loc[0]] # we know the move ended at this square

                # if we know where a piece is for certain, we can make some inferences
                if maxes[rank, file] > 0.999:
                    piece_index = np.argmax(self.piece_grids[rank, file, :])
                    piece_type = self.piece_types[piece_index]

                    if loc[1] == None:  # if it's no longer there, it must have moved. eliminate all moves which don't start from this square and involve this piece
                        self.enemy_moves = [x for x in self.enemy_moves if x[1] == piece_type and x[0].from_square == loc[0]] # we know the move started at this square
                    elif loc[1].symbol() == piece_type:  # if it's still there, it can't have moved
                        self.enemy_moves = [x for x in self.enemy_moves if x[0].from_square != loc[0]]

                    self.enemy_moves = [x for x in self.enemy_moves if x[0].to_square != loc[0] or x[1] == piece_type]

                if loc[1] is None:
                    self.enemy_moves = [x for x in self.enemy_moves if x[0].to_square != loc[0]]

                # TODO: Add more inferences for how the pieces might have moved

            self.piece_grids = self.piece_grids_temp.copy()

            if len(self.enemy_moves) == 0: # We literally have no clue what move the enemy could have made
                # print("The bot has no idea what move the enemy made")
                pass
            else:
                # renormalize move probabilities
                moves, piece_types, chances = zip(*self.enemy_moves)
                chances = np.array(chances)
                chances /= np.sum(chances)
                self.enemy_moves = list(zip(moves, piece_types, chances.tolist()))

        # make a second update to probability grid with more informed enemy moves
        self.update_prob_board_from_moves(self.enemy_moves)

        # update piece grid based on sense results
        handled = [False] * 32
        for loc in sense_result:
            # we don't check our own pieces in the sense result
            if not loc[1] is None and loc[1].color == chess.WHITE:
                continue

            file = chess.square_file(loc[0])
            rank = chess.square_rank(loc[0])

            self.base_uncertainty[rank, file] = 0.0
            self.last_sensed[rank, file] = 0.0

            # if there is a piece, find which one it is and update probabilities accordingly
            if not loc[1] is None:
                max = -1.0
                piece_index = 0

                for i in range(16):
                    if self.piece_types[i] == loc[1].symbol() and self.piece_grids[rank, file, i] > max and not handled[i] \
                            and (not loc[1].symbol() == 'p' or file in self.enemy_pawn_columns[i - 8]):
                        max = self.piece_grids[rank, file, i]
                        piece_index = i

                self.piece_grids[:, :, piece_index] = np.zeros((8, 8))
                self.piece_grids[rank, file, :] *= 0
                self.piece_grids[rank, file, piece_index] = 1.0
                handled[piece_index] = True

            # todo: pawns need more logic to handle duplicates
        divider = self.piece_grids.sum((0, 1)).reshape(1, 1, 32)
        divider[divider < 0.001] = 1
        self.piece_grids /= divider

    def handle_player_move(self, completed_move: chess.Move, captured_piece: bool):
        # player passed and there is nothing to handle
        if completed_move == None:
            return

        from_file = chess.square_file(completed_move.from_square)
        from_rank = chess.square_rank(completed_move.from_square)
        to_file = chess.square_file(completed_move.to_square)
        to_rank = chess.square_rank(completed_move.to_square)

        piece_loc = np.argmax(self.piece_grids[from_rank, from_file, 16:]) + 16
        self.piece_grids[from_rank, from_file, piece_loc] = 0.0

        # TODO: Come up with better variable names for whatever is in this method

        # find out which piece was probably captured, and which pieces could have been captured
        if captured_piece:
            # print("We just captured a piece")
            if np.sum(self.piece_grids[to_rank, to_file, :16]) > 0.001:
                piece = np.argmax(self.piece_grids[to_rank, to_file, :16])
                indices = np.delete(np.arange(0, 16), piece)
                captured_list = np.delete(np.arange(0, 16), piece)[self.piece_grids[to_rank, to_file, indices] > 0.001]
                self.captured_list[piece] = captured_list
            else: # we have no clue which piece we just captured
                # print("We have no clue which piece it is")
                piece = 4
                while piece == 4: # guess anything so long as it's not the king
                    piece = random.randint(0, 15)
                captured_list = np.delete(np.arange(0, 16), piece)
                captured_list = np.delete(captured_list, 4)
                self.captured_list[piece] = captured_list
            self.piece_grids[:, :, piece] = np.zeros((8, 8))

        self.piece_grids[to_rank, to_file, piece_loc] = 1.0

        divider = self.piece_grids.sum((0, 1)).reshape(1, 1, 32)
        divider[divider < 0.001] = 1
        self.piece_grids /= divider

        if np.sum(self.piece_grids[:, :, 4]) < 0.01:
            # print("CODE RED WE LOST THE KING!!!!")
            pass

    def gen_certain_board(self):
        board = chess.Board()
        board.set_piece_map({})
        for i in range(32):
            piece_grid = self.piece_grids[:, :, i]
            if np.max(piece_grid) > 0.99:
                location = np.argmax(piece_grid)
                board.set_piece_at(location, chess.Piece.from_symbol(self.piece_types[i]))

        return board

    def gen_board(self):
        spaces = []
        piece_map = {}

        for i in order:
            if not self.captured_list[i] is None:
                continue

            # transposing from numpy format to board format begins here
            piece_grid = np.copy(self.piece_grids[:, :, i]).flatten()

            if np.sum(piece_grid) < 0.001:
                continue

            piece_grid_copy = piece_grid.copy()
            piece_grid[spaces] = 0
            if np.sum(piece_grid) < 0.001:
                # print("Oh no, no where to place this piece")
                #b = chess.Board()
                #b.set_piece_map(piece_map)
                ## print(b)
                # print(piece_grid_copy)
                pass
            else:
                piece_grid /= np.sum(piece_grid)

                num = np.random.choice(64, 1, p=piece_grid)[0]
                # and ends here when flattened index is reinterpreted as board index
                piece_map[num] = chess.Piece.from_symbol(self.piece_types[i])

                spaces.append(num)

        board = chess.Board()
        board.set_piece_map(piece_map)
        return board

    def num_board_states(self) -> int:
        piece_grids_copy = self.piece_grids.copy()
        piece_grids_copy[piece_grids_copy == 0] = 1.0 # entropy is zero when probability is zero or one, but log breaks with zero

        entropy = -np.sum(piece_grids_copy * np.log2(piece_grids_copy))
        entropy = 2 ** entropy

        return math.ceil(entropy)