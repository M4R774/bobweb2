import math
import string
from enum import Enum
from typing import List


class Align(Enum):
    LEFT = 0
    RIGHT = 1
    CENTER = 2


class ManipulationOperation(Enum):
    ROTATE_90 = 90                  # Clockwise (+90 degrees)
    ROTATE_NEG_90 = -90             # Counter clockwise (-90 degrees)
    ROTATE_180 = 180                # Upside down (+/- 180) degrees)
    FLIP_VERTICAL = 'vertical'      # Flip vertically
    FLIP_HORIZONTAL = 'horizontal'  # Flip horizontally


# Array = List of Lists (2d)
class MessageArrayFormatter:
    def __init__(self, column_delimiter: string, heading_delimiter: string):
        self.column_delimiter = column_delimiter  # Character used between columns
        self.heading_delimiter = heading_delimiter  # Character used between heading and data rows
        self.column_to_trunc = None
        self.maximum_row_width = None
        self.column_alignments = None

    # Builder method to add truncation if any row width is over given length
    def with_truncation(self, maximum_row_width=28, column_to_trunc=0):
        self.maximum_row_width = maximum_row_width  # in monospace characters
        # index of column which content should be truncated if row does not fit to maximum_row_width
        self.column_to_trunc = column_to_trunc
        return self

    # builder method to set each column alignment in order of columns
    def with_column_align(self, column_alignments: List[Align]):
        self.column_alignments = column_alignments
        return self

    def format(self, array: List[List[any]], last_heading_row_index=0) -> string:
        column_widths = self.calculate_content_length_max_for_columns(array)
        delimiter_count = len(column_widths) - 1  # delimiters are only between columns
        array_width = sum(column_widths) + (delimiter_count * len(self.column_delimiter))

        width_of_heading_delimiter = array_width
        if self.maximum_row_width is not None:
            width_of_heading_delimiter = min(array_width, self.maximum_row_width)

        array_str = ''
        for (r_index, row) in enumerate(array):
            row_str = ''
            for (i_index, item) in enumerate(row):
                column_max_width = column_widths[i_index]
                align = self.get_text_alignment(i_index)
                item_str = fit_text(item, column_max_width, align)
                delimiter_count = 0 if i_index == len(row) - 1 else 1  # no delimiter for last column
                item_str_with_delimiter = item_str + self.column_delimiter * delimiter_count
                row_str += item_str_with_delimiter
            array_str += row_str + '\n'

            if r_index == last_heading_row_index:
                array_str += str(self.heading_delimiter * width_of_heading_delimiter)[:width_of_heading_delimiter] + '\n'

        return array_str

    def calculate_content_length_max_for_columns(self, array: List[List[any]]) -> List[int]:
        transposed_array = transpose(array)
        # Note, objects and arrays are assumed to be shown in their string representation
        # example: tuple (1, 2) -> '(1, 2)' => length of 6. Brackets, commas and spaces are included in the length
        column_widths = [max([len(str(row_item)) for row_item in column]) for column in transposed_array]

        if self.maximum_row_width is not None:
            delimiter_count = len(column_widths) - 1  # delimiters are only between columns
            delimiter_chars_taken_total = delimiter_count * len(self.column_delimiter)
            chars_over_max_width = (sum(column_widths) + delimiter_chars_taken_total) - self.maximum_row_width

            if chars_over_max_width > 0:
                column_widths[self.column_to_trunc] = max(0, column_widths[self.column_to_trunc] - chars_over_max_width)

        return column_widths

    def get_text_alignment(self, index: int):
        if self.column_alignments is not None:
            return self.column_alignments[index]
        else:
            # Assumption, first row align left, rest align right
            return Align.LEFT if index == 0 else Align.RIGHT


def fit_text(item: any, max_width: int, align: Align = Align.LEFT):
    chars_over_limit = len(str(item)) - max_width
    if chars_over_limit > 0:
        item = truncate_string(item, chars_over_limit)

    return form_single_item_with_padding(str(item), max_width, align)


def form_single_item_with_padding(item: any, max_len: int, align: Align, padding=' '):
    if align == Align.LEFT:
        return str(item) + padding * (max_len - len(str(item)))
    if align == Align.RIGHT:
        return padding * (max_len - len(str(item))) + str(item)
    if align == Align.CENTER:
        padding_left = math.floor(max_len - len(str(item)) / 2)
        padding_right = max_len - padding_left - len(str(item))
        return padding_left * padding + str(item) + padding_right * padding


# Transposes given matrix. Each row should have same number of items
# Otherwise transposed matrix has None values on last rows
def transpose(matrix):
    rows = len(matrix)
    columns = max([len(row) for row in matrix])

    matrix_transposed = []
    for c_index in range(columns):
        row = []
        for r_index in range(rows):
            # If original matrix has different lengths on different rows, None is used in place of non existing items
            item = matrix[r_index][c_index] if len(matrix[r_index]) > c_index else None
            row.append(item)
        matrix_transposed.append(row)

    return matrix_transposed


def manipulate_matrix(m: List[List], operation: ManipulationOperation):
    """
    Rotate a matrix either clockwise or counterclockwise.
    Args:
        m (List[List]): The matrix to be rotated.
        operation (ManipulationOperation): The direction to rotate the matrix.
    Returns:
        List[List]: The rotated matrix.
    """

    # Get the number of rows and columns in the matrix.
    row_count = len(m)
    col_count = len(m[0])

    # Create a new matrix to hold the rotated values.
    rotated_matrix = [[0] * row_count for _ in range(col_count)]

    for i in range(row_count):
        for j in range(col_count):

            match operation:
                case ManipulationOperation.ROTATE_90:
                    rotated_matrix[j][row_count - 1 - i] = m[i][j]

                case ManipulationOperation.ROTATE_NEG_90:
                    rotated_matrix[col_count - 1 - j][i] = m[i][j]

                case ManipulationOperation.ROTATE_180:
                    rotated_matrix[row_count - 1 - i][col_count - 1 - j] = m[i][j]

                case ManipulationOperation.FLIP_VERTICAL:
                    rotated_matrix[row_count - 1 - i][j] = m[i][j]

                case ManipulationOperation.FLIP_HORIZONTAL:
                    rotated_matrix[i][col_count - 1 - j] = m[i][j]

                case _:
                    # None or unknown value: no rotation
                    rotated_matrix[i][j] = m[i][j]

    return rotated_matrix


def truncate_string(value, chars_over_limit: int, number_of_dots=2):
    # Remove n + m characters.
    #  - n = number of characters that row is over the limit
    #  - m = number of dots added to indicate that value was truncated
    return str(value)[:-(chars_over_limit + number_of_dots)] + ('.' * number_of_dots)
