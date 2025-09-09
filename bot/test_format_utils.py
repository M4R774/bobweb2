from unittest import TestCase

from bot.utils_format import ManipulationOperation, manipulate_matrix

# Simple 3x3 matrix (list of lists) for testing
simple_matrix = [[1, 2, 3],
                 [4, 5, 6],
                 [7, 8, 9]]

non_square_matrix = [[1, 2, 3],
                     [4, 5, 6]]


class TestMatrixManipulationOperations(TestCase):
    """ Tests format utils. Uses Unit test case as no need for models or database connections """

    def test_rotate_matrix_clockwise_90(self):
        operation = ManipulationOperation.ROTATE_90
        expected = [[7, 4, 1],
                    [8, 5, 2],
                    [9, 6, 3]]
        rotated_matrix = manipulate_matrix(simple_matrix, operation)
        self.assertEqual(expected, rotated_matrix)

        expected = [[4, 1],
                    [5, 2],
                    [6, 3]]
        rotated_matrix = manipulate_matrix(non_square_matrix, operation)
        self.assertEqual(expected, rotated_matrix)

    def test_rotate_matrix_counter_clockwise_90(self):
        operation = ManipulationOperation.ROTATE_NEG_90
        expected = [[3, 6, 9],
                    [2, 5, 8],
                    [1, 4, 7]]
        rotated_matrix = manipulate_matrix(simple_matrix, operation)
        self.assertEqual(expected, rotated_matrix)

        expected = [[3, 6],
                    [2, 5],
                    [1, 4]]
        rotated_matrix = manipulate_matrix(non_square_matrix, operation)
        self.assertEqual(expected, rotated_matrix)

    def test_rotate_matrix_180(self):
        operation = ManipulationOperation.ROTATE_180

        expected = [[9, 8, 7],
                    [6, 5, 4],
                    [3, 2, 1]]
        rotated_matrix = manipulate_matrix(simple_matrix, operation)
        self.assertEqual(expected, rotated_matrix)

        expected = [[6, 5, 4],
                    [3, 2, 1]]
        rotated_matrix = manipulate_matrix(non_square_matrix, operation)
        self.assertEqual(expected, rotated_matrix)

    def test_flip_matrix_vertically(self):
        operation = ManipulationOperation.FLIP_VERTICAL
        expected = [[7, 8, 9],
                    [4, 5, 6],
                    [1, 2, 3]]
        rotated_matrix = manipulate_matrix(simple_matrix, operation)
        self.assertEqual(expected, rotated_matrix)

        expected = [[4, 5, 6],
                    [1, 2, 3]]
        rotated_matrix = manipulate_matrix(non_square_matrix, operation)
        self.assertEqual(expected, rotated_matrix)

    def test_flip_matrix_horizontal(self):
        operation = ManipulationOperation.FLIP_HORIZONTAL
        expected = [[3, 2, 1],
                    [6, 5, 4],
                    [9, 8, 7]]
        rotated_matrix = manipulate_matrix(simple_matrix, operation)
        self.assertEqual(expected, rotated_matrix)

        expected = [[3, 2, 1],
                    [6, 5, 4]]
        rotated_matrix = manipulate_matrix(non_square_matrix, operation)
        self.assertEqual(expected, rotated_matrix)
