from unittest import TestCase


from bobweb.bob.utils_format import ManipulationOperation, manipulate_matrix

# Simple 3x3 matrix (list of lists) for testing
simple_matrix = [[1, 2, 3],
                 [4, 5, 6],
                 [7, 8, 9]]


class TestMatrixManipulationOperations(TestCase):
    """ Tests format utils. Uses Unit test case as no need for models or database connections """

    def test_rotate_matrix_clockwise_90(self):
        expected = [[7, 4, 1],
                    [8, 5, 2],
                    [9, 6, 3]]
        rotated_matrix = manipulate_matrix(simple_matrix, ManipulationOperation.ROTATE_90)
        self.assertEqual(expected, rotated_matrix)

    def test_rotate_matrix_counter_clockwise_90(self):
        expected = [[3, 6, 9],
                    [2, 5, 8],
                    [1, 4, 7]]
        rotated_matrix = manipulate_matrix(simple_matrix, ManipulationOperation.ROTATE_NEG_90)
        self.assertEqual(expected, rotated_matrix)

    def test_rotate_matrix_180(self):
        expected = [[9, 8, 7],
                    [6, 5, 4],
                    [3, 2, 1]]
        rotated_matrix = manipulate_matrix(simple_matrix, ManipulationOperation.ROTATE_180)
        self.assertEqual(expected, rotated_matrix)

    def test_flip_matrix_vertically(self):
        expected = [[7, 8, 9],
                    [4, 5, 6],
                    [1, 2, 3]]
        rotated_matrix = manipulate_matrix(simple_matrix, ManipulationOperation.FLIP_VERTICAL)
        self.assertEqual(expected, rotated_matrix)

    def test_flip_matrix_horizontal(self):
        expected = [[3, 2, 1],
                    [6, 5, 4],
                    [9, 8, 7]]
        rotated_matrix = manipulate_matrix(simple_matrix, ManipulationOperation.FLIP_HORIZONTAL)
        self.assertEqual(expected, rotated_matrix)

