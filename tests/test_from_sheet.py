import sys
from unittest.mock import patch, MagicMock


def _set_argv(*args):
    sys.argv = ["from_sheet.py", "--spreadsheet-id", "abc123"] + list(args)


def test_parse_args_defaults():
    _set_argv()
    import importlib
    import from_sheet
    importlib.reload(from_sheet)
    args = from_sheet.parse_args()
    assert args.spreadsheet_id == "abc123"
    assert args.sheet_name is None          # fix: default là None, không phải "Sheet1"
    assert args.col_website == "website"    # fix: chữ thường, khớp tên cột thực tế
    assert args.output_sheet == "Enriched"
    assert args.delay == 1.0


def test_parse_args_custom():
    _set_argv("--sheet-name", "RawData", "--output-sheet", "Done", "--delay", "2.5")
    import from_sheet
    import importlib
    importlib.reload(from_sheet)
    args = from_sheet.parse_args()
    assert args.sheet_name == "RawData"
    assert args.output_sheet == "Done"
    assert args.delay == 2.5
